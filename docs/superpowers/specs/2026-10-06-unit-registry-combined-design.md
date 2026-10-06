# Unit Registry — combined design (June dynamic-units spec + October CRUD/MCP request)

- **Date:** 2026-10-06
- **Status:** APPROVED 2026-10-06 (all of §0 C1–C8 accepted). Revised and re-approved 2026-10-06: **unit types** added (C9, §4.4, §6.1, §7.1). Next: implementation plan.
- **Merges:**
  - **[J]** `2026-06-01-dynamic-unit-normalization-design.md`: backend, never implemented (status "DESIGN — not code"; its branch `features/normalization-dynamic` no longer exists on origin).
  - **[UI]** `2026-06-01-units-admin-frontend-design.md`: admin UI, on `features/poc`, depends on [J]'s API.
  - **[O]** October 2026 brainstorming: "create a service for CRUD of normalization unit, then add in the normalization mcp the tools for create/update/deactivate/get unit".
- **Already shipped:** `mcp-normalize-unite-service` (PR #845, merged into `features/poc`), with `normalize_quantity` and `normalize_range`.
- **Section tags:** each section says where it comes from: **[J]** kept from June, **[O]** from October, **[J+O]** merged.

---

## 0. Choices to confirm before this spec is approved

These are the places where [J] and [O] disagree. Each row gives a recommendation; the rest of the spec is written as if every recommendation is accepted.

| # | Question | [J] said | [O] said | **Recommendation** | Why |
|---|---|---|---|---|---|
| C1 | Where do writes live? | gRPC mutation RPCs inside the normalizer | Separate CRUD service | **Separate service** `unit-registry-service` | Asked for explicitly in [O]. Bonus: the 5 normalizer replicas become read-only and carry no write listener or admin key |
| C2 | Transport of the CRUD service | gRPC (proto in §6 / A.3) | REST | **gRPC, [J]'s contract**, moved to a new proto `unit_registry.proto` | [UI]'s BFF is designed for gRPC + `ADMIN_KEY`; the MCP (Go) already speaks gRPC; one contract instead of two |
| C3 | Propagation | Poll `registry_version` every 30s | RabbitMQ fanout, targeted per unit, outbox | **Push ([O])** + [J]'s `registry_version` used for gap detection | [J] deferred push explicitly "with no structural change"; 5 replicas need fanout |
| C4 | How a replica applies an event | Never `define()` on the live registry; always build new + swap ([J] §3.4, post-review) | In-place `define()` for creates, rebuild for update/deactivate | **Always build-new-and-swap, from the local table** (no network) | pint `UnitRegistry` is not thread-safe; 50 gRPC threads read it. Still "only the concerned unit": the event carries one unit, the replica patches one row of its local table. Cost ~0.22s per event (measured) |
| C5 | Database | Shared `catalog_db` (user override in June, "open for reversal") | Own `normalization_db` | **Own `normalization_db`** | Latest decision; [J] §2.4 says switching is a DSN change only |
| C6 | Phase-1 layer scope | All 5 layers (A, B, C, D, E1–E3) | Units only | **Layers A + B + D (read-only) in P1**; C, E1, E2, E3 in P2 with the admin UI | The October request is unit CRUD; C/E3 CRUD only matters once the admin UI exists. Full [J] schema created in P1 so P2 needs no migration |
| C7 | Regression sample on create | Mandatory (G4) | Not planned | **Mandatory**, including from MCP | It is the permanent test that stops a wrong conversion factor from going live. The MCP tool takes a `sample` object |
| C8 | Per-unit optimistic `version` | none ([J] uses `FieldMask` partial update) | `version` column | **Drop it**; keep `FieldMask` + global `registry_version` | YAGNI: low write volume, single operator surface |
| C9 | Unit types (added 2026-10-06) | — | User: "add the type of unit, e.g. DIMENSION, CAPACITY; other types not registered yet" | **Open vocabulary `unit_types`**, linked **many-to-many to physical dimensions**; a unit inherits the types of its dimension. Explicit CRUD (gRPC + MCP); unknown codes are rejected, never auto-created. **Metadata only in P1** | Decided with the user: attach to the dimension, several types per dimension, explicit registration (so `CAPACITE` vs `CAPACITY` typos can't fork the vocabulary), no effect on normalization |

---

## 1. Goal [J+O]

Stop the "FIX 1–16" cycle ([J] §1.1): today, adding a unit means editing `infrastructure/unit_normalization_service.py` (963 lines on 2026-10-06), opening a PR, rebuilding the image and redeploying 5 replicas. Until then, every product with that unit returns `{}` and goes to the DLQ.

After this work:

| | Today | After P1 |
|---|---|---|
| Add a unit | code → PR → build → redeploy ×5 | `create_unit` MCP tool (or gRPC `RegisterUnit`) → G1–G6 → ACTIVE |
| Time to live | hours | ~1s on all 5 replicas (event + 0.22s rebuild) |
| Safety | reviewer reads a dict diff | 6 automated guards + a mandatory regression sample |

**Non-goals [J]:** do not rewrite the pint engine; do not change the output of any existing case. The seed-parity test (§9) proves it.

---

## 2. Facts this design rests on (measured 2026-10-06)

- **pint 0.24.4** (what `pip install pint` gives in `python:3.10-slim`; `requirements.txt` has bare `pint`). Probed in a container:
  - `define()` of a **new** name on a live registry works.
  - `define()` of an **existing** name is **silently ignored** (`3 galette` stays `3 count` after redefining it as `2 * count`).
  - No public API removes a unit (only `remove_context`).
  - `UnitRegistry()` builds in **0.22 s**.
- **[J] §5.2:** `define()` is **lazy**: `baz = 3 * nonexistent` is accepted, and fails only when used. Validation must force evaluation (G1).
- `graph-rag-normalize-unite-service` runs **`replicas: 5`** in `docker-compose.yml`.
- **[J] §1.1 layer sizes** (re-asserted at seed extraction, never hard-coded): A = 56 defines, B = 200 keys, C = 99 ordered keys, D = 36 dimensions.
- MySQL `docker-entrypoint-initdb.d` scripts only run on an **empty** volume; `gateway_mysql_data` already exists.

---

## 3. Architecture [J+O]

```
 MCP create/update/deactivate/get_unit        (P2) account-service BFF  ── admin UI [UI]
            │ gRPC + Bearer UNITS_ADMIN_KEY              │ gRPC + Bearer UNITS_ADMIN_KEY
            ▼                                             ▼
   ┌──────────────────────── unit-registry-service (NEW, Python, gRPC) ───────────────────────┐
   │ G1–G6 (libs/unit-registry) → build FULL new registry → txn{ row + registry_version+1      │
   │                                                            + outbox row } → commit        │
   │ outbox relay ──publish (confirms)──▶ RabbitMQ fanout exchange "normalization.units"       │
   └────────────────────────────────────────────┬─────────────────────────────────────────────┘
                     MySQL normalization_db      │ one exclusive auto-delete queue per replica
                                                 ▼
   graph-rag-normalize-unite-service ×5  (READ-ONLY consumer)
     consumer thread: event → gap check → patch ONE row of local table → build new RegistryBundle
                      (libs/unit-registry builder, no network) → atomic swap
     startup / reconnect / gap: full ListUnits(status=ACTIVE) from unit-registry-service
     hot path: NormalizeQuantity / NormalizeRange read the in-memory RegistryBundle only
```

### 3.1 Components

| Component | Role | Change |
|---|---|---|
| `libs/unit-registry/` (NEW Python lib) | Domain types ([J] A.1), `build_registry_bundle(units, dimensions)` ([J] §3.3), `validate_unit()` G1–G6 ([J] §5, collect-all per [J] B.2), seed extractor ([J] §9) | Shared by the CRUD service (trial build) and the normalizer (real build), so the two can never disagree |
| `apps-microservices/unit-registry-service/` (NEW) | gRPC `UnitRegistryService` (§6), SQLAlchemy 2 + PyMySQL ([J] D8), outbox relay, auth interceptor ([J] B.3), `/health` + `/metrics` on a side HTTP port | New |
| `graph-rag-normalize-unite-service` | Reads layers A/B/D from a `RegistryBundle` instead of the hard-coded dicts; event consumer; frozen dicts kept as **fallback floor** ([J] D11) | Modified; no DB access, no write RPCs |
| `mcp-normalize-unite-service` | 4 unit tools (§7) + 5 unit-type tools (§7.1) calling `UnitRegistryService` over gRPC | Modified |
| `protos/grpc_stubs/unit_registry.proto` (NEW) | [J] A.3's CRUD contract, moved off `GraphNormalizationService` | `graph_normalization.proto` stays **untouched** |

### 3.2 Concurrency rule [J] §3.4, kept

- Never `define()` on the serving registry. Build a brand-new `RegistryBundle` off to the side, validate it whole, then reassign one attribute (GIL-atomic).
- **CRUD write path:** validate G1–G6, build the full new registry from all ACTIVE units plus the change, and only then commit. A unit that passes per-candidate guards but breaks the global registry is never stored.
- **Replica build failure** after an event: keep serving the **last-good** bundle (not the frozen fallback, which would revert every dynamic add), raise a loud metric, do not record the version as applied, and resync on the next event or reconnect.

---

## 4. Data model — MySQL `normalization_db` [J] §4, with [O] deltas

Conventions from [J] §4: `CHAR(36)` UUID PKs, `JSON` lists, `ENUM` closed sets, `DATETIME` timestamps, `utf8mb4_bin` where lookups are accent-sensitive, FK `ON DELETE RESTRICT` to the dimension vocabulary.

### 4.1 Created and used in P1

- **`unit_dimensions`**: exactly [J] §4.1 (36 seed rows, `canonical_unit`, `bypass_pint` for `count`/`count_rate`). **Read-only in P1** (seeded; no write RPC until P2).
- **`units`**: exactly [J] §4.2. In P1 the write path **rejects** `kind=PASSTHROUGH`, `rewrite_expression`, `label_condition` and `canonical_override` with `InvalidArgument "not supported before P2"`. The seed leaves them NULL/default (E1/E2 stay in code in P1). Deactivate = `status=DISABLED` ([J] soft delete).
- **`registry_meta`**: exactly [J] §4.5. `registry_version` is bumped in the same transaction as every write. In [O]'s push model it is used for **gap detection** (§5), not polling.
- **`unit_events` (outbox, [O])**:

  | column | type |
  |---|---|
  | `id` | BIGINT PK AUTO_INCREMENT |
  | `registry_version` | BIGINT NOT NULL UNIQUE |
  | `payload` | JSON NOT NULL (event body, §5) |
  | `created_at` | DATETIME NOT NULL |
  | `published_at` | DATETIME NULL |

### 4.2 Created in P1, used from P2 (no migration later)

`label_rules` ([J] §4.3), `disambiguation_rules` ([J] §4.4), `unit_proposals` ([J] §4.5): schema created, **not seeded, not read** in P1. Layers C and E3 keep running from code until P2 seeds them and switches the engine over, behind their own parity gate.

### 4.3 Bootstrap [J] §9.1 + [O]

- `unit-registry-service/init-db/01_schema.sql` creates the database, the `normalization_user` user and all tables. It is mounted into `mysql` for fresh volumes.
- For the **existing** volume, the service CLAUDE.md documents a one-time `mysql -uroot … < init-db/01_schema.sql`.
- On boot, the service runs `Base.metadata.create_all()` and `bootstrap_units()` when `units` is empty ([J]'s "skip if exists").

### 4.4 Unit types (C9) — created, written and read in P1

A **type** is a business category of measurement (`DIMENSION`, `CAPACITY`, …). The vocabulary is **open**: new types are registered at runtime through CRUD, never hard-coded. A type is attached to **physical dimensions**, many-to-many. A unit has no type column; its types are **inherited from its dimension**. For example, if `length` is linked to `DIMENSION`, then `mm`, `cm` and `pouce` are all `DIMENSION`.

```sql
CREATE TABLE IF NOT EXISTS unit_types (
  id          CHAR(36)     PRIMARY KEY,
  code        VARCHAR(64)  NOT NULL,          -- stable key, ^[A-Z][A-Z0-9_]{1,63}$, immutable after create
  label       VARCHAR(128) NOT NULL,          -- display label, e.g. 'Capacité'
  description VARCHAR(512) NULL,
  is_active   TINYINT(1)   NOT NULL DEFAULT 1,
  created_by  VARCHAR(255) NOT NULL,
  created_at  DATETIME     NOT NULL,
  updated_at  DATETIME     NOT NULL,
  UNIQUE KEY uniq_unit_type_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS dimension_unit_types (
  dimension_id CHAR(36)     NOT NULL,
  unit_type_id CHAR(36)     NOT NULL,
  created_by   VARCHAR(255) NOT NULL,
  created_at   DATETIME     NOT NULL,
  PRIMARY KEY (dimension_id, unit_type_id),
  CONSTRAINT fk_dut_dimension FOREIGN KEY (dimension_id) REFERENCES unit_dimensions (id) ON DELETE RESTRICT,
  CONSTRAINT fk_dut_type      FOREIGN KEY (unit_type_id) REFERENCES unit_types (id)      ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Rules:

- **T1 — explicit registration.** Linking a code that does not exist, or is inactive, is rejected (`NotFound` / `FailedPrecondition`); nothing is auto-created. A near-duplicate code (same code once `_` and accents are stripped, e.g. `CAPACITE` vs `CAPACITÉ`) is rejected on create (`AlreadyExists`, the message names the existing code).
- **T2 — `code` is immutable.** Update changes `label` and `description` only.
- **T3 — deactivate is soft.** `is_active=0` keeps the links, but inactive types are omitted from every read that returns types (`GetUnit`, `ListUnits`, `GetUnitType` on a dimension). Reactivating restores them. Hard delete is out of scope.
- **T4 — links are set per dimension, as a whole.** `SetDimensionTypes(dimension, codes[])` replaces that dimension's set (empty list clears it). That is idempotent and avoids add/remove pairs.
- **T5 — metadata only.** Types never enter the `RegistryBundle`, do **not** bump `registry_version`, write **no** outbox row, and emit **no** event. The 5 normalizer replicas are unaware of them.
- **Seed:** the types `DIMENSION` (label `Dimension`) and `CAPACITY` (label `Capacité`) are created at bootstrap **with no links**. Which dimensions they cover is an operator decision, made with `set_dimension_types`.

---

## 5. Propagation [O], with [J]'s version as the ordering key

**Exchange:** `normalization.units`, type **fanout**, durable. Each normalizer replica declares an **exclusive, auto-delete, server-named** queue bound to it, so every replica receives every event. (A shared work queue would reach 1 replica in 5.)

**Event body** (persistent JSON):

```json
{
  "event": "unit.created | unit.updated | unit.disabled",
  "registry_version": 42,
  "unit_id": "uuid",
  "unit": { "...full UnitRecord after the change, as in ListUnits..." },
  "occurred_at": "2026-10-06T12:00:00Z"
}
```

**Outbox relay** (in `unit-registry-service`): publishes `unit_events` rows with `published_at IS NULL` in `registry_version` order, using publisher confirms. It sets `published_at` only after the broker acks. A crash between commit and publish only delays an event; it never loses one.

**Replica handling**, per event:

1. `registry_version ≤ applied_version` → drop (duplicate).
2. `registry_version > applied_version + 1` → **gap**: full resync (`ListUnits(status=ACTIVE)`), then set `applied_version` from the response.
3. Otherwise, patch the one unit in the local table (`status=ACTIVE` → upsert; `DISABLED` → remove), build a new `RegistryBundle` from the local table, swap, and set `applied_version`.

**Full resync** happens only at startup, on every (re)connect to RabbitMQ, and on a gap. If `unit-registry-service` is unreachable at startup, the replica serves the **frozen fallback** with a loud log and metric, and retries with backoff ([J] D11).

`ListUnits` returns the current `registry_version` alongside the list, so a resync knows where it stands.

**Metrics (normalizer):** `unit_registry_applied_version`, `unit_registry_events_total{result=applied|duplicate|gap}`, `unit_registry_source{source=db|fallback}`, `unit_registry_build_seconds`, `unit_registry_build_failures_total`.

---

## 6. gRPC contract — `protos/grpc_stubs/unit_registry.proto` [J] A.3, moved

`package unit_registry; service UnitRegistryService`. Messages `UnitSpec`, `RegressionSample`, `UnitResponse`, `RegisterUnitRequest`, `UpdateUnitRequest` (with `google.protobuf.FieldMask`), `DeleteUnitRequest`, `GetUnitRequest`, `ListUnitsRequest`/`Response`, `GetRegistryStatus` are **copied verbatim from [J] A.3**, with three changes:

1. `GetUnitRequest` gains `string token = 2;` (get by id **or** token; the MCP resolves names this way).
2. `ListUnitsResponse` gains `int64 registry_version = 3;` (for resync, §5).
   `UnitResponse` gains `repeated string types = 9;`: the active type codes inherited from the unit's dimension (read-only, §4.4). `ListUnitsRequest` gains `string type = 5;` (filter by type code).
3. P1 serves only `RegisterUnit`, `GetUnit`, `ListUnits`, `UpdateUnit`, `DeleteUnit`, `GetRegistryStatus`, `ValidateUnit`, plus the unit-type RPCs in §6.1. The other RPCs from [J] §6 and B.1 (dimensions, label rules, disambiguation, proposals) are added to the proto in P2/P3, when they are implemented. No stubs for RPCs that do nothing.

**Status codes [J] §6.2:** G1–G5 failure / missing field / P2-only field → `InvalidArgument` (failing guard named). G6 → `AlreadyExists`. Unknown id/token → `NotFound`. DB down → `Unavailable`.

**Auth [J] D10 + B.3:** a server interceptor requires `authorization: Bearer <UNITS_ADMIN_KEY>` on `RegisterUnit`, `UpdateUnit`, `DeleteUnit`. Reads and `ValidateUnit` are open. Listener on `services-net` via `expose`, never `ports`. The `authorization` header is redacted in logs.

### 6.1 Unit-type RPCs (C9) [O]

```proto
rpc CreateUnitType(CreateUnitTypeRequest)         returns (UnitTypeResponse);       // WRITE
rpc UpdateUnitType(UpdateUnitTypeRequest)         returns (UnitTypeResponse);       // WRITE: label/description (FieldMask)
rpc DeactivateUnitType(DeactivateUnitTypeRequest) returns (UnitTypeResponse);       // WRITE: is_active=0 (idempotent)
rpc GetUnitType(GetUnitTypeRequest)               returns (UnitTypeResponse);       // READ: by id or code
rpc ListUnitTypes(ListUnitTypesRequest)           returns (ListUnitTypesResponse);  // READ: include_inactive flag
rpc SetDimensionTypes(SetDimensionTypesRequest)   returns (DimensionTypesResponse); // WRITE: replace a dimension's type set (T4)

message UnitTypeSpec        { string code = 1; string label = 2; string description = 3; }
message UnitTypeResponse    { string id = 1; UnitTypeSpec spec = 2; bool is_active = 3;
                              repeated string dimensions = 4;   // dimension names linked to this type
                              string created_by = 5; string created_at = 6; string updated_at = 7; }
message CreateUnitTypeRequest     { UnitTypeSpec spec = 1; string created_by = 2; }
message UpdateUnitTypeRequest     { string id = 1; UnitTypeSpec spec = 2; google.protobuf.FieldMask update_mask = 3; string updated_by = 4; }
message DeactivateUnitTypeRequest { string id = 1; string updated_by = 2; }
message GetUnitTypeRequest        { string id = 1; string code = 2; }
message ListUnitTypesRequest      { bool include_inactive = 1; }
message ListUnitTypesResponse     { repeated UnitTypeResponse types = 1; }
message SetDimensionTypesRequest  { string dimension = 1; repeated string type_codes = 2; string updated_by = 3; }
message DimensionTypesResponse    { string dimension = 1; repeated string type_codes = 2; }
```

Status codes: bad `code` format, `code` in the update mask, or an unknown dimension → `InvalidArgument`. Duplicate or near-duplicate code → `AlreadyExists`. Unknown id/code (including in `type_codes`) → `NotFound`. Inactive code in `type_codes` → `FailedPrecondition`. The auth interceptor's write set gains `CreateUnitType`, `UpdateUnitType`, `DeactivateUnitType` and `SetDimensionTypes`.

**Write pipeline [J] §6.3 + [O]:** `validate_unit()` (G1–G6 collect-all) → if not ok, abort with the first failing guard's code → build + validate the full new registry → `BEGIN { write units row; registry_version += 1; insert unit_events row } COMMIT` → return `UnitResponse{registry_version}`. The relay publishes asynchronously.

---

## 7. MCP tools — `mcp-normalize-unite-service` [O]

A new gRPC client to `unit-registry-service` (`UNIT_REGISTRY_GRPC_ADDR`, `UNITS_ADMIN_KEY` sent as a bearer on write calls). Stubs are generated by the service's existing `proto/generate.sh`. The registry `Clients` struct gains `Units`.

| tool | input | RPC |
|---|---|---|
| `create_unit` | `token` (req), `dimension` (req), `sample` (req: `label`, `value`, `expected_canonical_value`, `expected_canonical_unit`, optional `unit`, `data_type`, `expected_canonical_max`), optional `pint_definition`, `aliases[]`, `depends_on[]`, `case_sensitive` | `RegisterUnit` |
| `update_unit` | `id` **or** `token` (req) + any of `dimension`, `pint_definition`, `aliases[]`, `depends_on[]`, `sample` | `GetUnit` (if token) → `UpdateUnit` with a `FieldMask` of exactly the fields given |
| `deactivate_unit` | `id` **or** `token` | `GetUnit` (if token) → `DeleteUnit` (→ `DISABLED`) |
| `get_unit` | `id` **or** `token` | `GetUnit` |

- `aliases: []` given explicitly clears the aliases; omitted leaves them unchanged (the `FieldMask` distinction from [J] §6).
- On `InvalidArgument`/`AlreadyExists`/`NotFound`, the tool returns `isError: true` with the server message, which names the failing guard, so the agent can fix its input. Other errors return `isError: true` and are logged.
- Tool descriptions state that writes go live on all replicas within about a second, and that a sample is required because it becomes a permanent regression test.
- `get_unit` output includes `types` (inherited from the dimension, §4.4).

### 7.1 Unit-type tools (C9)

| tool | input | RPC |
|---|---|---|
| `create_unit_type` | `code` (req), `label` (req), optional `description` | `CreateUnitType` |
| `update_unit_type` | `id` **or** `code` (req) + any of `label`, `description` | `GetUnitType` (if code) → `UpdateUnitType` (FieldMask of the fields given) |
| `deactivate_unit_type` | `id` **or** `code` | `GetUnitType` (if code) → `DeactivateUnitType` |
| `get_unit_type` | `id` **or** `code`; omit both to list all active types | `GetUnitType` / `ListUnitTypes` |
| `set_dimension_types` | `dimension` (req), `type_codes[]` (req, `[]` clears) | `SetDimensionTypes` |

`create_unit_type`'s description tells the agent to call `get_unit_type` without arguments first, to reuse an existing type instead of creating a near-duplicate.

---

## 8. What stays in code [J] §9.3, plus P1 scope

- **Forever:** E4 text hygiene (NFKC, paren strip, `·`→`.`, superscripts), E5 value hygiene (`+/-`, `±`, `.6g` on the pint branch), `original_unit` derivation, `_strip_accents`, and the frozen fallback dicts.
- **Until P2:** layer C (`LABEL_TO_DIMENSION`, ordered), E1 rewrites (`db(a)`→`dBA`, `tr/min`→`rpm`, …), E2 literal passthroughs (`%`, `ra`, `mohs`, `Facteur G`), E3 disambiguation (`nm`, `t/min`).

---

## 9. Testing [J] §10, scoped to P1

| Test | Gate |
|---|---|
| **Seed parity** ([J] §10.2, layers A/B/D) | Exploded B-index from the seed `==` the 200-key `UNIT_TO_DIMENSION`; every [J] §10.2 case gives identical `normalize()` / `normalize_range()` output with the DB-built bundle and with the legacy code. Counts asserted against live dicts. |
| Guards ([J] §10.1) | G1 lazy-define trap and bare `TypeError` forms; G2 coherence; G3 `nm` prefix collision and the grandfathered allow-list; G4 `.6g` vs unrounded branches and `numeric_range`; G6 duplicate. G5 is out of scope until P2 |
| pint pin | `pint==0.24.4` in both `requirements.txt` files; a probe test pins silent redefinition, lazy define and the exception set ([J] D12) |
| Write path | Full-registry validation before commit; one transaction writes row + version + outbox; P2-only fields rejected; auth interceptor rejects a missing/wrong bearer on writes and lets reads through |
| Relay | Publishes in version order, marks `published_at` only on ack, retries on nack/broker down |
| Replica | duplicate dropped; gap → resync; DISABLED removes the unit; in-flight request on the old bundle returns the old result (atomic swap); build failure keeps last-good; CRUD down at boot → fallback + metric |
| Unit types | T1 unknown/inactive code rejected and never auto-created; near-duplicate code rejected; T2 `code` immutable; T3 inactive types hidden from `GetUnit`/`ListUnits` but links kept; T4 `SetDimensionTypes` replaces the set and is idempotent; T5 no `registry_version` bump, no outbox row; `ListUnits(type=…)` filter; bootstrap seeds `DIMENSION` and `CAPACITY` with no links |
| MCP | 4 unit tools + 5 type tools against a fake `UnitRegistryService`: success, NotFound, AlreadyExists, InvalidArgument/FailedPrecondition passthrough, token/code→id resolution, `FieldMask` contents, bearer only on writes |
| Wiring | compose blocks, env vars, `tools/list` returns 11 tools |

---

## 10. Phasing [J] §11, re-cut

| Phase | Scope |
|---|---|
| **P1 (this request)** | `libs/unit-registry`, `unit_registry.proto`, `unit-registry-service` (units CRUD + ValidateUnit + outbox + auth), normalizer reads A/B/D from DB via events, unit types (C9: vocabulary + dimension links, metadata only), 9 MCP tools, seed + parity for A/B/D, pint pin |
| **P2 (admin UI)** | Dimension / label-rule / disambiguation CRUD ([J] B.1), G5, E1/E2/C/E3 seeded and DB-driven behind their own parity gate, the [UI] BFF and frontend |
| **P3** | Auto-proposals from the manual DLQ ([J] §8), unchanged, gated on a measured drain |

**Commit/PR shape for P1** (per `.claude/rules/refactoring.md`): one commit per area. PR target `features/poc`.

1. `libs/unit-registry` + tests
2. proto + stubs
3. `unit-registry-service`
4. normalizer
5. MCP tools
6. compose + docs

---

## 11. Amendments this implies to the June specs

- **[J]:** superseded for P1 by this document on C1 (writes leave the normalizer), C2 (new proto), C3/C4 (push + build-and-swap), C5 (own DB), C6 (layer phasing). Everything else ([J] §3.3–§5, §9, §10, appendices) still applies and is referenced here.
- **[UI]:** the BFF upstream changes from `graph-rag-normalize-unite-service:50057` to `unit-registry-service`; env `UnitsRegistryGRPC` points there. The "propagation toast" (`GetRegistryStatus`) now reports near-instant propagation. The Unités table can show the inherited `types` column, and P2 adds a "Types" tab (or a section of the Dimensions tab) on top of the §6.1 RPCs.

When this spec is approved, both June files get a one-line header pointing here.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Lazy `define()` lets a bad unit through | G1 forced evaluation + full-registry build before commit |
| Silent redefinition hides an update | Updates never call `define()` on an existing registry; always a fresh build |
| Event lost between commit and publish | Outbox + relay with confirms |
| Replica misses events (broker or consumer down) | Resync on reconnect; gap detection on `registry_version` |
| `unit-registry-service` down | Normalizer keeps last-good bundle (or fallback at boot); only writes are unavailable |
| Bad unit goes live fleet-wide in ~1s (vs ≤30s in [J]) | Same guards as [J] + mandatory sample; `DeleteUnit` reverts just as fast |
| Static bearer over plaintext gRPC | Internal listener only, documented threat model ([J] §6.4) |
| Existing MySQL volume skips init scripts | Documented one-time bootstrap command |
