# Dynamic Unit Normalization — Design Spec

**Service:** `graph-rag-normalize-unite-service` (+ `protos/`, `libs/grpc-stubs`, `api-gateway` for Phase 2, `graph-rag-normalize-unite-*-processor` for Phase 3)
**Branch:** `features/normalization-dynamic` (from `origin/features/poc`)
**Status:** DESIGN — implementation-ready, not code
**Date:** 2026-06-01
**Author:** Synthesis of 4 analyses (A–E inventory, catalog/Tortoise conventions, pint G1–G3 feasibility, auto-proposal/DLQ flow) + 3 adversarial critiques (coherence, completeness, safety). All critique findings are folded in and marked **[FIX]**.

---

## 0. Locked Decisions

These were decided with the user during brainstorming and are designed **around**, not relitigated:

| # | Decision | Choice |
|---|----------|--------|
| D1 | **Scope** | All 5 dynamic layers (A pint-defines, B unit→dim, C label→dim ordered, D dim→canonical, E1 rewrite / E2 bypass / E3 disambiguation) move to MySQL. E4 (text hygiene) + E5 (value hygiene) **stay in code**. |
| D2 | **Surface** (phased) | P1 = gRPC mutation RPCs; P2 = admin REST via api-gateway; P3 = auto-proposal from normalization failures. |
| D3 | **Garde-fous** | G1–G6 defense-in-depth, every add. |
| D4 | **Lifecycle** | Hybrid: manual add (gRPC/REST) → ACTIVE on passing G1–G6; auto-proposal → PENDING until operator approval. |
| D5 | **Propagation** | **Poll-only 30s reconcile loop** (no push). 5 replicas, each polls `registry_version`. Reload fn kept separable so a push transport (Redis/RabbitMQ) can be added later if needed. |
| D6 | **Runtime** | Stays **Python** (pint is Python-only — it IS the engine). Synchronous gRPC (`ThreadPoolExecutor`). Hot read path keeps using the in-memory pint registry — never the DB. |
| D7 | **Data model** | Hybrid (§4): a wide `units` table for unit-owned data + small dedicated tables for cross-cutting/ordered data. |
| D8 | **DB access** | Sync **SQLAlchemy 2.x + PyMySQL** (rejects Tortoise-async-bridge: wrong runtime; rejects raw driver: reinvents pooling). |
| D9 | **DB target** | Shared **`catalog_db`** on the `mysql` compose service (user override of the precedent's dedicated-DB default — see §2.4). Tables namespaced. |
| D10 | **Write-RPC transport** | Internal-only listener + static `ADMIN_KEY` bearer via env; documented threat model + rotation note (§6.4). |
| D11 | **Boot fallback** | DB unreachable at boot → serve the frozen in-code seed (LOUD log), reconcile heals when DB returns. |
| D12 | **pint version** | **Pinned to an exact version** in `requirements.txt`; G1/G3 behaviors verified against it in CI (§5.4). |

---

## 1. Context & Goal

### 1.1 The redeploy-per-unit pain (FIX 1–16 churn)

`infrastructure/unit_normalization_service.py` (957 lines) is a singleton built once at import. Its five dynamic layers (**verified counts** — [FIX]: the original draft mis-sized these):

| Layer | Structure | **Verified size** | Role |
|---|---|---|---|
| **A** | `ureg.define(...)` calls in `__new__` | **56 statements** | Build the pint registry |
| **B** | `UNIT_TO_DIMENSION` dict | **200 keys** | unit-string → physical dimension |
| **C** | `LABEL_TO_DIMENSION` dict | **99 keys, insertion-ordered** | French label-substring → dimension (first substring match wins) |
| **D** | `CANONICAL_UNITS` dict | **36 entries** | dimension → canonical target unit |
| **E** | `normalize()` sanitize chain | ~250 lines (~50 E1 rewrites + 4 E2 literal bypasses + 2 E3 disambiguations + E4/E5 hygiene) | sanitize/bypass/disambiguate |

> **[FIX — count accuracy]** These counts (A=56, B=200, C=99, D=36) are the live ground truth. The seed extractor (§9) MUST be **count-asserted against the live dicts at extraction time** — never hardcode magic counts. The seed-parity test (§10.2) asserts `row_count == len(live_dict)` per layer and fails loudly on drift.

The file's own comments narrate 16 successive "FIX" rounds: a human reads failures off a dead-letter queue, hand-codes a new alias/dimension/label rule, rebuilds the image, redeploys all 5 replicas. Between failure and redeploy, **every product with an unknown unit returns `{}` and is silently dropped to the DLQ.**

### 1.2 What dynamization buys

| Dimension | Today | After |
|---|---|---|
| Add a unit | Edit code → PR → CI → build → redeploy ×5 | `RegisterUnit` RPC → G1–G6 → ACTIVE |
| Time to live | Hours | Local: instant; fleet-wide: ≤30s |
| Safety | Reviewer eyeballs a dict diff | 6 automated garde-fous |
| Discovery | Human reads DLQ 16× | Auto-proposal queue ranked by occurrence (P3) |
| Blast radius of a bad unit | Whole image redeployed | One validated DB row |

**Non-goals:** does NOT rewrite the conversion engine (pint stays); does NOT make E4/E5 dynamic; does NOT change output for any existing case — the seed-parity test (§10.2) proves byte-for-byte equivalence.

---

## 2. Alternative Approaches & Resolutions

### 2.1 Data model — RESOLVED: hybrid (D7)

A logical "unit" like `decibel` fans out into ~12 string keys across A/B/C/D/E; `nm` and `t/min` touch B, C, D, E3 simultaneously. A unit is **not** a single-row entity — it's a concept joined by the `dimension` vocabulary. Layer C is **order-sensitive** and not owned by any unit (`charge`→mass belongs to no token).

**Chosen — Hybrid:** a wide `units` table for everything a *token* owns (aliases, pint def, E1 rewrite, E2 kind, dimension FK, regression sample), PLUS small dedicated tables for cross-cutting/ordered data (`unit_dimensions` D, `label_rules` C with `priority`, `disambiguation_rules` E3), plus `registry_meta` and `unit_proposals`. Minimum normalization that honors Layer-C ordering and the dimension join key.

### 2.2 DB access — RESOLVED: sync SQLAlchemy + PyMySQL (D8)

The service is synchronous (`grpc.server(ThreadPoolExecutor)`, blocking `wait_for_termination()`, no asyncio loop). Tortoise-ORM (the api-gateway precedent) is async and would force `run_until_complete` bridges into a service with no event loop — brittle, zero benefit (DB is a cold path, 3 touchpoints). Sync SQLAlchemy fits the ThreadPoolExecutor model; `QueuePool` is thread-safe and shared across worker + reconcile threads; reproduces the catalog's "models + repository + `ErrNotFound` sentinel + map-based partial update" shape (which is itself sync, in Go/GORM).

### 2.3 Code dicts — RESOLVED: frozen seed + fallback floor (D11)

Dicts are **removed as the edit surface** but **kept frozen** as: (a) the seed origin, (b) the seed-parity oracle (§10.2), (c) the boot-time fallback floor if MySQL is unreachable. DB is the authoritative live source.

### 2.4 DB target — RESOLVED: shared `catalog_db` (D9), with coupling noted

> **[FIX — factual correction]** The original draft claimed reusing `gateway_db` was "the catalog's reality." **This was wrong.** Verified: `api-catalog-service/init-db/01_schema.sql` does `CREATE DATABASE IF NOT EXISTS catalog_db; USE catalog_db;`, `config.go` defaults `MYSQL_DB=catalog_db`, user `catalog_user`, on the compose service named **`mysql`** (not `gateway-mysql`). The precedent therefore favors a **dedicated** database per service.

The user chose to place the units tables in the existing **`catalog_db`** anyway (fewer credentials, single MySQL). **Accepted tradeoff:** this couples the normalization schema to the catalog service's database. Mitigation: all six tables are namespaced with a clear prefix (`unit_*` / `*_rules` / `registry_meta`) and owned by this service's migration; the catalog service must never touch them. **Open for reversal:** switching to a dedicated `normalize_db` later is a connection-string change only.

---

## 3. Architecture

### 3.1 Hexagonal layers (kept) + new adapters

```
application/normalization_use_case.py        (use cases — unchanged boundary)
infrastructure/unit_normalization_service.py (the pint engine + the 5 layers, now DB-backed)
infrastructure/grpc_server.py                (synchronous gRPC adapter + new mutation handlers)
app/main.py                                  (composition root)
app/config.py                                (+ MySQL DSN settings)

infrastructure/db/            NEW
  engine.py        create_engine(DSN, pool_pre_ping=True, pool_recycle=3600)  — one module-level Engine
  models.py        SQLAlchemy models: units, unit_dimensions, label_rules, disambiguation_rules, registry_meta, unit_proposals
  repository.py    UnitRepo / DimensionRepo / LabelRuleRepo / DisambiguationRepo / MetaRepo / ProposalRepo
                   (ErrNotFound sentinel, map-based partial Update, ListAll, RowsAffected-as-existence)
infrastructure/registry/      NEW
  builder.py       build_registry_from_db() -> RegistryBundle (pure; two-pass validate; topo order by depends_on)
  reconcile.py     daemon thread: poll registry_version every 30s; on change build-new + atomic swap; failure -> keep last-good
  garde_fous.py    validate_unit(candidate, probe_registry, label_rules) -> ValidationResult  (G1..G6; shared by mutation + approve)
  seed.py          frozen-dict extraction + bootstrap_units() + fallback floor
```

### 3.2 Hot path vs cold path

```
                  MySQL catalog_db
   units | unit_dimensions | label_rules | disambiguation_rules | registry_meta | unit_proposals
        ▲ (3) reconcile: SELECT registry_version /30s; on change ListAll -> rebuild
        │ (2) mutation: validate G1-G6 -> persist + bump version (1 txn)
   ┌────┼──────────────────────────────────────────── POD (×5) ──────────────────────────────────┐
   │ reconcile daemon thread ──build-new-then-atomic-swap──┐                                       │
   │                                                       ▼                                       │
   │            ┌──────────────────────────────────────────────────────┐                          │
   │            │  IN-MEMORY RegistryBundle  (HOT CACHE):                │  read-only, no DB        │
   │            │   ureg (pint) + flat B-index + ordered C-list +        │◀── NormalizeQuantity /   │
   │            │   D-map + E1/E2/E3 indexes                             │    NormalizeRange        │
   │            └──────────────────────────────────────────────────────┘    (sync, hot)           │
   └────────────────────────────────────────────────────────────────────────────────────────────┘
```

The `RegistryBundle` (pint registry + materialized B/C/D/E indexes) **is** the hot-path cache. DB is touched only at: (1) startup load, (2) on-mutation, (3) 30s reconcile.

### 3.3 The `RegistryBundle` and the B-index explosion

> **[FIX — B-index materialization]** The hot path's Layer-B lookup is an **exact dict-key match** on `original_unit.strip().lower()`. The DB stores a unit's spellings as `token` + `aliases` (JSON). `build_registry_from_db()` MUST **explode** `token` + every alias into a **flat dict** `{spelling_lower: dimension}` that reproduces the live 200-key `UNIT_TO_DIMENSION` **key-for-key**. A startup parity assertion checks `built_B_index == legacy_UNIT_TO_DIMENSION`. Without this, "byte-for-byte parity" (§10.2) is unsubstantiated.

The bundle exposes exactly the structures the (unchanged) engine logic consumes:
- `ureg` — pint registry with all Layer-A defines loaded.
- `B_index: dict[str,str]` — flat `spelling_lower → dimension` (exploded from token+aliases).
- `C_rules: list[(key_substring, dimension)]` — **ordered by `priority` ASC** (replaces dict insertion order).
- `D_canonical: dict[str,str]` + `D_bypass: set[str]` (dimensions with `bypass_pint=1`: `count`, `count_rate`).
- `E1_rewrites: dict[str,str]` — `sanitized_form → pint_expression`.
- `E2_passthrough: dict[str, PassthroughRule]` — literal bypass tokens.
- `E3_disambig: dict[str, DisambigRule]` — keyed by trigger token (`nm`, `t/min`).

### 3.4 Concurrency rule (load-bearing)

> **[FIX — reconcile failure semantics + pre-commit validation]**
> - pint's `UnitRegistry` is **not thread-safe** and has **no `remove()`** (append-only). Reconcile and mutation MUST **build a brand-new registry off to the side, validate it whole, then atomically reassign the module-level reference** (single GIL-atomic attribute assignment). Never `define()` on the live registry while NormalizeQuantity threads read it. Use `UnitRegistry(cache_folder=":auto:")` to cut rebuild cost.
> - **Mutation builds + validates the FULL new registry BEFORE committing the row.** A row that passes per-candidate G1–G6 but produces a globally-inconsistent registry (e.g. an E1 rewrite depending on a not-yet-present symbol) must never be committed.
> - **Reconcile failure:** if a post-bump `ListAll → rebuild` throws, the pod **keeps serving its last-good in-memory registry** (NOT the frozen-dict fallback — that would silently revert every dynamic add), emits a LOUD metric/alert, does **not** cache the new version as consumed, and retries on the next tick.

---

## 4. Data Model (MySQL, `catalog_db`)

Conventions mirror `api-catalog-service`: `CHAR(36)` PKs (`str(uuid4())`), `JSON` for lists, `ENUM` for closed sets, `TINYINT(1)` flags, two `DATETIME NOT NULL` timestamps set by the repo, `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`, `IF NOT EXISTS`, unique business keys (= G6 at the DB layer), FK `ON DELETE RESTRICT` for the dimension vocabulary.

### 4.1 `unit_dimensions` (Layer D — the shared FK vocabulary; 36 seed rows)

```sql
CREATE TABLE IF NOT EXISTS unit_dimensions (
  id             CHAR(36)     PRIMARY KEY,
  name           VARCHAR(64)  NOT NULL,        -- token EXACTLY as code uses; keep 'frequency' and '[frequency]'
                                               -- distinct; keep 'ratio' and 'dimensionless' distinct
  canonical_unit VARCHAR(128) NOT NULL,        -- e.g. 'kilogram', 'liter / minute', 'count / second'
  bypass_pint    TINYINT(1)   NOT NULL DEFAULT 0,  -- 1 for 'count' AND 'count_rate' (E2 dimension-driven bypass)
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_by     VARCHAR(255) NOT NULL,
  created_at     DATETIME     NOT NULL,
  updated_at     DATETIME     NOT NULL,
  UNIQUE KEY uniq_dim_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 4.2 `units` (Layers A + E1 + E2-literal + the unit-owned half of B)

```sql
CREATE TABLE IF NOT EXISTS units (
  id                  CHAR(36)     PRIMARY KEY,
  token               VARCHAR(128) NOT NULL,   -- B-lookup key, stored in the original_unit form (see §4.6), pre-lowercased
  case_sensitive      TINYINT(1)   NOT NULL DEFAULT 0,  -- see [FIX] note below
  aliases             JSON         NULL,        -- additional spellings (Unicode/ASCII/accented variants of THIS token)
  kind                ENUM('NORMAL','PASSTHROUGH') NOT NULL DEFAULT 'NORMAL',
  label_condition     VARCHAR(128) NULL,        -- E2 conditional (only 'Facteur G' uses it: 'facteur')
  pint_definition     VARCHAR(255) NULL,        -- Layer A, verbatim ureg.define() string
  depends_on          JSON         NULL,        -- non-builtin symbols referenced (topo order for forced-eval)
  rewrite_expression  VARCHAR(255) NULL,        -- Layer E1; keyed on the SANITIZED form (post-E4.4) — see §4.6
  dimension_id        CHAR(36)     NULL,        -- FK -> unit_dimensions.id (declared dimension)
  canonical_override  VARCHAR(128) NULL,        -- rare per-unit override; else dimension.canonical_unit
  status              ENUM('ACTIVE','PENDING','REJECTED','DISABLED') NOT NULL DEFAULT 'ACTIVE',
  source              ENUM('seed','manual','auto_proposal') NOT NULL DEFAULT 'manual',
  regression_sample   JSON         NOT NULL,    -- G4 — see §5.2 (range samples carry min/max)
  created_by          VARCHAR(255) NOT NULL,
  created_at          DATETIME     NOT NULL,
  updated_at          DATETIME     NOT NULL,
  UNIQUE KEY uniq_unit_token (token),
  KEY idx_unit_status (status),
  KEY idx_unit_dimension (dimension_id),
  KEY idx_unit_kind (kind),
  CONSTRAINT fk_unit_dimension FOREIGN KEY (dimension_id)
      REFERENCES unit_dimensions (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

> **Load-bearing collation: `utf8mb4_bin`.** Layer B is accent-**sensitive** (`décibels` ≠ `decibels`; `μm` is Greek-mu U+03BC, not micro-sign). The code lowercases/NFKC-normalizes the *input*; `token` is the pre-lowercased form, so the DB must do exact binary match. `utf8mb4_general_ci` would wrongly collapse accented/unaccented and break the intentional distinction.
>
> **[FIX — `case_sensitive` clarification]** This flag governs **only** the literal exact-case token match for the `G` (gauss) / `Facteur G` case (code `unit.strip() == 'G'`). The actual Facteur-G discriminator is `label_condition='facteur'` + `kind=PASSTHROUGH`; `case_sensitive` just prevents a lowercased `g` (gram) from matching the `G` token. PASSTHROUGH units **skip G3's parse-collision screen** (they never enter the pint registry) — see §5.2.

### 4.3 `label_rules` (Layer C — ORDER-SENSITIVE; 99 seed rows)

```sql
CREATE TABLE IF NOT EXISTS label_rules (
  id            CHAR(36)     PRIMARY KEY,
  key_substring VARCHAR(255) NOT NULL,   -- stored ACCENTED; compared accent-stripped on BOTH sides
  dimension_id  CHAR(36)     NOT NULL,
  priority      INT          NOT NULL,   -- THE ordering. Lower = checked first = more specific.
  is_active     TINYINT(1)   NOT NULL DEFAULT 1,
  source        ENUM('seed','manual','auto_proposal') NOT NULL DEFAULT 'manual',
  created_by    VARCHAR(255) NOT NULL,
  created_at    DATETIME     NOT NULL,
  updated_at    DATETIME     NOT NULL,
  UNIQUE KEY uniq_label_key (key_substring),
  UNIQUE KEY uniq_label_priority (priority),
  KEY idx_label_active_priority (is_active, priority),
  CONSTRAINT fk_label_dimension FOREIGN KEY (dimension_id)
      REFERENCES unit_dimensions (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

**Ordering as data:** `priority` is sparse (seed 10, 20, 30, …) so a new specific rule slots between two existing ones without renumbering. The builder does `SELECT … WHERE is_active=1 ORDER BY priority ASC` and materializes an **ordered list** iterated exactly like the code's `for keyword, dim in LABEL_TO_DIMENSION.items()`. Comparison is **accent-insensitive on both sides** (`_strip_accents(key) in _strip_accents(label.lower())`). The documented traps — `capacité de production`→mass_flow before `capacité`→mass; `vitesse de rotation` before `vitesse`; `ratio masse/volume` before `ratio`; the `charge`/`consommation`/`débit`/`batterie` families — are preserved by seed priority and enforced per-add by **G5** (§5.2).

### 4.4 `disambiguation_rules` (Layer E3 — `nm`, `t/min`)

> **[FIX — nm and t/min are STRUCTURALLY DIFFERENT]** The original draft modeled them identically; that breaks parity. Verified:
> - **`nm`** is **absent** from Layer B. Its dimension comes *entirely* from disambiguation (length if a length-keyword matches, else torque). So nm's row supplies **both** the match branch **and** the default branch.
> - **`t/min`** **IS** a Layer-B key (`UNIT_TO_DIMENSION['t/min'] = '[frequency]'`). Its default comes from the **B row**; disambiguation only supplies the **override** (mass_flow + `tonne / minute`) when a mass-flow keyword matches.
>
> The table supports both via **nullable default columns**: `NULL default_*` means "no explicit default — fall through to the normal B-lookup" (t/min); non-NULL means "explicit default, token has no B row" (nm).

```sql
CREATE TABLE IF NOT EXISTS disambiguation_rules (
  id                   CHAR(36)     PRIMARY KEY,
  trigger_unit         VARCHAR(128) NOT NULL,   -- 'nm' | 't/min' (matched on unit_lower)
  keyword_list         JSON         NOT NULL,   -- OR-matched, accent-stripped; order immaterial
  match_dimension_id   CHAR(36)     NOT NULL,   -- branch when ANY keyword present (length / mass_flow)
  match_pint_expr      VARCHAR(255) NULL,       -- NULL for nm (pint parses 'nm'); 'tonne / minute' for t/min
  default_dimension_id CHAR(36)     NULL,       -- NON-NULL for nm (torque); NULL for t/min (use B-row default)
  default_pint_expr    VARCHAR(255) NULL,       -- NULL for nm; (t/min default 'rpm' handled by normal pipeline)
  is_active            TINYINT(1)   NOT NULL DEFAULT 1,
  created_by           VARCHAR(255) NOT NULL,
  created_at           DATETIME     NOT NULL,
  updated_at           DATETIME     NOT NULL,
  UNIQUE KEY uniq_disambig_trigger (trigger_unit),
  CONSTRAINT fk_disambig_match FOREIGN KEY (match_dimension_id) REFERENCES unit_dimensions (id) ON DELETE RESTRICT,
  CONSTRAINT fk_disambig_default FOREIGN KEY (default_dimension_id) REFERENCES unit_dimensions (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
```

Seed rows:
- **`nm`**: `keyword_list=["longueur d'onde","wavelength","epaisseur","diametre","rayon","distance","profondeur","largeur","hauteur","longueur"]`, `match_dim→length` (`match_pint_expr=NULL`), `default_dim→torque` (`default_pint_expr=NULL`). **No B row** (parity: nm must resolve via this rule).
- **`t/min`**: `keyword_list=["debit","capacite de production","production","consommation","tonnage"]`, `match_dim→mass_flow`, `match_pint_expr='tonne / minute'`, `default_dim=NULL`, `default_pint_expr=NULL` → default `[frequency]`/`rpm` comes from the **B row** (`t/min`) + the existing E1 `rpm` rewrite. This single row unifies the dual-copy logic the code currently duplicates in `_get_dimension` and `normalize()`.

This rule is consulted **before** the plain B lookup, exactly as the code does.

### 4.5 `registry_meta` (reconcile version) and `unit_proposals` (Phase 3)

```sql
CREATE TABLE IF NOT EXISTS registry_meta (
  id               TINYINT      PRIMARY KEY,    -- always 1
  registry_version BIGINT       NOT NULL DEFAULT 1,
  last_bumped_by   VARCHAR(255) NULL,
  last_bumped_at   DATETIME     NULL,
  CONSTRAINT chk_meta_singleton CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS unit_proposals (              -- columns ship in P1; behavior in P3
  id                  BIGINT       PRIMARY KEY AUTO_INCREMENT,  -- high-churn event table, not a catalog entity
  dedup_key           CHAR(64)     NOT NULL,   -- sha256(lower(strip(unit)) | dimension_hint | failure_reason | label_bucket)
  raw_unit            VARCHAR(128) NOT NULL,
  normalized_unit     VARCHAR(128) NOT NULL,
  dimension_hint      VARCHAR(64)  NULL,
  failure_reason      VARCHAR(64)  NULL,        -- 'no_dimension' | 'pint_parse' | 'to_failed'
  data_type           VARCHAR(32)  NOT NULL,
  occurrence_count    BIGINT       NOT NULL DEFAULT 1,
  first_seen_at       DATETIME     NOT NULL,
  last_seen_at        DATETIME     NOT NULL,
  sample_labels       JSON         NOT NULL,    -- bounded, ≤10 distinct
  sample_value        VARCHAR(64)  NULL,
  state               ENUM('PENDING','VALIDATING','ACTIVE','REJECTED','REJECTED_VALIDATION','SUPERSEDED')
                          NOT NULL DEFAULT 'PENDING',
  proposed_definition JSON         NULL,
  created_by          VARCHAR(64)  NOT NULL DEFAULT 'auto-collector',
  reviewed_by         VARCHAR(64)  NULL,
  created_at          DATETIME     NOT NULL,
  updated_at          DATETIME     NOT NULL,
  UNIQUE KEY uniq_proposal_dedup (dedup_key),
  KEY idx_proposal_state_occ (state, occurrence_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **[FIX — dedup_key]** `dimension_hint` is **null for genuinely-unknown units** (no dimension is exactly why they failed), so it can't discriminate the nm-trap population alone. The dedup key adds `failure_reason` + a coarse `label_bucket`. The nm-length-vs-torque split is resolved by the **operator at approve time**, not claimed to be auto-forced by the dedup key.

---

## 5. Garde-Fou Engine (G1–G6)

One callable `validate_unit(candidate, probe_registry, label_rules) -> ValidationResult` in `infrastructure/registry/garde_fous.py`, used by **both** the mutation handlers and the Phase-3 approve action (no duplication). Runs **between "normalize the request" and "persist"**.

### 5.1 Ordered bypass-resolution sequence (the engine's runtime control flow as data)

> **[FIX — explicit ordered bypass sequence; count vs count_rate canonical]** The engine reproduces the code's exact control flow, in this order:
> 1. **E2 literal PASSTHROUGH** on the *sanitized* unit string — the **4 literal bypasses**: `%`, `ra` (→`count`), `mohs` (→`count`), and `Facteur G` (`token='G'` + `label_condition='facteur'` → `count`). Fires **before** dimension lookup; returns `float(value)` (unrounded). A PASSTHROUGH row **fully replaces** any B row — a token is never both PASSTHROUGH and a B/`unreachable` entry.
> 2. **E3 disambiguation** (`nm`, `t/min`) — consulted before plain B lookup.
> 3. **`_get_dimension`** — B-index exact match, else ordered C-rule substring scan.
> 4. **Dimension-driven bypass** — if `dimension ∈ D_bypass` (`count`, `count_rate`): return `float(value)` (unrounded) with `canonical = D_canonical[dimension]` — i.e. **`count`→"count"** but **`count_rate`→"count / second"**. (The G2 note "canonical is count" is corrected: count_rate canonicalizes to `count / second`.)
> 5. **pint convert** — `ureg.Quantity(value, expr).to(canonical)`, magnitude rounded **`.6g`** *only here*.

### 5.2 The six guards

**G1 — pint-parse (throwaway registry).** `define()` is **lazy** — `'baz = 3 * nonexistent'` is accepted silently; the error only surfaces at use. G1 MUST force evaluation:
```python
def g1_parse(definition, rewrite_expr, full_probe):   # full_probe pre-loaded with ALL active Layer-A defines
    if definition:
        full_probe.define(definition)
        name = definition.split('=')[0].strip()
        (1 * full_probe[name]).to_base_units()          # FORCE eval -> UndefinedUnitError if RHS bogus
    if rewrite_expr:
        full_probe.parse_expression(rewrite_expr).to_base_units()
```
Catch `(pint.errors.PintError, TypeError, ValueError)` (pint leaks bare `TypeError`/`ValueError` for several malformed forms). Reject → `InvalidArgument "G1 parse failed: …"`.

**G2 — dimensional coherence.**
```python
q = 1 * probe.parse_expression(expr)
assert q.dimensionality == probe.get_dimensionality(declared_dim_base)   # reduces to declared dimension
q.to(canonical)                                                          # raises DimensionalityError on mismatch
```
PASSTHROUGH units skip G2. Reject → `InvalidArgument "G2 incoherent: …"`.

**G3 — collision detection (the `nm` trap). Our own logic, not pint's.** Default `on_redefinition='warn'`, and even `'raise'` does NOT catch prefix-formed collisions (`nm` = `nano`+`meter`). Pre-screen:
```python
def g3_collision(probe, name, has_disambiguation):
    if name in probe: raise Collision(f"{name} already a stored unit/builtin")
    for cs in (True, False):
        if probe.parse_unit_name(name, case_sensitive=cs) and not has_disambiguation:
            raise Collision(f"{name} shadows a builtin -> require a disambiguation rule")
```
A prefix-colliding token is rejected **unless** the operator supplied a `disambiguation_rules` entry. Reject → `InvalidArgument`.
> **[FIX — G3 vs the seed: grandfathering]** The existing seed ALREADY shadows builtins (`m=meter`, `kg`, `cm`, `mm`, `Pa`, `V`, `A`, `N`, `L`, `t`, …). G3 would reject its own seed. Resolution: **seed rows are trusted-by-construction and skip G3** (seed correctness is proven by the parity test §10.2). G3 consults an explicit **grandfathered-shadow allow-list** (the seed's builtin-shadowing tokens) so that later re-add/update of those tokens does not spuriously fail. An invariant test asserts every active seed row is reproducible via the live `RegisterUnit` path (with its disambiguation companion where applicable).
> **[FIX — G3 scope]** `t/min` is NOT a pint prefix-collision (it's a slash expression); it's a *semantic* overload forced into `disambiguation_rules` by policy because `t` alone is a pint builtin. Only `nm`-class single-token prefix collisions are detected by `parse_unit_name`.

**G4 — mandatory regression sample (permanent test).** Every add carries a `regression_sample` JSON. G4 builds a temp registry **including the candidate** and runs the sample end-to-end.
> **[FIX — numeric_range + rounding]** `normalize_range()` is the entry point for range samples (two scalar `numeric` calls under the hood — the engine never calls `normalize(data_type='numeric_range')`); range samples assert `valeur_min_canonique` **and** `valeur_max_canonique`. **`.6g` comparison applies only to the pint-convert branch**; the passthrough/count/unit-null branches return `float(value)` unrounded and are compared with `==`. Sample schema:
```json
{"label":"…","unit":"…","value":"…","data_type":"numeric|numeric_range",
 "expected_canonical_value": 0.0, "expected_canonical_max": null, "expected_canonical_unit":"…"}
```
The sample row persists in `units.regression_sample`; the seed-parity test (§10.2) re-runs all of them in CI forever. Reject → `InvalidArgument "G4 regression failed: …"`.

**G5 — label-rule ordering (shadow validation).** Runs only when the candidate touches `label_rules`. Invariant: for any pair where `strip(A) in strip(B)` with different dimensions, the **more specific (containing) rule must have the lower `priority`**. Catches both directions (adding a generic that shadows existing specifics; adding a specific below an existing generic). Defends the `capacité`/`vitesse`/`ratio`/`charge` traps. The `dureté`/`duree` near-miss (not a substring) is allowed. Reject → `InvalidArgument`.

**G6 — idempotency / uniqueness.**
> **[FIX — idempotency on business key]** Business key = `(token, dimension, pint_definition, rewrite_expression, kind)`, excluding provenance/sample. Identical business key → `AlreadyExists` (409). A re-add of the same `token` with a **different** regression_sample or definition → `AlreadyExists` (409), **never** a silent overwrite (use `UpdateUnit` to change a unit). DB `UNIQUE KEY` is the belt; the RPC pre-check is the suspenders.

### 5.3 Validation order & build hazards

Order (fail-fast, cheapest first): **G6 → G3 → G1 → G2 → (G5) → G4**.
- **Forced-eval is order-dependent** though `define()` is not: the startup/reconcile builder loads ALL rows first, then runs the forced-eval G1/G2 pass **in topological order of `depends_on`** (handles chained aliases like `CV = cheval_vapeur`). For a single live add, the throwaway probe is pre-loaded with all active defines.
- **Circular definitions hang pint** — wrap each `.to_base_units()` in a recursion/timeout guard; reject cycles explicitly.

### 5.4 pint version pinning (D12)

> **[FIX]** `requirements.txt` currently has bare `pint`. G1/G3 rest on version-sensitive behavior (`parse_unit_name` signature, the exception set, `on_redefinition` default). **Pin pint to an exact version.** A small executable probe in CI (the §10.1 tests) re-verifies the relied-upon behaviors against the pinned version and fails the build on drift. A pint bump is a garde-fou-affecting change requiring re-validation.

---

## 6. gRPC Contract (Phase 1)

Additive change to `protos/grpc_stubs/graph_normalization.proto` — **`NormalizeQuantity`/`NormalizeRange` untouched**. Regenerate Python stubs in `libs/grpc-stubs` via `/proto-sync`.

```proto
service GraphNormalizationService {
  // EXISTING (untouched)
  rpc NormalizeQuantity(NormalizeQuantityRequest) returns (NormalizeQuantityResponse);
  rpc NormalizeRange(NormalizeRangeRequest)       returns (NormalizeRangeResponse);

  // Phase 1 — unit catalog mutations (WRITE, admin-key gated, internal listener)
  rpc RegisterUnit(RegisterUnitRequest) returns (UnitResponse);
  rpc UpdateUnit(UpdateUnitRequest)     returns (UnitResponse);
  rpc DeleteUnit(DeleteUnitRequest)     returns (DeleteUnitResponse);   // soft-delete -> DISABLED
  rpc GetUnit(GetUnitRequest)           returns (UnitResponse);          // READ
  rpc ListUnits(ListUnitsRequest)       returns (ListUnitsResponse);     // READ
  rpc GetRegistryStatus(GetRegistryStatusRequest) returns (RegistryStatus);  // READ — propagation observability [FIX]

  // Phase 3 — proposals (RPCs defined now for forward-compat; behavior deferred)
  rpc ListProposals(ListProposalsRequest)     returns (ListProposalsResponse);
  rpc ApproveProposal(ApproveProposalRequest) returns (UnitResponse);
  rpc RejectProposal(RejectProposalRequest)   returns (ProposalResponse);
}

message UnitSpec {
  string token = 1; bool case_sensitive = 2; repeated string aliases = 3;
  string kind = 4;                 // "NORMAL" | "PASSTHROUGH"
  string label_condition = 5;
  string pint_definition = 6; repeated string depends_on = 7;
  string rewrite_expression = 8;
  string dimension = 9;            // declared dimension token (FK by name)
  string canonical_override = 10;
  RegressionSample regression_sample = 11;   // MANDATORY (G4)
}
message RegressionSample {
  string label = 1; string unit = 2; string value = 3; string data_type = 4;
  double expected_canonical_value = 5;
  optional double expected_canonical_max = 6;   // for numeric_range [FIX]
  string expected_canonical_unit = 7;
}
message RegisterUnitRequest { UnitSpec spec = 1; string created_by = 2; }
message UpdateUnitRequest {                      // partial update; FieldMask resolves the aliases-clear ambiguity [FIX]
  string id = 1; UnitSpec spec = 2;
  google.protobuf.FieldMask update_mask = 3;     // exactly which fields to apply (incl. clearing aliases)
  string updated_by = 4;
}
message DeleteUnitRequest { string id = 1; } message DeleteUnitResponse { bool success = 1; }
message GetUnitRequest { string id = 1; }
message ListUnitsRequest { string status = 1; string dimension = 2; int32 limit = 3; int32 offset = 4; }
message ListUnitsResponse { repeated UnitResponse units = 1; int64 total = 2; }
message UnitResponse {
  string id = 1; UnitSpec spec = 2; string status = 3; string source = 4;
  string created_by = 5; string created_at = 6; string updated_at = 7; int64 registry_version = 8;
}
message GetRegistryStatusRequest {}
message RegistryStatus { int64 loaded_version = 1; string last_reconcile_at = 2; int64 active_unit_count = 3; }

// Phase 3
message ListProposalsRequest { string state = 1; int32 limit = 2; int32 offset = 3; }
message ProposalView { int64 id=1; string raw_unit=2; string normalized_unit=3; string dimension_hint=4;
  string failure_reason=5; string data_type=6; int64 occurrence_count=7; repeated string sample_labels=8;
  string sample_value=9; string state=10; }
message ListProposalsResponse { repeated ProposalView proposals = 1; int64 total = 2; }
message ApproveProposalRequest { int64 id = 1; UnitSpec spec = 2; string reviewed_by = 3; }
message RejectProposalRequest { int64 id = 1; string reason = 2; string reviewed_by = 3; }
message ProposalResponse { int64 id = 1; string state = 2; }
```

> **[FIX — partial-update ambiguity]** `UpdateUnit` uses a `google.protobuf.FieldMask` so "clear aliases" vs "leave aliases unchanged" is unambiguous (the catalog's map-based partial update, expressed in proto).

### 6.2 Status-code mapping
Missing required field / any G1–G5 failure → `InvalidArgument` (failing guard named); G6 collision → `AlreadyExists`; id not found → `NotFound`; DB/infra error → `Unavailable`. (Reuses `InvalidArgument` for garde-fou failures to stay consistent with the catalog, which has no `FailedPrecondition` usage.)

### 6.3 Handler pipeline (every write RPC)
`validate required → normalize key → G6 pre-check → G3 → G1 → G2 → (G5) → G4 → build+validate FULL new registry → BEGIN txn {persist row; bump registry_version} COMMIT → atomic-swap local registry → read-after-write → return UnitResponse{registry_version}`.

### 6.4 Transport security (D10)
> **[FIX]** The server uses `add_insecure_port` (plaintext gRPC). Posture: the mutation RPCs bind to an **internal-only listener never exposed beyond the cluster mesh**; a unary interceptor requires `authorization: Bearer <ADMIN_KEY>` (env-only, per `security.md`) on the `writeMethods` allow-set. Read RPCs (`NormalizeQuantity`/`NormalizeRange`/`GetUnit`/`ListUnits`/`GetRegistryStatus`/`ListProposals`) stay unauthenticated. **Documented threat model:** a static bearer over plaintext is sniffable on the pod network — accepted only because the listener is mesh-internal; the key is rotated via env redeploy (no in-band rotation). Logs redact `authorization`. If exposure beyond the mesh is ever needed, add TLS/mTLS first.

---

## 7. Lifecycle & Propagation

### 7.1 Hybrid state machine
```
manual RegisterUnit ─G1–G6─▶ pass → ACTIVE (instant local; ≤30s fleet)   fail → rejected (never persisted)

auto-collector → PENDING ─operator Approve─▶ VALIDATING ─G1–G6 pass─▶ ACTIVE
                    │                              └ fail → REJECTED_VALIDATION (diagnostic attached, stays queued)
                    ├ operator Reject → REJECTED (collector bumps count, never resurrects)
                    └ covered by a manual add → SUPERSEDED
```
Approve reuses the **same** `validate_unit()` engine. P3 supplies the candidate queue; P1 supplies the validation+activation engine.

### 7.2 registry_version bump + 30s reconcile (poll-only, D5)
```
T+0.00  RegisterUnit on POD-A: G1–G6 pass; build+validate FULL new registry
T+0.05  BEGIN txn → INSERT units (ACTIVE) → UPDATE registry_meta SET registry_version+=1 → COMMIT
T+0.06  POD-A: atomic-swap local registry  ── LOCAL: live before the RPC returns
T+0.10  return UnitResponse{registry_version=N+1}
  … each of PODs B–E runs its own reconcile daemon …
T+≤30s  POD-x tick: SELECT registry_version → N+1 ≠ cached N → ListAll → build NEW registry → atomic swap
        (on build failure: keep last-good, alert, do NOT cache version, retry next tick — §3.4)
T+≤30s  Fleet consistent. Worst-case staleness = one poll interval.
```
Docker DNS round-robin means a request for the just-added unit may hit a not-yet-reconciled pod and fail **once** within the window — acceptable for a unit that didn't exist moments ago, self-healing, and harmless for the async/retry batch pipeline. The separable reload fn lets a Redis/RabbitMQ push replace polling later with no structural change (explicitly deferred — §11).

---

## 8. Auto-Proposal Flow (Phase 3)

Automates the FIX 1–16 cowpath. Grounding facts: `normalize()` returns bare `{}` on failure; failures fan out twice (processor → `graph_rag_normalization_retry`; retry → `graph_rag_normalization_manual_dlq`); the **manual DLQ is terminal and currently unconsumed** and is NOT in `dlq_archiver.py`'s `DLQ_QUEUES`.

1. **Capture point = the manual-DLQ tail, NOT the hot path.** A new always-on consumer `unit-proposal-collector` (clone the retry-processor's aio_pika skeleton) drains `graph_rag_normalization_manual_dlq`. The hot path is unchanged (no proto change, no DB write in `normalize()`).
2. **Diagnose:** re-run `_get_dimension` + a throwaway-registry parse → `dimension_hint`, `failure_reason`.
3. **Dedup:** `dedup_key = sha256(lower(strip(unit)) | dimension_hint | failure_reason | label_bucket)`; bump `occurrence_count`, keep ≤10 `sample_labels`.
4. **Lifecycle:** rows land PENDING; operator Approve runs G1–G6 then flips to ACTIVE (reusing the manual-add path); Reject suppresses re-proposal.
5. **YAGNI line:** ship only the cheap `unit_proposals` columns + `status`/`source` in P1. Gate the always-on collector on a **one-shot drain measurement** of manual-DLQ yield before committing to a 6th consumer. No auto-approval, no confidence scoring (locked D4). ES backfill deferred (the live queue drain covers it; ES likely lacks the data).

---

## 9. Seeding / Migration

### 9.1 One-time extraction (count-asserted)
A one-shot extractor reads the **frozen** code dicts and emits seed rows, **asserting `row_count == len(live_dict)`** per layer (A=56, B=200, C=99, D=36):
- `unit_dimensions` ← D (36). `bypass_pint=1` on `count` and `count_rate`. Keep `frequency`/`[frequency]` and `ratio`/`dimensionless` distinct.
- `units` ← A + B(unit-owned) + E1 + E2-literal. Multiple B-spellings of one token collapse into `token` + `aliases` **but the builder re-explodes them into the flat 200-key B-index (§3.3)**. The 4 literal bypasses (`%`,`ra`,`mohs`,`Facteur G`) become `kind=PASSTHROUGH` rows (no B/`unreachable` row). `db(a)`→`dBA` and `tr/min`/`trs/min`→`rpm` are seeded as **E1 rewrites** (alias + `rewrite_expression`) — [FIX]: explicitly assigned to E1, with parity cases. Every seed row carries a `regression_sample` (the G4 corpus).
- `label_rules` ← C (99) with `priority` in **exact current insertion order**, sparse (10, 20, …). G5 must pass over the seed.
- `disambiguation_rules` ← E3 (`nm`, `t/min`) per §4.4 (nm: no B row, both branches; t/min: B-row default + override).
- `registry_meta` ← single row, version 1.

Delivered as both `init-db/01_schema_units.sql` + `init-db/02_seed_units.sql` (authoritative, idempotent) **and** an idempotent `bootstrap_units()` run on boot when the table is empty (mirrors the gateway's `bootstrap_refresh_tokens` "skip if exists"). Startup also calls `Base.metadata.create_all(engine)` (the SQLAlchemy twin of GORM `AutoMigrate`).

### 9.2 Frozen dicts: seed origin + parity oracle + fallback floor (D11)
Dicts removed as the edit surface; kept frozen as the seed source, the §10.2 oracle, and the DB-unreachable boot floor (LOUD log; reconcile heals).

### 9.3 What stays in code (locked)
- **E4** (NFKC, trailing-paren strip, `·`→`.`, superscript→digit) — global text hygiene.
- **E5** (value `lstrip('+')`/`replace('/-','')`/`replace('±','')`, `data_type` gate, `.6g` rounding on the pint branch only) — value hygiene.
- **`original_unit` derivation** = NFKC + paren-strip + middot **only** (pre `db(a)`/`tr/min` rewrite, **pre** superscript-strip). B-lookup keys are matched against THIS form (§4.6 reference).
- `_strip_accents` (NFKD) for C/E3 comparison; NFKC for unit input — two different forms, both in code.
- Bootstrap dimensions / fallback dicts — the disaster floor.

### §4.6 referenced: original-vs-sanitized lookup keys
> **[FIX]** Two lookup keys per logical unit, against two different normalization stages:
> - **B-dimension lookup** uses `original_unit` (NFKC+paren+middot, superscripts/parens-content INTACT) → so B-keys include `m³`, `m²`, `kg/m³`, `db(a)`. Stored as `units.token`/`aliases`.
> - **E1 rewrite** is keyed on the **sanitized** form (post superscript-strip, e.g. `m2`, `m3`) → stored as the match key for `rewrite_expression`.
> Seed-parity (§10.2) explicitly covers `m³/h` vs `m3/h`, `m³`(volume) vs `m²`(area) vs `m2`, `kg/m³` vs `kg/m3`, `db(a)`.

---

## 10. Testing

### 10.1 Garde-fou engine unit tests (table-driven)
- **G1:** lazy-define trap (`'baz = 3 * nonexistent'` FAILS via forced eval); bare-`TypeError` forms (`'foo = = bar'`, `'z = (3'`); valid passes; assert catch set `(PintError, TypeError, ValueError)`.
- **G2:** coherent/incoherent pairs; PASSTHROUGH skips G2; count_rate canonical = `count / second`.
- **G3:** `nm` rejected without a disambiguation rule, accepted with one; both case modes; stored-name (`meter`) rejected; grandfathered-shadow allow-list lets `kg`/`m`/`t` re-validate; `t/min` is NOT a parse-collision.
- **G4:** `.6g` form (µm/nm magnitudes like `2.5e-05`) on the pint branch; unrounded on passthrough/null/count; a `numeric_range` sample asserting min+max.
- **G5:** generic `capacité` above `capacité de production` rejected; specific below generic rejected; `dureté`/`duree` near-miss allowed.
- **G6:** duplicate business key → AlreadyExists; differing sample on same token → AlreadyExists (no overwrite).
- **Circular-definition guard:** `meter = 9999*foot` with `foot→meter` rejected (timeout/cycle), not hang.
- **Chained alias:** register a unit defined in terms of a just-registered custom unit (topo order).

### 10.2 Seed-parity test — THE critical regression gate
Loads the frozen dicts (oracle) and the DB-driven registry from the seed, asserts **byte-for-byte identical output for all known cases**:
```
for case in ALL_KNOWN_CASES:                       # FIX 1–16 corpus + every B/C/D/E example + E5 + range
    assert DbDrivenNormalizer(seed).normalize(*case) == LegacyNormalizer().normalize(*case)
```
MUST cover: nm/t-min both branches; the 4 bypasses; ordered traps (`capacité de production` vs `capacité`, `vitesse de rotation` vs `vitesse`, `ratio masse/volume` vs `ratio`); Unicode dual-lookup (`m³/h` vs `m3/h`, `m³` vs `m²` vs `m2`, `kg/m³`, `db(a)`); accent-sensitive B pairs (`décibels` vs `decibels`); `unit=null` label-only; `numeric_range`; **E5 cases** (`'+/- 2'`, `'± 3.5'`, leading `+`, a non-numeric value → `{}`); count_rate `count / second`; the exploded B-index == the 200-key `UNIT_TO_DIMENSION`, the C-list == the 99-key ordered `LABEL_TO_DIMENSION`. The G4 corpus is a continuously-rerun subset.

### 10.3 Reconcile-loop test
Version unchanged → no rebuild; bumped → exactly one rebuild, new unit queryable, in-flight read on old registry returns old result (atomic-swap); DB down at startup → frozen-dict fallback + LOUD log, heals on next reconcile; **post-bump rebuild THROWS → pod retains last-good registry, alerts, version not cached, retries next tick**; assert the live ref is reassigned (never `define()` on the serving registry).

### 10.4 Proposal/dedup test (Phase 3)
`mohs` ingested N× → one row, `occurrence_count=N`, ≤10 labels; two `nm` cases with different hint/reason → two rows; Approve runs `validate_unit` and bumps version; Reject suppresses re-proposal.

---

## 11. Phasing & YAGNI

| Phase | Scope | YAGNI flag |
|---|---|---|
| **Phase 1** | gRPC mutations + 6 MySQL tables + sync-SQLAlchemy + 30s poll reconcile + seed/migration + G1–G6 + seed-parity test + internal-listener auth + pinned pint | None — this is the feature. |
| **Phase 2** | Admin REST via api-gateway (`/graph-rag-normalize-unite-service/admin/units…`); FastAPI admin routes funnel through the SAME use-case/garde-fou path; `X-Admin-Key`. | **DEFER** until a human-facing admin UI exists. Low risk, no architectural debt. |
| **Phase 3** | `unit-proposal-collector` on the manual DLQ + proposal behavior + Approve/Reject. | **DEFER hardest.** Ship cheap columns in P1; gate behavior on a measured one-shot drain. No auto-approval. |

**Explicitly deferred (the YAGNI line):** push propagation (Redis/RabbitMQ — the 30s poll suffices; reload fn kept separable); a `failure_reason` field on `NormalizeQuantityResponse` (re-derive in the collector to avoid shared-proto blast radius); ES-mining backfill; per-unit canonical-override generalization / multi-dimension units / pint contexts.

---

## 12. Risks & Open Questions

**Risks (all mitigated unless noted):**
1. **`define()` laziness (HIGH).** Mitigated by G1 forced eval. *If not implemented, dynamization is unsafe.*
2. **Prefix collisions invisible to pint (HIGH).** Mitigated by G3 `parse_unit_name` pre-screen (both case modes) + grandfathered allow-list.
3. **Layer-C ordering drift (MED).** Mitigated by `priority` + G5 + parity test.
4. **Registry not thread-safe / no remove() (MED).** Mitigated by build-new-then-atomic-swap, version-gated, `cache_folder=":auto:"`.
5. **Reconcile rebuild failure after version bump (MED).** Mitigated: keep last-good registry (NOT frozen-dict), alert, don't cache version; mutation validates the full registry before commit.
6. **DB unavailable at boot (MED).** Mitigated by frozen-dict fallback (D11).
7. **pint version drift (MED).** Mitigated by exact pin + CI behavior probe.
8. **Shared-`catalog_db` coupling (LOW, accepted, D9).** Tables namespaced; reversible to a dedicated `normalize_db` via DSN change.
9. **≤30s propagation window (LOW, accepted).** Self-heals; harmless for the batch pipeline.
10. **Phase-3 may be YAGNI (LOW).** Measured before building.

**Open questions for the user (review gate):**
- **`UNIQUE(priority)` reseeding:** sparse-gap insertion accepted, or prefer fractional/rebalancing? (Default: sparse gaps.)
- **Phase-3 proto timing:** define proposal RPCs in the P1 proto now (chosen — forward-compat, harmless) or only when P3 is built?
- **pint exact version:** which version to pin? (To be chosen at implementation against the installed/tested release.)

---

*End of design. Next: user reviews this spec, then → writing-plans for the implementation plan.*
