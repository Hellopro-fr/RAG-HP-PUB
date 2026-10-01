# Units Admin UI — Frontend Design Spec

**Host:** `apps-microservices/account-service-frontend` (Vue 3.5 + TS 5.7 + Vite 6 + Tailwind v4 / TailAdmin Pro, Pinia, vue-router)
**BFF:** `apps-microservices/account-service-backend` (Go 1.24, `net/http` `ServeMux`)
**Upstream:** `graph-rag-normalize-unite-service` (Python, gRPC `:50057`)
**Companion to:** `docs/superpowers/specs/2026-06-01-dynamic-unit-normalization-design.md` (the backend "Dynamic Unit Normalization" spec — referenced below as *the backend spec*)
**Status:** DESIGN — implementation-ready, not code
**Date:** 2026-06-01
**Author:** Synthesis of 3 analyses (BFF wiring, validate-endpoint contract, tabs UX) + 4 design-review gaps, designed AROUND the locked frontend decisions.

---

## 0. Locked Decisions (designed around, not relitigated)

| # | Decision |
|---|----------|
| F1 | **Host** = `account-service-frontend`. Verified stack: Vue 3.5 `<script setup lang="ts">`, TS 5.7, Vite 6, Tailwind v4 (TailAdmin Pro), Pinia, vue-router (lazy, `meta.requiresAuth` + `meta.minRole='admin'`), `@tanstack/vue-table` via `src/components/common/DataTable.vue`, native-fetch wrapper `src/api/client.ts` (`api<T>()`, `credentials:'include'` → **session-cookie** auth, NOT bearer), **French-only hardcoded labels**, **full-page form views (no modals)**, `AdminLayout.vue` + `AppSidebar.vue` (`menuGroups` computed), `main.css` design tokens (brand palette, Outfit font, dark mode). |
| F2 | **IA** = option A "Hub à onglets" — ONE sidebar entry "Unités" → a tabbed hub: Unités \| Dimensions \| Étiquettes \| Désambiguïsation \| Propositions. |
| F3 | **Units table** = rich default + a "Colonnes" column-visibility selector (presets Compact/Riche/Tout) + per-operator choice persisted in `localStorage`. Columns: Jeton(+alias chips) / Type(NORMAL\|PASSTHROUGH) / Dimension / Canonique / Source(seed\|manual\|auto_proposal) / Créé par(off by default) / Statut(ACTIVE\|PENDING\|DISABLED) / Actions. **Jeton + Actions locked visible.** |
| F4 | **Unit form** = TWO-PANE full-page view — fields left, a STICKY "Garde-fous" panel right showing G1–G6 as a live checklist (per-guard ok/✗ + message) + a dry-run preview card + a "Tester" button + "Enregistrer & activer" enabled **only when all pass**. |
| F5 | **Proposal queue** = COMBINED — a ranked `DataTable` (sort by `occurrence_count` DESC, search/filter by failure/state) + a master-detail pane on row-select (failing labels, sample value, `failure_reason`, a suggested next step). "Préparer" opens the prefilled form. |
| F6 | **Backend wiring** = `account-service-backend` is a BFF. It exposes admin-gated (cookie + `minRole=admin`) REST routes `/api/v1/admin/units*`, `/dimensions*`, `/label-rules*`, `/disambiguation*`, `/proposals*`, and a validate route; it forwards to the units service Phase-1 gRPC RPCs (the units service runs an INTERNAL-only gRPC listener + `ADMIN_KEY` bearer — the BFF holds that key; the browser only ever uses its session cookie). |

The four design-review gaps this spec resolves: **G-1** validate-only endpoint (`ValidateUnit` RPC + structured `ValidationResult`), **G-2** Dimensions/Étiquettes/Désambiguïsation tabs (label-rule priority reorder + live G5; disambiguation nm/t-min asymmetry), **G-3** approve forks (unit form vs disambiguation-rule form), **G-4** polish (numeric_range regression samples, raw-pint-under-French-label, propagation toast).

---

## 1. Context & Goal

### 1.1 What this is

An **admin operator UI** layered on top of the dynamic-units backend (the backend spec). Today, adding a unit means editing the 957-line `unit_normalization_service.py` singleton, opening a PR, rebuilding the image, and redeploying 5 replicas — and between failure and redeploy every product with an unknown unit is silently dropped to a DLQ (backend spec §1.1, "FIX 1–16 churn"). The backend spec moves all five dynamic layers (A pint-defines, B unit→dim, C label→dim ordered, D dim→canonical, E1/E2/E3) into MySQL and exposes Phase-1 gRPC mutation RPCs guarded by six garde-fous G1–G6. **This UI is the human surface on those RPCs**: it lets an operator add/edit/disable a unit, manage dimensions and the order-sensitive label rules and the nm/t-min disambiguation rules, and triage the auto-proposal queue — all in the browser, with the garde-fous shown live before any write commits.

### 1.2 Who uses it

`is_admin` operators (the maintainers who today read the DLQ and hand-code FIX rounds). The whole module is behind `meta.minRole='admin'`; server-side that maps to the `is_admin` boolean column in MySQL (BFF analysis §1 — there is no role string, `RequireAdmin` resolves `u.IsAllowed && u.IsAdmin`). Non-admin → 403.

### 1.3 Relation to the backend spec phases

| Backend phase (spec §11) | What the FE consumes |
|---|---|
| **P1** — gRPC mutation RPCs + G1–G6 + reconcile loop | `ListUnits/GetUnit/RegisterUnit/UpdateUnit/DeleteUnit`, the new `ValidateUnit` (this spec §3), `GetRegistryStatus`, dimensions/label-rules/disambiguation CRUD |
| **P2** — admin REST via api-gateway | *Not used.* This UI's REST surface is the **`account-service-backend` BFF**, not the api-gateway P2 surface. (The BFF reaches the units service over gRPC directly — see §2.) |
| **P3** — auto-proposal from normalization failures | `ListProposals/GetProposal/ApproveProposal/RejectProposal` → the Proposal Queue tab (§8) |

The FE phasing (§10) tracks these: FE Phase A = read-only tables (needs P1 read RPCs), FE Phase B = write form + garde-fous (needs P1 + the new `ValidateUnit`), FE Phase C = proposal queue (needs P3).

---

## 2. Architecture & Wiring

### 2.1 The auth chain (browser → BFF → units gRPC)

```
Browser (account_session cookie: JWT signed w/ JWT_SECRET, aud="session"; HttpOnly, SameSite=Lax)
   │  fetch(..., { credentials:'include' })   ← src/api/client.ts L37, cookie auth, NO bearer
   ▼
account-service-backend   RequireAdmin(JWT_SECRET, resolver)        ← internal/auth/middleware.go
   │  validates cookie JWT; resolver = FindByEmail(email) → (IsAllowed, IsAdmin); non-admin → 403
   ▼  (BFF holds the key; the browser never sees ADMIN_KEY)
graph-rag-normalize-unite-service   gRPC :50057
      metadata: authorization: Bearer <UNITS_ADMIN_KEY>            ← AppendToOutgoingContext, like CatalogClient.authCtx
```

This is an **almost-exact clone of the existing `api-catalog` BFF path** (BFF analysis §1–2): the backend already proxies an admin UI to a remote gRPC service with session-cookie auth at the edge and an `ADMIN_KEY` bearer on the outbound leg. Adding the Units BFF = cloning the `api_catalog` client+handler+route triad.

**Where `UNITS_ADMIN_KEY` lives:** add `UnitsRegistryGRPC` (default `graph-rag-normalize-unite-service:50057`) and `UnitsRegistryAdminKey` (`os.Getenv("UNITS_ADMIN_KEY")`) to `internal/config/config.go` alongside the existing `APICatalogGRPC`/`CatalogAdminKey`, dial in `internal/app/app.go` next to the catalog dial, add `UnitsClient` to `routeDeps`, and inject both env vars in `docker-compose.yml` (precedent: `CATALOG_ADMIN_KEY: ${CATALOG_ADMIN_KEY:-dev-catalog-key}`). The key never reaches the browser.

### 2.2 BFF route list (Go `ServeMux`, all `requireAdmin`)

Mounted in `internal/app/routes.go` immediately after the API-Catalog block, following its idiom (one handler, mount per method+pattern, wrap in `requireAdmin`). Reuse the existing `writeGRPCError` (maps `InvalidArgument→400`, `AlreadyExists→409`, `Unavailable→503`, `NotFound→404`) and `writeJSON` (extract them to a shared file since two handlers now use them).

| Method + pattern | gRPC RPC | Notes |
|---|---|---|
| `GET /api/v1/admin/units` | `ListUnits` | query: `status`, `dimension`, limit/offset |
| `POST /api/v1/admin/units` | `RegisterUnit` | validate + persist → 201 / 400 / 409 |
| `POST /api/v1/admin/units:validate` | **`ValidateUnit`** (G-1) | validate-only, no persist → **always 200** (see §3) |
| `GET /api/v1/admin/units/{id}` | `GetUnit` | |
| `PUT /api/v1/admin/units/{id}` | `UpdateUnit` | |
| `DELETE /api/v1/admin/units/{id}` | `DeleteUnit` | soft-delete → `status=DISABLED` |
| `GET /api/v1/admin/units/registry-status` | `GetRegistryStatus` | post-save propagation toast (§3.4, G-4) |
| `GET\|POST /api/v1/admin/dimensions` + `PUT /{id}` | `*Dimension` | G-2 |
| `GET\|POST /api/v1/admin/label-rules` + `PUT /{id}` | `*LabelRule` | list `ORDER BY priority ASC` |
| `POST /api/v1/admin/label-rules:reorder` | `ReorderLabelRules` | G-2; full `[{id,priority}]`, runs real G5, returns rebalanced sparse priorities or `InvalidArgument` |
| `GET\|POST /api/v1/admin/disambiguation` + `PUT /{id}` | `*DisambiguationRule` | G-2 |
| `GET /api/v1/admin/proposals` | `ListProposals` | ranked by `occurrence_count` |
| `GET /api/v1/admin/proposals/{id}` | `GetProposal` | master-detail pane (backend Addendum B.1) |
| `POST /api/v1/admin/proposals/{id}/approve` | `ApproveProposal` | unit-fork approve; `UnitSpec` in body → `PENDING→VALIDATING→ACTIVE` |
| `POST /api/v1/admin/proposals/{id}/reject` | `RejectProposal` | reason in body → `state=REJECTED` |

> **[REVIEW FIX] No `proposals/{id}:validate` route.** A `{id}` wildcard segment CANNOT be suffixed with `:validate` — Go `ServeMux` **panics** at registration (`bad wildcard segment`). The literal-`:` trick only works on literal segments (`units:validate`, `label-rules:reorder`). The prefill-from-proposal form calls the existing `POST /api/v1/admin/units:validate` with the prefilled spec instead. Disambiguation-fork proposals are resolved via `CreateDisambiguationRule` (+ `from_proposal_id` → `SUPERSEDED`), backend Addendum B.4 — there is no "approve a proposal with a disambiguation rule" RPC.

> **Mux ordering (BFF analysis §3):** register the literal `:validate` / `:reorder` / `registry-status` routes **before** the `{id}` wildcards. Go's `ServeMux` treats `:` as a literal path char, so `units:validate` is a distinct literal segment that won't collide with `units/{id}` — a clean choice that mirrors the existing `POST /admin/api/rescan`-before-`{id}` precedent.

> **Latent bug — DO NOT clone (BFF analysis §4):** the existing `actorEmail(r)` in `api_catalog_handlers.go` reads context key `ctxKey("user_email")`, but nothing sets it — so every catalog audit record logs an **empty actor**. When cloning for units, fix it: add an exported `auth.EmailFromContext(ctx)` reading `SessionFromContext(...).Email`, or have `RequireAuth` stash `user_email`. The units `created_by` must be the real operator email. **[REVIEW FIX] Mandatory, not advisory:** add a backend test asserting `created_by == session email` (not empty) on `RegisterUnit`; apply the identical fix to the existing api-catalog handler (it shares the bug) in a **separate commit** per the project's refactoring/shared-component rules.

> **[REVIEW FIX — auth gating, BLOCKER] Every units BFF route MUST use `auth.RequireAdmin`, NOT `requireAuth`.** The api-catalog precedent being cloned wraps its *mutations* in `requireAuth` (ANY authenticated user) and only `DELETE` in `requireAdmin` (`routes.go` L140–148). Faithfully cloning that idiom would let any logged-in HelloPro user register/edit/disable units, reorder label rules, and approve proposals — the router `meta.minRole='admin'` only *hides* the UI (client-side redirect, zero enforcement). This units registry feeds the entire RAG pipeline, so **all** units routes — **including reads** (it's an internal admin registry) — mount under `auth.RequireAdmin(cfg.JWTSecret, resolver)`. This is the one place the units BFF deliberately diverges from the catalog clone. Add backend tests asserting a non-admin session (`IsAllowed=true, IsAdmin=false`) gets **403** on `POST /units`, `units:validate`, `label-rules:reorder`, and the proposal routes. Note: server-side enforcement at the units gRPC layer is the prerequisite interceptor (backend Addendum B.3) — until both land, there is admin enforcement at no layer.

### 2.3 Frontend module / file layout

```
src/
  api/
    units.ts                 ← native-fetch wrapper, mirrors apiCatalog.ts (cookie auth via api<T>())
  types/
    units.ts                 ← TS mirrors of UnitSpec + records + ValidationResult (proto-derived)
  stores/
    units.ts                 ← Pinia: caches dimensions (FK <select> source), dimensionNames/dimensionByName
  composables/
    useColumnVisibility.ts    ← column-visibility + localStorage persistence (F3)
    useG5Shadowing.ts         ← client-side label-rule shadowing pre-check (G-2)
  router/index.ts             ← +1 hub route +6 form routes (lazy, requiresAuth + minRole='admin')
  components/layout/AppSidebar.vue   ← +1 "Unités" entry in the auth.isAdmin "Administration" group
  views/units/
    UnitsHubView.vue          ← the tabbed hub shell (tab via ?tab=, <KeepAlive>)
    UnitFormView.vue          ← two-pane unit form (create / edit / prefill-from-proposal)
    DimensionFormView.vue     ← single-pane dimension form
    DisambiguationFormView.vue← single-pane disambiguation editor (nm/t-min asymmetry)
  components/units/
    UnitsTab.vue              ← units DataTable + "Colonnes" selector
    DimensionsTab.vue         ← dimensions DataTable
    LabelRulesTab.vue         ← ordered list + reorder + live G5
    DisambiguationTab.vue     ← disambiguation DataTable
    ProposalsTab.vue          ← combined ranked table + master-detail
    GardeFousPanel.vue        ← sticky G1–G6 checklist + dry-run card + Tester/Enregistrer
    ColumnSelector.vue        ← "Colonnes" dropdown (presets + per-column toggles)
    ChipInput.vue             ← reusable chip add/remove (aliases / depends_on / keyword_list)
    RegressionSampleEditor.vue← numeric / numeric_range sample fields (G-4)
    MasterDetailPane.vue      ← proposal detail pane
```

**Sidebar** (`AppSidebar.vue`, `menuGroups` computed): add ONE entry inside the existing `if (auth.isAdmin)` "Administration" block (verified at L243–248), so it sits beside "Utilisateurs" and "Journal d'audit":

```ts
// inside the auth.isAdmin "Administration" group items
{ icon: BoxCubeIcon, name: "Unités", path: "/admin/units" },
```

**Pinia store** — only one is needed (`units` store) and only because **every form needs the dimension `<select>`** and chip-validates against the dimension vocabulary. It caches `dimensions`, exposes `dimensionNames` / `dimensionByName`, loads once on hub mount, refreshes after a dimension create/edit. Lists themselves are per-tab local state (the existing views don't use stores for list data — match that).

### 2.4 Compose / reachability note (operational, not FE)

Both services are on `services-net`; the units service is reachable as `graph-rag-normalize-unite-service:50057` (`expose`, no host port — same as the BFF dialing `api-catalog-service:9100`). **Profile gotcha (BFF analysis §5):** `account-service-backend` is `profiles:[app]`, units is `profiles:[graph-rag]`. End-to-end requires `docker compose --profile app --profile graph-rag up`; with only `--profile app` the units service won't start and the BFF returns a graceful **503** (gRPC `Unavailable`), which the FE renders as "service indisponible, réessayez" (§9). **Upstream constraint to surface:** the units service runs `replicas: 5`; the registry RPCs MUST be backed by shared persistence (the backend spec's MySQL `catalog_db`), or the "propagation ≤30s" toast (§3.4) is meaningless. This is an upstream design constraint the BFF cannot paper over — flagged in §12.

---

## 3. Backend Contract Additions (a backend ENGINE CHANGE + new RPCs — see backend Addendum B)

> **[REVIEW FIX] This is NOT a "small addendum".** It (a) re-architects the garde-fou engine (`validate_unit()` becomes collect-all/non-raising, `RegisterUnit` a thin wrapper that now runs ALL guards + dry-run with no short-circuit), and (b) the 3 catalog tabs (Dimensions/Étiquettes/Désambiguïsation) depend on ~10 CRUD RPCs that **did not exist** in the original §6 contract. All of these are now formally specified in the backend spec's **Addendum B** (B.1 missing CRUD RPCs, B.2 engine change, B.3 the prerequisite gRPC auth interceptor, B.4 the disambiguation-fork proposal resolution). This §3 details only the `ValidateUnit`/`ValidationResult` shape the panel consumes; treat Addendum B as the authoritative contract delta.

> The original framing (kept for the engine rationale): The backend spec's Phase-1 gRPC contract (§6) currently has `RegisterUnit` = validate **+** persist, with a single fail-fast English string on the first failed guard (eval order `G6→G3→G1→G2→(G5)→G4`, §5.3). The two-pane garde-fous panel needs the opposite: run **all six guards**, collect a result per guard, plus a dry-run, persist nothing. So we add a **`ValidateUnit` RPC** and make `validate_unit()` the single source of truth.

### 3.1 New RPC + messages (additive to `protos/grpc_stubs/graph_normalization.proto`)

`NormalizeQuantity` / `NormalizeRange` / `RegisterUnit` are untouched. Regenerate stubs via `/proto-sync` (Python into `libs/grpc-stubs`, Go into `internal/genproto/`).

```proto
service GraphNormalizationService {
  // ... existing Normalize* + Phase-1 CRUD ...

  // Phase 1 — VALIDATE-ONLY (READ-classified: no persist, no version bump, no swap).
  // Runs the SAME validate_unit() engine as RegisterUnit; returns ALL-guard results.
  rpc ValidateUnit(ValidateUnitRequest) returns (ValidationResult);
}

message ValidateUnitRequest { UnitSpec spec = 1; }   // same write contract as RegisterUnitRequest.spec, minus created_by

message GuardResult {
  string guard   = 1;   // "G1" | "G2" | "G3" | "G4" | "G5" | "G6"
  bool   ok      = 2;
  bool   skipped = 3;   // true => guard not APPLICABLE (PASSTHROUGH skips G2/G3; no-label-touch skips G5)
  string message = 4;   // RAW engine/pint text; empty on a plain pass
}

message DryRunResult {
  bool   ok             = 1;   // normalize() produced a result at all
  double canonical_value = 2;  // valeur_canonique (or valeur_min_canonique for a range)
  optional double canonical_max = 3;   // set ONLY for data_type="numeric_range" (G-4)
  string canonical_unit = 4;
  bool   bypassed       = 5;   // PASSTHROUGH / count / count_rate path (value returned unrounded)
  string error          = 6;   // raw failure text when ok=false
}

message ValidationResult {
  bool overall_ok            = 1;  // AND of all non-skipped guards AND dry_run.ok
  repeated GuardResult guards = 2;  // ALWAYS length 6, DISPLAY order G1..G6 (NOT eval order)
  DryRunResult dry_run       = 3;
}
```

**Contract invariants (pin to the backend spec):**
- `guards` is **always length 6, in display order G1..G6** — even though §5.3 evaluates `G6→G3→G1→G2→(G5)→G4`. The panel renders a fixed 6-row checklist; eval order is an engine internal. The engine collects into a dict keyed by guard code, emits in display order.
- **`skipped` ≠ `ok=false`.** PASSTHROUGH skips G2 (§5.2) and G3's parse-collision screen (§4.2); a unit touching no `label_rules` skips G5. Skipped guards are `ok=true, skipped=true` and **do not drag down `overall_ok`** — the panel greys them (not a green check) so the operator understands *why* it wasn't evaluated.
- **`overall_ok = (every guard where !skipped → ok) AND dry_run.ok`.** G4 (regression) *is* the dry-run's correctness assertion; both derive from the same `_run_dry_run()` call so they never contradict.
- `DryRunResult` **mirrors `NormalizeQuantityResponse`** (`canonical_value`/`canonical_unit`/error) + `optional canonical_max` for the range sample (runs `normalize_range()` = two scalar calls, §5.2). The FE reuses ONE renderer for the dry-run card.

### 3.2 Engine refactor — `validate_unit()` collect-all (CHANGED, in `infrastructure/registry/garde_fous.py`)

Today each guard `raise`s `InvalidArgument` on first failure. The refactor makes each guard a **pure predicate returning a `GuardOutcome`, never raising for an expected garde-fou failure** (it catches pint's exceptions internally and turns them into `ok=false` + raw message). The orchestrator runs every guard and aggregates. Proto-free domain mirrors (`GuardOutcome` / `DryRunOutcome` / `ValidationOutcome`) live in `infrastructure/db/types.py` (alongside the spec's Appendix A.1 dataclasses); the gRPC adapter maps domain↔proto.

```python
def validate_unit(candidate, *, dimensions, label_rules, existing_units,
                  disambiguations, grandfathered_shadows) -> ValidationOutcome:
    """Run ALL of G1–G6 + dry-run; collect, never fail-fast. Side-effect-free:
    builds a throwaway PROBE registry (all ACTIVE Layer-A defines + the candidate,
    topo-ordered by depends_on, §5.1/§5.3), runs guards against it, discards it.
    Used IDENTICALLY by ValidateUnit (return as-is) and RegisterUnit (persist iff overall_ok)."""
    probe = _build_probe_registry(candidate, dimensions, disambiguations)
    o: dict[str, GuardOutcome] = {}
    o["G6"] = _g6_idempotency(candidate, existing_units)        # eval order stays §5.3 cheap-first,
    o["G3"] = _g3_collision(candidate, probe, grandfathered_shadows, disambiguations)  # but NOTHING
    o["G1"] = _g1_parse(candidate, probe)                       # short-circuits — every guard runs.
    o["G2"] = _g2_coherence(candidate, probe, dimensions)
    o["G5"] = _g5_label_ordering(candidate, label_rules)
    dry_run, o["G4"] = _run_dry_run(candidate, probe, dimensions, disambiguations, label_rules)
    guards = tuple(o[g] for g in ("G1","G2","G3","G4","G5","G6"))   # display order
    overall_ok = all(g.ok for g in guards if not g.skipped) and dry_run.ok
    return ValidationOutcome(overall_ok=overall_ok, guards=guards, dry_run=dry_run)
```

Three load-bearing details:
1. **A failed precondition must not crash a later guard.** If G1 (parse) fails, G2/G4 can't meaningfully run → they return `ok=false` with a message like `"G2 non évalué : échec du parsing G1"` — **not** `skipped=true` (skipped = "not applicable"; failed-precondition = "couldn't check"). Each guard wraps pint calls in `try/except (PintError, TypeError, ValueError)` (the §5.2 G1 catch set) so a leaked exception becomes a clean `ok=false`, never a gRPC 500. The §5.3 circular-definition timeout guard wraps every `.to_base_units()`.
2. **G4 and the dry-run are one engine call.** `_run_dry_run()` runs the candidate's `regression_sample` through the **real `normalize()` logic** (the §5.1 ordered bypass: E2 literal → E3 disambig → `_get_dimension` → dimension-bypass → pint-convert) against the probe, then emits both `GuardOutcome("G4", ok=match, message=mismatch_detail)` and `DryRunOutcome`. **Distinction the panel surfaces:** `dry_run.ok` = "produced *a* value"; `G4.ok` = "produced the *expected* value". A green dry-run card with a red G4 = "it computed a value but not the one you predicted" — a genuinely useful operator signal.
3. **The probe registry is the §5.2 `full_probe`** — built fresh per call, discarded after. `ValidateUnit` simply never reaches the §3.4 "atomically reassign the module-level reference" step.

### 3.3 `RegisterUnit` becomes a thin wrapper (CHANGED, `infrastructure/grpc_server.py`)

```python
def RegisterUnit(self, request, context):
    candidate = _spec_from_proto(request.spec)
    snapshot  = self._load_validation_inputs()        # dims, active label_rules, units, disambig, allow-list
    result    = validate_unit(candidate, **snapshot)   # the SAME call ValidateUnit makes
    if not result.overall_ok:
        failed = next(g for g in result.guards if not g.ok and not g.skipped)
        code = grpc.StatusCode.ALREADY_EXISTS if failed.guard == "G6" else grpc.StatusCode.INVALID_ARGUMENT
        context.abort(code, f"{failed.guard} failed: {failed.message}")   # §6.2 mapping
    # overall_ok → the §6.3 persist pipeline (UNCHANGED): build+validate FULL new registry, txn, swap, return
    ...
```

> **Subtle correctness point (woven into §6 of this spec):** `RegisterUnit` still does the §3.4 "build + validate the FULL new registry BEFORE committing" against the **live snapshot at commit time** — which may have drifted between a "Tester" click and the "Enregistrer" click 30s later. So the FE "Tester" result is **advisory**; `RegisterUnit` re-validates authoritatively, and a stale "all green" can still yield a 400/409 on save. The panel handles this (§6.4): on save error it re-paints the single offending guard and re-disables save.

### 3.4 `GetRegistryStatus` — the post-save propagation feedback (G-4)

> **[REVIEW FIX] "Toast" = the existing inline-banner pattern, not new infrastructure.** The frontend has no toast/snackbar system (`header/NotificationMenu.vue` is a persisted-notification dropdown, not transient toasts); every view surfaces transient status via an inline message banner bound to a ref (e.g. `ApiCatalogListView`'s `rescanMsg`). So the four-state propagation feedback below renders as a **persistent inline banner on the post-save view that mutates through the states as the `GetRegistryStatus` poll resolves** — no `Toast.vue`/`useToast` store is introduced. Wording/states unchanged; only the rendering mechanism is the existing banner.

`RegisterUnit`'s response carries `registry_version = N+1` (the version *after* this write, §7.2). `GetRegistryStatus` returns `loaded_version` = the version the *queried pod* has reconciled to. The toast uses the **gap**, and (critically) the comparison is `loaded_version >= write_version`, never `==`:

```
1. RegisterUnit 201 → write_version = body.registryVersion
2. toast (info, persistent):  « Unité active localement. Propagation à la flotte sous ≤30 s. »
3. poll GET /units/registry-status every ~5s up to ~35s:
     if loadedVersion >= write_version → toast (success, auto-dismiss):  « Unité active et propagée (v{loaded}). »
4. after ~35s with loadedVersion < write_version (one missed window):
     toast (info, dismissable):  « Active. Propagation en cours — peut prendre jusqu'à 30 s sur les réplicas. »
```

**Why `>=` not `==` (integrity note):** between the operator's write and their poll, *other* admins may bump the version higher; the queried pod could be at `N+3`. The operator's unit is propagated as long as the pod's loaded version is `>=` their write version. `==` would falsely show "still propagating" under concurrent writes. **Why `loaded_version`, not a boolean:** the §7.2 model is poll-only across 5 replicas with Docker DNS round-robin; one `GetRegistryStatus` call hits *one* pod, so `loaded >= write` on that pod is a positive signal but not a fleet-wide guarantee. The toast copy must **never claim instant fleet consistency** — that would contradict the locked propagation model.

### 3.5 Other backend deltas required (for the backend-spec author)

1. `POST /admin/label-rules:reorder` → `ReorderLabelRules(repeated {id, priority})`: runs the **real G5**, returns rebalanced sparse priorities (10/20/30…) or `InvalidArgument` with the raw G5 message (G-2, §7).
2. Add `string suggested_resolution = N` to the proposal record (`"unit" | "disambiguation"`), set by the §8 diagnose step, so "Préparer" routes deterministically (G-3, §8).
3. Confirm garde-fou messages are returned as **raw pint strings** — no server-side translation (G-4, §6.3).
4. **BFF JSON casing — ONE deferred decision for the user:** proto3-default `camelCase` (`overallOk`, `canonicalMax`) vs `preserving_proto_field_name=True` snake_case. **Recommendation: keep proto3 camelCase** — matches the Vue/TS convention and avoids a translation layer. The FE `types/units.ts` below is written assuming this is resolved at integration time; field names there are illustrative and MUST be aligned to whatever the BFF emits.

---

## 4. Information Architecture

### 4.1 Hub à onglets (F2) — one entry, five tabs, query-param driven

ONE sidebar entry "Unités" → `/admin/units` → `UnitsHubView.vue`. Tabs are **query-param driven** (`?tab=units|dimensions|labels|disambiguation|proposals`), NOT nested routes — this keeps the single sidebar highlight and breadcrumb working (the locked IA is "one entry → tabbed hub") and lets deep-links + the back button work. Form views are **separate full-page routes** (locked: no modals).

```
UnitsHubView.vue  (shell)
 ├─ PageBreadcrumb + <h1>Unités</h1>
 ├─ tab strip: Unités | Dimensions | Étiquettes | Désambiguïsation | Propositions
 │     (each a <button>; active = brand underline; main.css brand tokens, Outfit font)
 │     bound to route.query.tab (default 'units'); switching does router.replace({ query:{ tab } })
 └─ <KeepAlive><component :is="activeTabComponent" /></KeepAlive>
       UnitsTab | DimensionsTab | LabelRulesTab | DisambiguationTab | ProposalsTab
```

`<KeepAlive>` is load-bearing: it preserves the column-visibility state and the proposal master-detail selection across tab switches. Each tab is a **component** under `src/components/units/` (not a view), so the hub composes them while the full-page forms stay separate routes.

### 4.2 Routing (lazy, admin-guarded — verified against the existing router)

The existing router already enforces `meta.minRole==='admin' && !a.isAdmin → redirect` (index.ts L52). Every entry below carries `meta:{ requiresAuth:true, minRole:'admin' }` — matching the existing `/admin/users`, `/admin/audit` entries.

```ts
// hub (tabs via ?tab=)
{ path:'/admin/units', name:'units-hub', component:()=>import('@/views/units/UnitsHubView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Unités' } },
// unit two-pane form (create / edit / prefill-from-proposal)
{ path:'/admin/units/new',      name:'unit-create', component:()=>import('@/views/units/UnitFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Nouvelle unité' } },
{ path:'/admin/units/:id/edit', name:'unit-edit',   component:()=>import('@/views/units/UnitFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Modifier unité' } },
// dimension form
{ path:'/admin/units/dimensions/new',      name:'dimension-create', component:()=>import('@/views/units/DimensionFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Nouvelle dimension' } },
{ path:'/admin/units/dimensions/:id/edit', name:'dimension-edit',   component:()=>import('@/views/units/DimensionFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Modifier dimension' } },
// disambiguation-rule form (also the target of an nm-class proposal "Préparer")
{ path:'/admin/units/disambiguation/new',      name:'disambig-create', component:()=>import('@/views/units/DisambiguationFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Nouvelle règle de désambiguïsation' } },
{ path:'/admin/units/disambiguation/:id/edit', name:'disambig-edit',   component:()=>import('@/views/units/DisambiguationFormView.vue'),
  meta:{ requiresAuth:true, minRole:'admin', title:'Modifier règle de désambiguïsation' } },
```

(Label rules and proposals have no standalone create/edit route — label rules are edited inline in their ordered list; proposals are resolved via "Préparer" which routes to the unit or disambiguation form.)

---

## 5. Screen: Units Table

`src/components/units/UnitsTab.vue` — `DataTable.vue` (reused verbatim: `h()` columns, `globalFilter`, pagination) + the "Colonnes" selector. `listUnits()` on mount into a local `ref`; the existing `error`-ref + loading pattern (§9).

### 5.1 Columns (F3)

| Column | Field | Cell render | Default visible | Lockable |
|---|---|---|---|---|
| **Jeton** | `spec.token` (+ `spec.aliases`) | `<code>` mono token + alias chips (first 3, "+N" overflow) | Yes | **locked visible** |
| Type | `spec.kind` | badge `NORMAL` (grey) / `PASSTHROUGH` (amber) | Yes | — |
| Dimension | `spec.dimension` | `<code>` mono | Yes | — |
| Canonique | `spec.canonical_override` ?? dimension's `canonical_unit` | text | Yes | — |
| Source | `source` | badge `seed` / `manual` / `auto_proposal` (3 enum values — **not** `auto`, which never matches) | Yes | — |
| Créé par | `created_by` | email text | **No (off by default)** | — |
| Statut | `status` | badge `ACTIVE` (green) / `PENDING` (amber) / `DISABLED` (grey) | Yes | — |
| **Actions** | — | "Modifier" → `/admin/units/:id/edit`; "Désactiver" (soft-delete) | Yes | **locked visible** |

### 5.2 Column-visibility selector + persistence

`@tanstack/vue-table` supports a `columnVisibility` state that `DataTable.vue` does NOT currently wire. **Additive change to `DataTable.vue`**: accept an optional `columnVisibility` v-model and pass it into `useVueTable({ state:{ get columnVisibility() {...} }, onColumnVisibilityChange })`. (Backward-compatible: existing callers omit the prop → all columns visible.)

`ColumnSelector.vue` (a `DropdownMenu.vue`-style popover) provides:
- **Three presets** — `Compact` (Jeton, Type, Dimension, Statut, Actions), `Riche` (default; everything except "Créé par"), `Tout` (all columns). Jeton + Actions are always forced on regardless of preset/toggle.
- **Per-column checkboxes** for fine control.

`composables/useColumnVisibility.ts` persists each operator's choice in `localStorage` under `units:columns:v1` (versioned key so a future column change can invalidate cleanly). On mount: read localStorage → else apply `Riche`. Jeton + Actions are filtered back on if a stale persisted value somehow hid them.

### 5.3 Filters & actions

- **Filters:** `globalFilter` (built into `DataTable`) over token/alias/dimension; plus a `status` `<select>` (`ACTIVE`/`PENDING`/`DISABLED`/all) and a `dimension` `<select>` (from the units store) feeding `listUnits({ status, dimension })`. Same filter-row pattern as `ApiCatalogListView`.
- **Row actions:** "Modifier" → unit form; "Désactiver" → `disableUnit(id)` (soft-delete → `status=DISABLED`, the backend spec keeps the row, never hard-deletes — preserves the seed-parity oracle). A confirm step ("Désactiver l'unité « {token} » ?") before the DELETE.
- **Header button** "+ Nouvelle unité" → `/admin/units/new` (same style as `ApiCatalogListView`'s `+ Créer`).

---

## 6. Screen: Unit Form (two-pane) — F4

`src/views/units/UnitFormView.vue`. Reuses the `ApiCatalogFormView.vue` skeleton (`reactive(form)`, `isEdit` computed, `onMounted` load, `submit()`), restructured into a two-column grid: `grid lg:grid-cols-[1fr_380px] gap-6 p-6`. Left = fields; right = the sticky `GardeFousPanel`.

### 6.1 Left pane — fields (the full `UnitSpec`)

| Field (FR label) | `UnitSpec` key | Control | Notes |
|---|---|---|---|
| Jeton | `token` | text, required | |
| Type | `kind` | radio `NORMAL` \| `PASSTHROUGH` | |
| Dimension | `dimension` | `<select>` from units store (FK by name) | hidden/optional when nm-style fully resolves via disambiguation |
| Alias | `aliases` | `ChipInput` | add/remove chip pattern |
| Sensible à la casse | `case_sensitive` | checkbox | only meaningful for the `G`/gauss token |
| Définition pint | `pint_definition` | text | Layer A; optional |
| Dépend de | `depends_on` | `ChipInput` (symbols) | drives probe topo-order |
| Réécriture (E1) | `rewrite_expression` | text | helper « clé = forme assainie » |
| Canonique (override) | `canonical_override` | text | placeholder = dimension's `canonical_unit` |
| Condition d'étiquette | `label_condition` | text | shown **only when** `kind=PASSTHROUGH` |
| Échantillon de régression | `regression_sample` | `RegressionSampleEditor` (§6.5) | required — G4 |

### 6.2 Right pane — `GardeFousPanel.vue` (sticky `top-6 self-start`)

Props: `spec: UnitSpec`, `clientValid: boolean` (required-fields gate). Local state: `result: ValidationResult | null`, `testing: boolean`, `dirtySinceTest: boolean`. **The FE never computes pass/fail — it reflects the body verbatim.**

The panel renders a **fixed 6-row checklist** + a **dry-run card** + the two buttons. French guard labels are the **only French the FE owns** for guards; the engine messages stay raw English (§6.3).

```ts
const GUARD_LABELS: Record<string,string> = {
  G1: 'G1 — Analyse pint (parsing de la définition)',
  G2: 'G2 — Cohérence dimensionnelle',
  G3: 'G3 — Détection de collision (piège « nm »)',
  G4: 'G4 — Échantillon de régression',
  G5: "G5 — Ordre des règles d'étiquette",
  G6: 'G6 — Unicité / idempotence',
}
```

Per-row render, driven by one `GuardResult`:

| `ok` | `skipped` | Row render |
|---|---|---|
| `true` | `false` | green ✓ + French label, no message |
| `false` | `false` | red ✗ + French label + **raw `message` verbatim** underneath in a `text-xs font-mono text-red-600` block |
| `true` | `true` | greyed/disabled + French label + small note « non applicable (PASSTHROUGH / pas de règle d'étiquette) » |

### 6.3 G-4 decision — raw English pint message under a French guard label: SHOW RAW

The `message` field carries the verbatim pint/engine error (e.g. `Cannot convert from 'newton * meter' to 'hertz'`, `UndefinedUnitError: 'nonexistent' is not defined in the unit registry`). The FE **does NOT translate it.** Example row:

> **G2 — Cohérence dimensionnelle**  ✗
> `Cannot convert from 'newton * meter' ([length]*[mass]/[time]**2) to 'hertz' (1/[time])`

Rationale (this resolves the locked-decision phrasing *"decide: show raw under a French label"* → **show raw under a French label**):
- The audience is *admin operators writing pint definitions* — they need pint's **exact** wording (the failing symbol) to fix the definition. A generic French "erreur de conversion" destroys the actionable detail.
- Translating pint's open-ended exception text is a maintenance trap (pint version drift changes wording — backend spec §5.4) and would desync from what the operator sees testing the same expression in a pint REPL.
- The French frame comes from the **label** (row title); the raw string supplies the "why". French frame, English detail. Render the raw text in a visually-distinct monospace block so it reads as "machine output", not broken UI copy.

### 6.4 Button state machine

```
mount / any field edit  →  [Tester]=enabled  [Enregistrer & activer]=DISABLED ; checklist empty/stale-greyed
click "Tester"          →  POST units:validate → 200 ValidationResult (rows show "…" spinner while pending)
                            render 6 rows + dry-run card
                            if body.overallOk === true → [Enregistrer & activer]=ENABLED ; else stays DISABLED
edit ANY field after Tester (watch(spec, …, {deep:true}))  →  dirtySinceTest=true ; [Enregistrer]=DISABLED ; mark checklist stale
click "Enregistrer & activer"  →  POST /units (RegisterUnit)
                            201      → success path (§3.4 toast) → router back to ?tab=units
                            400/409  → re-render the SINGLE failing guard from the error detail, re-disable save
```

`[Enregistrer & activer]` is `:disabled="!clientValid || !result?.overallOk || dirtySinceTest"` (the locked *"enabled only when all pass"*). Disabled tooltip: « Lancez « Tester » et corrigez les garde-fous avant d'activer. » The 400/409-after-green path (§3.3 stale-snapshot) re-paints the offending guard so the panel **degrades gracefully instead of lying** — `ValidateUnit` is advisory, `RegisterUnit` is authoritative.

> **`ValidateUnit` is HTTP 200 even on failure.** It's read-classified — it returns gRPC `OK` even when `overall_ok=false`; the failure lives in the body. The BFF maps it to **200 + full `ValidationResult`** regardless. The panel inspects `body.overallOk`; it never treats a failed validation as an HTTP error. (Contrast: `RegisterUnit` failure → gRPC `InvalidArgument`/`AlreadyExists` → BFF 400/409.) The BFF still maps gRPC `Unavailable → 503` so the panel can say "service indisponible" rather than render a misleading all-red checklist.

### 6.5 Dry-run card + `RegressionSampleEditor` (G-4 numeric_range)

`RegressionSampleEditor.vue` (embedded left pane) — a `data_type` radio drives conditional fields:

```
Échantillon de régression (obligatoire — G4)
 • Étiquette (label)          text
 • Unité (unit)               text (defaults to the token)
 • Type (data_type)           radio: numeric | numeric_range
 • Valeur (value)             text (raw string; for numeric_range the source range e.g. "10 - 20")
 — data_type === 'numeric' —
 • Valeur canonique attendue  number → expected_canonical_value
 — data_type === 'numeric_range' —
 • Valeur min. canonique      number → expected_canonical_value (the min)
 • Valeur max. canonique      number → expected_canonical_max
 • Unité canonique attendue   text   → expected_canonical_unit
```

Client validation: when `numeric_range`, require `expected_canonical_max` and enforce `max ≥ min` (inline). This matches §5.2 G4: range samples assert both bounds via `normalize_range()`; the `.6g` rounding caveat applies only on the pint branch (the FE displays whatever the dry-run returns; it doesn't round).

**Dry-run preview card** (below the checklist, shown when `result.dryRun` present):
- `ok=true`, no `canonicalMax` → « Aperçu : `{canonicalValue} {canonicalUnit}` » (e.g. « 2.5e-05 meter »).
- `ok=true`, `canonicalMax` present → two lines « min : `{canonicalValue} {canonicalUnit}` » / « max : `{canonicalMax} {canonicalUnit}` » (the G-4 numeric_range min/max display).
- `bypassed=true` → badge « Bypass (PASSTHROUGH / count) » so the operator sees the value was returned unrounded (§5.1 step 4).
- `ok=false` → red card « Aperçu (échec) » with the raw `error` (same raw-under-French-frame rule).

---

## 7. Screens: Dimensions / Étiquettes / Désambiguïsation — G-2

### 7.1 DIMENSIONS tab — simple table + form

`DimensionsTab.vue` — a plain `DataTable.vue`:

| Header | Field | Cell |
|---|---|---|
| Nom | `name` | `<code>` mono (the FK token, e.g. `mass_flow`, `[frequency]`) |
| Unité canonique | `canonical_unit` | text (`kilogram`, `liter / minute`, `count / second`) |
| Bypass pint | `bypass_pint` | badge `Oui` (amber) / `Non` (grey) + tooltip |
| Statut | `is_active` | `Actif` / `Inactif` |
| Actions | — | "Modifier" → `/admin/units/dimensions/:id/edit` |

Header button « + Créer une dimension ». **`bypass_pint` semantics in the UI:** the tooltip and form helper state that `bypass_pint=Oui` means this dimension's units skip pint conversion and return raw `float(value)` unrounded, canonical taken from `canonical_unit`. Seed cases the helper names explicitly: **`count` → canonical `count`**, **`count_rate` → canonical `count / second`** (the backend spec §5.1 step 4 corrects the "canonical is count" note — `count_rate` is NOT `count`). When `bypass_pint=Oui`, `canonical_unit` is a literal label (never pint-parsed) so no pint syntax check applies.

`DimensionFormView.vue` — single-column full-page form, **no garde-fou panel** (dimensions don't run G1–G6). Fields: `name` (text, **locked in edit mode** — it's a FK referenced by `units`/`label_rules`/`disambiguation_rules`; renaming would orphan rows), `canonical_unit`, `bypass_pint` (checkbox + the inline semantics note), `is_active`. On save → refresh the units store's dimension cache → route back to `?tab=dimensions`.

### 7.2 ÉTIQUETTES (`label_rules`) tab — priority ordering + live G5

`LabelRulesTab.vue` is **NOT a sortable `DataTable`** — priority IS the data, rows render in `priority ASC` order ("first substring match wins" only makes visual sense top-to-bottom). It's a custom ordered list reusing `DataTable`'s Tailwind shell (`rounded-xl border`). `listLabelRules()` returns rows already `ORDER BY priority ASC`.

| Col | Content |
|---|---|
| Ordre | the `priority` int (read-only) + a faint rank "#1, #2…" |
| Réordonner | ▲ / ▼ buttons (move up/down) + a drag handle (⠿) |
| Clé (sous-chaîne) | `key_substring` (accented, e.g. `capacité de production`) in mono |
| Dimension | links to dimension |
| Statut | `is_active` toggle |
| Actions | Modifier / Désactiver |

**Reorder UX (sparse-gap strategy, backend spec §4.3):** two equivalent inputs, both producing a `reorderLabelRules(order)` payload (full `[{id,priority}]` list):
- **▲/▼ buttons** swap a row with its neighbour; the moved row's new `priority` = midpoint of the two surrounding priorities, floored. If no integer gap remains (adjacent, e.g. 20 & 21) → request a full **rebalance**.
- **Drag-and-drop** via HTML5 `draggable` (no extra dep — the codebase has no DnD lib).

After any reorder the local list is **replaced with the server's returned `items`** (authoritative rebalanced priorities), so displayed `priority` values stay truthful.

**Live G5 shadowing feedback (G-2) — two layers:**
1. **Client-side pre-check (instant, advisory).** `composables/useG5Shadowing.ts` computes, on every reorder, all pairs where one accent-stripped `key_substring` is a substring of another **with a different dimension**, and flags any pair currently ordered generic-before-specific. Accent-strip **mirrors the backend**: `s.normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase()`. Flagged rows get an amber left-border + a ⚠ chip; hover shows: *« "capacité" (masse) masque "capacité de production" (débit massique) — placez la règle spécifique au-dessus. »* This catches the documented traps (`capacité`/`vitesse`/`ratio`/`charge`) **before** the operator commits the reorder. The `dureté`/`durée` near-miss is correctly NOT flagged (not a substring).
2. **Server-authoritative confirmation.** The client check is advisory only — the **backend `:reorder` route runs the real G5** and returns `InvalidArgument` if the new ordering violates the invariant. On 4xx the tab **reverts to the last-good order** and shows the raw G5 message under an amber banner « Ordre refusé (G5) : … ». The FE never claims an ordering is safe that the engine would reject; the client check is a fast warning, the server is the gate.

The same `useG5Shadowing` composable also feeds the unit form's **G5 row** — this tab's live check is the editing-time twin of that guard.

### 7.3 DÉSAMBIGUÏSATION (`disambiguation_rules`) tab — nm/t-min asymmetry

`DisambiguationTab.vue` — a plain `DataTable.vue` (tiny set: seed = `nm`, `t/min`):

| Header | Cell |
|---|---|
| Déclencheur | `trigger_unit` mono (`nm`, `t/min`) |
| Mots-clés | first 3 `keyword_list` chips + "+N" |
| Branche « match » | `match_dimension` (+ `match_pint_expr` mono if set) |
| Branche « défaut » | if `default_dimension` present → that dimension; if null → badge « héritée (lookup B) » |
| Type | derived badge: « Auto-portée » when `default_dimension` set (nm), « Surcharge » when null (t/min) |
| Actions | Modifier → `/admin/units/disambiguation/:id/edit` |

`DisambiguationFormView.vue` — single-column full-page editor modelling the §4.4 nullable-default semantics directly:
- **Déclencheur** (`trigger_unit`) — text, locked in edit.
- **Liste de mots-clés** (`keyword_list`) — `ChipInput`; helper « comparés sans accents, en OU (n'importe lequel suffit) ».
- **Branche « correspondance »** (always present): `match_dimension` `<select>` + optional `match_pint_expr` text (helper « laisser vide pour que pint analyse le jeton tel quel — cas `nm` ; renseigner `tonne / minute` pour `t/min` »).
- **Branche « défaut »** — a checkbox **« Cette règle fournit sa propre dimension par défaut »** that reveals/hides the default fields:
  - **Checked (the `nm` case):** reveals `default_dimension` `<select>` (+ optional `default_pint_expr`). Helper: *« Le jeton n'existe PAS dans le lookup B — il doit résoudre entièrement via cette règle. Sans mot-clé correspondant, on retombe sur cette dimension (ex. `nm` → couple). »*
  - **Unchecked (the `t/min` case):** `default_dimension`/`default_pint_expr` stay **null**. Helper: *« Le jeton possède une ligne B — la dimension par défaut vient du lookup B (`t/min` → `[frequency]`/`rpm`). Cette règle ne fournit qu'une surcharge quand un mot-clé correspond. »*

Persist `default_dimension: null` when unchecked, the dimension name when checked — exactly the backend spec §4.4 distinction (NULL default = "fall through to B" for t/min; non-NULL = "explicit default, token has no B row" for nm).

---

## 8. Screen: Proposal Queue — F5 + G-3

`src/components/units/ProposalsTab.vue` — `grid lg:grid-cols-[1fr_minmax(0,420px)]`. Left = ranked `DataTable.vue`; right = `MasterDetailPane` (opens on row-select; selection survives tab switches via the hub's `<KeepAlive>`).

**Left table** — `listProposals()`, default sort `occurrence_count` DESC (`sorting.value = [{ id:'occurrence_count', desc:true }]`) + a `state`/`failure_reason` `<select>` filter row:

| Header | Field |
|---|---|
| Jeton brut | `raw_unit` (+ `normalized_unit` sub-line) |
| Occurrences | `occurrence_count` (sortable, DESC default) |
| Échec | `failure_reason` badge (`no_dimension` / `pint_parse` / `to_failed`) |
| Indice dimension | `dimension_hint` or "—" |
| État | `state` badge (`PENDING`/`VALIDATING`/`ACTIVE`/`REJECTED`/`REJECTED_VALIDATION`/`SUPERSEDED`) |

**Right detail pane** — failing `sample_labels` as chips, `sample_value`, `failure_reason`, a **« Prochaine étape suggérée »** line, and two buttons: **« Préparer »** (primary) and **« Rejeter »** (`rejectProposal(id, reason)` — a reason textarea is required; the rejection writes `state=REJECTED` with the reason for the audit trail).

### 8.1 Approve-fork — "Préparer" routes to the right form (G-3)

The fork is driven by a **backend-supplied derived field** (§3.5 delta #2), NOT a fragile FE heuristic. The §8 diagnose step already re-runs `_get_dimension` + a throwaway-registry parse, so it knows whether the token prefix-collides with a builtin. It sets:

```
ProposalView.suggested_resolution : "unit" | "disambiguation"
  = "disambiguation"  when the diagnose parse hits a builtin prefix collision
                      (the nm class — needs a disambiguation_rules entry to pass G3)
  = "unit"            otherwise (a plain unknown unit)
```

The FE routes deterministically:

```ts
function prepare(p: ProposalView) {
  if (p.suggestedResolution === 'disambiguation')
    router.push({ name:'disambig-create', query:{ from_proposal: String(p.id) } })  // → DisambiguationFormView
  else
    router.push({ name:'unit-create',     query:{ from_proposal: String(p.id) } })  // → UnitFormView
}
```

The « Prochaine étape suggérée » line reflects the same value in French: *« Unité inconnue → préparer une nouvelle unité »* vs *« Collision de préfixe (type `nm`) → une règle de désambiguïsation est requise (G3) »*.

> **FE fallback if the backend delta #2 ships late:** if `suggested_resolution` is absent, default to the **unit** form (the common case) and show an info note in the detail pane that the operator can switch to a disambiguation rule manually. The deterministic backend field is the design target; the heuristic is a stopgap, not the contract.

### 8.2 Prefill

Both forms read `route.query.from_proposal` in `onMounted`, fetch the proposal, and seed `reactive(form)`:
- **Unit form prefill:** `token = normalized_unit`; `dimension = dimension_hint` (if present, else empty for the operator to pick); the **regression sample is pre-seeded** from `sample_value` + the first `sample_labels` entry + `data_type` (operator must still supply `expected_canonical_value`/`unit` — that's the human judgment G4 demands). On save → `createUnit(spec)`; the BFF, seeing `from_proposal`, routes to `ApproveProposal(id, spec)` instead of `RegisterUnit` so the proposal flips `PENDING → VALIDATING → ACTIVE/REJECTED_VALIDATION` (backend spec §7.1) and the same `validate_unit()` runs.
- **Disambiguation form prefill:** `trigger_unit = normalized_unit`; `keyword_list` seeded from any detected length/mass-flow keywords (or empty); the operator picks the **match branch** and decides the **default branch** (for an nm-class token they check « fournit sa propre dimension par défaut » and pick `couple`/torque). Save → `createDisambiguation` + the backend links the proposal.

After save the same propagation toast (§3.4) fires; the proposal disappears from the PENDING-filtered list on reload.

---

## 9. States & Conventions

- **Loading / empty / error** — match the existing pattern exactly: a per-view `loading` ref + `error` ref + (for write actions) an inline message banner like `ApiCatalogListView`'s `rescanMsg`/`error`. `DataTable` already renders an empty state (`emptyText`, default « Aucune donnée »). On `ApiError`: 401 → the global `onUnauthorized` handler (already wired in `client.ts`) redirects to login; 403 → « Accès réservé aux administrateurs » (shouldn't happen behind the router guard but defend anyway); 503 → « Service des unités indisponible, réessayez » (the profile/Unavailable case, §2.4); 400/409 on save → the garde-fou re-paint path (§6.4) for the unit form, or an inline banner elsewhere.
- **Dark mode** — every component uses the existing Tailwind dark-variant classes (`dark:bg-white/[0.03]`, `dark:text-white/90`, `dark:border-gray-800`) the same way `DataTable`/`ApiCatalogListView` do. No new color tokens; brand palette + Outfit font from `main.css`.
- **French-only** — all operator-facing copy is hardcoded French (no i18n framework — the app has none). The **sole exception** is the raw pint/engine `message` strings inside garde-fou rows and the dry-run error card (§6.3) — those stay raw English by design.
- **Accessibility basics** — buttons are real `<button>` with `type="button"`; the tab strip uses `role="tablist"`/`role="tab"` + `aria-selected`; the garde-fou checklist rows carry `aria-label` combining the French label + status word (« réussi »/« échoué »/« non applicable ») so the green/red icon isn't the only signal (color-independent status); the reorder ▲/▼ buttons have `aria-label` (« Monter »/« Descendre ») and drag handles are keyboard-skippable (the ▲/▼ buttons are the accessible equivalent of drag). Form fields have associated `<label>`s.

---

## 10. Phasing (aligned with backend phases)

| FE Phase | Scope | Backend dependency |
|---|---|---|
| **FE Phase A — read-only visualize** | The hub shell + sidebar entry + routing/guard; all five **read** views: Units table (with the "Colonnes" selector + localStorage), Dimensions table, Étiquettes ordered list (read-only, no reorder yet), Désambiguïsation table, Proposals table (read-only, no "Préparer"). `units.ts` read endpoints, `types/units.ts`, the `units` Pinia store. | Backend **P1 read RPCs** (`ListUnits/GetUnit/*Dimension list/*LabelRule list/*DisambiguationRule list`) + the BFF read routes. |
| **FE Phase B — write** | The two-pane `UnitFormView` + `GardeFousPanel` (Tester/Enregistrer) + `RegressionSampleEditor`; `DimensionFormView`; `DisambiguationFormView`; label-rule **reorder + live G5**; row actions (edit/disable); the propagation toast. `validateUnit`, `createUnit`/`updateUnit`/`disableUnit`, `reorderLabelRules`, dimension/disambiguation CRUD, `getRegistryStatus`. | Backend **P1 + the new `ValidateUnit` RPC** (§3) + `ReorderLabelRules` + `GetRegistryStatus` + the BFF write routes. **`ValidateUnit` is the hard gate for this phase** — without it the garde-fou panel can't render. |
| **FE Phase C — proposal queue** | The combined `ProposalsTab` (ranked table + master-detail) + the approve-fork routing (`suggested_resolution`) + reject-with-reason + prefill. `listProposals`/`rejectProposal`, the `from_proposal` prefill path. | Backend **P3** (auto-proposal) + the `suggested_resolution` field (§3.5 delta #2). |

**Deferred (YAGNI):** server-side pagination for the units table (client-side `DataTable` pagination is fine until the unit count is large — seed is ~200 units); bulk operations (multi-select disable); a push-based propagation indicator (the backend is poll-only by D5 — the toast is the only propagation UX); any i18n beyond hardcoded French; an undo for disable (re-enable is just an edit setting status back to ACTIVE — covered by the form, no dedicated UI).

---

## 11. Testing (Vitest component tests, matching the existing `*.spec.ts` style)

The repo already has `apiCatalog.spec.ts`, `services.spec.ts`, `ProtocolBadge.spec.ts` — same harness (`vitest`, `@vue/test-utils`, fetch mocked).

| Test | Asserts |
|---|---|
| **`GardeFousPanel.spec.ts` — each guard state** | Given a mocked `ValidationResult`, the panel renders exactly 6 rows in G1..G6 order; a `{ok:true,skipped:false}` row shows the green ✓ and the French label with no message; a `{ok:false}` row shows the red ✗ + the **raw message verbatim** in a `<pre>/<code>` block (assert the exact pint string appears, untranslated); a `{ok:true,skipped:true}` row is greyed with the « non applicable » note. |
| **`GardeFousPanel.spec.ts` — button gate** | `[Enregistrer & activer]` is disabled before any Tester; enabled only when the last result `overallOk===true`; re-disabled (`dirtySinceTest`) after a `spec` edit; stays disabled when `overallOk===false`. |
| **`GardeFousPanel.spec.ts` — dry-run card** | numeric → one line; numeric_range with `canonicalMax` → two lines (min/max); `bypassed:true` → the bypass badge; `ok:false` → the raw-error card. |
| **`useColumnVisibility.spec.ts` — persistence** | Applying preset `Compact` writes the expected key to `localStorage`; a fresh mount reads it back; Jeton + Actions are forced visible even if a stale persisted value hid them; unknown stored key version → falls back to `Riche`. |
| **`useG5Shadowing.spec.ts` — reorder feedback** | `capacité` before `capacité de production` (different dims) → flagged; same order reversed → not flagged; `dureté`/`durée` (not a substring) → not flagged; same-dimension substring pair → not flagged. |
| **`LabelRulesTab.spec.ts` — reorder payload + revert** | ▲/▼ produces a full `[{id,priority}]` payload with the midpoint priority; a mocked `:reorder` 400 reverts to last-good order and shows the « Ordre refusé (G5) » banner with the raw message. |
| **`ProposalsTab.spec.ts` — approve-fork routing** | `suggested_resolution:'unit'` → "Préparer" pushes `unit-create` with `from_proposal`; `'disambiguation'` → pushes `disambig-create`; absent field → defaults to `unit-create` (the fallback). |
| **`units.spec.ts` — API module** | `validateUnit` POSTs to `/api/v1/admin/units:validate` with `{spec}`; `reorderLabelRules` POSTs the order array to `:reorder`; all calls go through `api<T>()` (cookie auth, no bearer header set client-side). |

Two integration-ish notes (NOT run locally — flagged for CI/manual): the 200-on-validation-failure mapping (the panel must not throw on `overallOk:false`) and the 400/409-after-green save path. Both are exercised with mocked fetch in the component tests above rather than a live backend.

---

## 12. Risks & Open Questions

1. **[UPSTREAM, blocking end-to-end] Registry state vs `replicas: 5`.** The units service runs 5 replicas; the BFF dials the compose DNS name (round-robin). If the registry RPCs are backed by per-replica in-memory state rather than the shared `catalog_db`, reads/writes are inconsistent and the « propagation ≤30s » toast is meaningless. The backend spec's MySQL-backed model resolves this — but the FE design **assumes** it. If the units service can't guarantee shared state, the registry RPCs must run `replicas: 1`. The BFF cannot paper over this.
2. **[UPSTREAM] Three things must be built before the BFF works:** (a) `ValidateUnit` + Phase-1 RPCs in `graph_normalization.proto` (none of the CRUD/validate RPCs exist today — the service only has `NormalizeQuantity`/`NormalizeRange`), (b) the Python servicer backed by shared state, (c) a **server-side `ADMIN_KEY` interceptor** on the units gRPC server (today it `add_insecure_port` with no auth — the BFF gate is the *only* gate until that interceptor lands).
3. **[CORRECTNESS] Don't clone the `actorEmail` empty-actor bug** (§2.2) — units `created_by` must be the real operator email via a fixed context helper.
4. **[OPEN, deferred to user] BFF JSON casing** — proto3 camelCase (recommended) vs snake_case. The FE `types/units.ts` and `units.ts` must align to whatever the BFF emits; resolve at integration time (§3.5 delta #4).
5. **[OPEN] Stale-Tester window.** A green "Tester" can still 400/409 on save if the live snapshot drifted (another admin's write between Tester and Enregistrer). Handled by the re-paint path (§6.4), but worth an operator-facing note in the panel (« La validation reflète l'état au moment du test »). Acceptable; flagged for visibility.
6. **[OPEN] Optimistic concurrency on edit.** `UpdateUnit` has no version/etag in the current contract — two admins editing the same unit last-write-wins. Low-frequency admin tool, so likely acceptable for P1, but if the backend adds an `If-Match`/`registry_version` precondition the form should send it. Out of scope for this spec; noted.
7. **[MINOR] `<KeepAlive>` memory.** Keeping all five tabs alive holds their data refs in memory; fine for an admin tool with bounded data, but if the units list grows to thousands, reconsider `<KeepAlive>` `:include` to keep only the active + recently-visited tabs.
8. **[MINOR] Drag-and-drop a11y.** HTML5 native drag is not keyboard-accessible; the ▲/▼ buttons are the accessible path (§9). If a richer DnD is ever wanted, it adds a dependency the codebase currently avoids — keep the no-dep native approach unless flagged.

---

## 13. Adversarial Review Fixes (applied — authoritative over conflicting text above)

Folded in from the 3-lens critique (coherence / completeness / safety). Blockers + majors are corrected inline above; this is the consolidated ledger.

**Blockers (fixed):**
- **Invalid Go route** `proposals/{id}:validate` → removed; a wildcard segment can't take a `:suffix` (panics). Prefill validate reuses `units:validate` (§2.2).
- **Missing contract** for Dimensions/Étiquettes/Désambiguïsation (3 of 5 tabs) → the full CRUD + `ReorderLabelRules` + `GetProposal` + `ValidateUnit` RPCs are now specified in **backend Addendum B.1** (no longer "phantom" RPCs).
- **Auth-gating hole** → all units BFF routes (incl. reads) mount under `RequireAdmin`, diverging from the catalog clone's `requireAuth`; backend tests required (§2.2 review-fix note).

**Majors (fixed):**
- Invented RPC names `ResolveProposal`/single-getter → `RejectProposal` + `ApproveProposal` + `GetProposal`; explicit `/approve` route; `from_proposal` threading specified (§2.2, §8.2).
- §3 relabeled from "small addendum" to a backend **engine change** + new RPCs (backend Addendum B.2).
- Propagation "toast" re-scoped to the existing inline-banner pattern — no new toast infra (§3.4).
- Approve-fork: `ApproveProposal` takes `UnitSpec` (unit fork only); the disambiguation fork resolves via `CreateDisambiguationRule(+from_proposal_id → SUPERSEDED)` (backend Addendum B.4, §2.2).
- Units gRPC has **no** auth interceptor today → elevated to a hard Phase-B prerequisite (backend Addendum B.3); `ValidateUnit` is read-classified (no bearer) but still BFF cookie+admin gated, and must keep the §5.3 circular-def timeout bound (DoS).
- `actorEmail`/`created_by` fix made mandatory + tested; same fix to api-catalog in a separate commit (§2.2).

**Minors (fixed/noted):**
- Source badge enum `auto` → `auto_proposal` (3 values) (§5.1).
- Go **1.24** (not 1.25) — matches `account-service-backend` CLAUDE.md/Dockerfile (header).
- **`DataTable.vue` needs two additive props**, both listed as modifications: `columnVisibility` v-model (§5.2) **and** an `initialSorting` prop (proposal default-sort §8); the empty-state `colspan` must use `table.getVisibleLeafColumns().length` (tracks visibility), not `columns.length`.
- **Units filters are client-side** over the loaded list (matching the *actual* `ApiCatalogListView` pattern + the client-side-pagination deferral §10) — not a server round-trip per filter; the `listUnits({status,dimension})` server-filter claim is dropped (§5.3).
- **`Canonique` column** needs a client-side join to the `units` store's `dimensionByName` (`UnitResponse.spec` carries only the dimension *name* + `canonical_override`); shows a placeholder until the dimension cache loads (§5.1).
- Non-admin: the **SPA router redirects to `/me`** before any request; **403 is the BFF response** if reached directly (§1.2/§9 — the two layers were conflated).
- Sidebar highlight holds on the hub (`/admin/units`) but **not** on the separate full-page form routes (exact-match `isActive`) — consistent with existing `/admin/api/new` behavior (§4.1).
- **CORS/CSRF note:** browser → same-origin BFF only; the BFF→units gRPC leg is server-side; `ADMIN_KEY` never reaches the browser (no new CORS surface). **Open risk:** admin mutations ride a `SameSite=Lax` + `SECURE_COOKIE=false`(dev) cookie with no CSRF token → recommend `SameSite=Strict` or a CSRF token on mutating routes, and `SECURE_COOKIE=true` in any internet-reachable deploy (§12).
- `LabelRulesTab` (non-`DataTable`) + form edit-mode record-load need their own loading/empty/error copy (§9).

---

*End of spec. Companion backend spec: `docs/superpowers/specs/2026-06-01-dynamic-unit-normalization-design.md` (see its **Addendum B** for the contract delta this UI requires). The two specs are now mutually consistent.*
