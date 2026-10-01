# Catalog-driven APITokenVerifier (api-gateway-go)

**Status:** Approved (design)
**Owner:** sandrianirinaharivelo
**Date:** 2026-05-28
**Branch:** `features/poc`
**Related services:** `api-gateway-go`, `api-catalog-service`, `account-service-backend`, `account-service-frontend`

## 1. Problem

`api-gateway-go/internal/auth/api_token.go` contains a TODO short-circuit (lines 42-51) that bypasses authentication for every proxied service — only `graphdlq-service` falls through to the real auth path, and even that path is unreachable because both branches `return` before it. Below the short-circuit lies a complete Bearer-JWT + Redis + DB verification flow that is currently dead code.

In parallel, `internal/config/service_map.go:BuildExcludedRoutes` hardcodes a single per-service exception (`graphdlq-service: /dlq/queues`) that should also be configurable without redeploying the gateway.

`api-catalog-service` already exists as the source of truth for service registration (consumed by the gateway's `catalog.Refresher` for routing). We want to extend that same source to drive auth decisions, with CRUD surfaced by `account-service-backend` and an admin UI in `account-service-frontend`.

## 2. Goals

1. Remove the hardcoded auth bypass in `api_token.go`.
2. Remove `config.BuildExcludedRoutes`.
3. Make per-service auth policy and per-endpoint overrides editable in the admin UI.
4. Preserve current production behavior at cutover (all services start as PUBLIC; `graphdlq-service` keeps `/dlq/queues` as a public path).
5. No new RPC hop on the hot path — auth decisions read an in-memory snapshot.

## 3. Non-goals

- Streaming invalidation from the catalog to the gateway (>60 s staleness acceptable for v1).
- Glob / regex path matching (exact match only).
- Session-cookie policy (the `/docs` flow stays handled by `DocsAuthMiddleware`).
- Re-introducing CORS, IP allowlists, or any policy axis other than the existing three (public / bearer / admin-key).

## 4. Decisions (locked during brainstorming)

| # | Decision | Rationale |
|---|----------|-----------|
| Q1 | Both per-service policy AND per-endpoint exclusions are catalog-driven | Replaces both the api_token.go bypass and BuildExcludedRoutes |
| Q2 | 3 modes: `PUBLIC` / `BEARER` / `ADMIN_KEY` | Covers every existing auth surface in the proxied path |
| Q3 | Schema: Service.auth_policy as default, Endpoint.auth_policy as override | Replaces both hardcoded mechanisms cleanly |
| Q4 | Delivery: extend `catalog.Refresher` snapshot | Reuses existing 60s polling; no new RPC hop per request |
| Q5 | Fail-open: default = `PUBLIC` when catalog unavailable | Migration is non-breaking; preserves current behavior |
| Q6 | Path match: exact string match only | Smallest blast radius; matches today's `BuildExcludedRoutes` semantics |
| Q7 | UI: service form gets dropdown + `public_paths` list; endpoint table gets inline select | Minimal new screens; reuses existing CRUD views |
| Q8 | Migration: seed init-db + single-PR cutover deleting hardcoded code | Atomic switch; rollback = single revert commit |
| App | Approach A — extend existing RPCs (no new RPC) | Smallest proto surface; `has_endpoint_overrides` hint avoids N+1 |

## 5. Architecture

```
┌───────────────────────────┐  HTTP PUT /api/v1/admin/api/{id}
│ account-service-frontend  │  HTTP PUT /api/v1/admin/api/{id}/endpoints/{ep}
│ ApiCatalogFormView        │
│ ApiCatalogDetailView      │
└──────────────┬────────────┘
               ▼
┌───────────────────────────┐  gRPC UpdateService / UpdateEndpoint
│ account-service-backend   │
│ api_catalog_handlers.go   │
└──────────────┬────────────┘
               ▼
┌───────────────────────────┐  source of truth
│ api-catalog-service       │
│ MySQL catalog_db          │
└──────────────┬────────────┘
               │ gRPC ListServices + ListEndpoints (refresher loop, 60s)
               ▼
┌───────────────────────────┐  per-request hot path reads snapshot only
│ api-gateway-go            │
│ catalog.Refresher         │  → AuthSnapshot
│ proxy.APITokenVerifier    │
└───────────────────────────┘
```

**Source of truth:** `api-catalog-service` MySQL.
**Hot path:** verifier reads an in-memory snapshot; never blocks on RPC.
**Write path:** admin UI → account-service-backend HTTP → catalog gRPC.

## 6. Components

### 6.1 protos/grpc_stubs/api_catalog.proto

```proto
enum AuthPolicy {
  AUTH_POLICY_UNSPECIFIED = 0;
  PUBLIC                  = 1;  // no auth (current default)
  BEARER                  = 2;  // Bearer JWT required
  ADMIN_KEY               = 3;  // X-Admin-Key header required
}

message Service {
  // existing fields 1-16 unchanged
  AuthPolicy auth_policy        = 17;
  repeated string public_paths  = 18;  // exact paths bypassing service default
  bool   has_endpoint_overrides = 19;  // server-computed; refresher hint
}

message Endpoint {
  // existing fields 1-9 unchanged
  optional AuthPolicy auth_policy = 10;  // overrides Service.auth_policy
}

message CreateServiceRequest {
  // existing fields 1-9 unchanged
  AuthPolicy auth_policy        = 10;
  repeated string public_paths  = 11;
}

message UpdateServiceRequest {
  // existing fields 1-5 unchanged
  optional AuthPolicy auth_policy = 6;
  repeated string public_paths    = 7;  // replace-all semantics
}

message UpdateEndpointRequest {
  string id                       = 1;
  optional AuthPolicy auth_policy = 2;
}

service ApiCatalog {
  // existing RPCs unchanged
  rpc UpdateEndpoint(UpdateEndpointRequest) returns (Endpoint);
}
```

### 6.2 api-catalog-service

- DB migration (init-db):
  - `ALTER TABLE services ADD COLUMN auth_policy TINYINT NOT NULL DEFAULT 1;`
  - `ALTER TABLE services ADD COLUMN public_paths JSON NULL;`
  - `ALTER TABLE endpoints ADD COLUMN auth_policy TINYINT NULL;`
- Seed migration:
  - Set every existing row's `auth_policy = 1 (PUBLIC)`.
  - `UPDATE services SET public_paths = JSON_ARRAY('/dlq/queues') WHERE name = 'graphdlq-service';`
- `ListServices` computes `has_endpoint_overrides` via `EXISTS (SELECT 1 FROM endpoints WHERE service_id = services.id AND auth_policy IS NOT NULL)`.
- `UpdateEndpoint` validates `auth_policy ∈ {1,2,3}` or clears (NULL).
- All policy mutations write an audit row (reuse existing audit hook).

### 6.3 account-service-backend (`internal/api/api_catalog_*.go`)

- `createReq` / `updateReq` gain `AuthPolicy string` (`"public"|"bearer"|"admin-key"`) and `PublicPaths []string`.
- Helpers `authPolicyFromString` / `authPolicyToString` mirror existing `statusFromString` style.
- Validation:
  - Whitelist `auth_policy ∈ {"public","bearer","admin-key"}`; reject others with 400 `{"error":"invalid_auth_policy"}`.
  - Each `public_paths` entry must start with `/` and contain no `*` or `?`; reject with 400 `{"error":"invalid_public_path"}`.
  - Normalization: trim trailing `/` from each entry before storage (so `/foo/` → `/foo`). Empty after trim is rejected. Storage canonical form is leading-slash + no trailing-slash + no query/fragment.
- New handler `PUT /api/v1/admin/api/{id}/endpoints/{endpoint_id}` → `UpdateEndpoint` gRPC.
- `CatalogClientIface` gains `UpdateEndpoint(ctx, req)`.
- Audit actions: `catalog.update` already covers service-level edits; add `catalog.update_endpoint` for endpoint overrides.

### 6.4 account-service-frontend

- `types/apiCatalog.ts`:
  ```ts
  export type AuthPolicy = 'public' | 'bearer' | 'admin-key'
  // ApiCatalogService: + authPolicy?: AuthPolicy; publicPaths?: string[]; hasEndpointOverrides?: boolean
  // ApiCatalogEndpoint: + authPolicy?: AuthPolicy
  // CreateApiRequest / UpdateApiRequest: + authPolicy?: AuthPolicy; publicPaths?: string[]
  ```
- `api/apiCatalog.ts`: add
  ```ts
  export function updateEndpoint(serviceId: string, endpointId: string,
                                  payload: { authPolicy?: AuthPolicy | null })
  ```
- `views/ApiCatalogFormView.vue`:
  - `<select>` bound to `form.authPolicy` (options: public / bearer / admin-key).
  - Tag-list editor for `form.publicPaths` (string array, comma- or chip-input).
- `components/api-catalog/EndpointTable.vue`:
  - Per-row `<select>` showing `'(inherit)' | 'public' | 'bearer' | 'admin-key'`.
  - On change: optimistic update + call `updateEndpoint`; on failure revert + toast.
- Backward compatibility: when backend response lacks `authPolicy`, treat as `'public'`.

### 6.5 api-gateway-go

New file `internal/auth/policy_snapshot.go`:

```go
type AuthPolicy int

const (
    PolicyPublic AuthPolicy = iota
    PolicyBearer
    PolicyAdminKey
)

type ServicePolicy struct {
    Default      AuthPolicy
    PublicPaths  map[string]struct{}     // exact match, canonical form: "/dlq/queues"
    EndpointAuth map[string]AuthPolicy   // key canonical form: "METHOD /dlq/queues"
}

// Normalization (gateway side, applied to every lookup):
//   path := "/" + strings.TrimRight(strings.Trim(c.Param("path"), "/"), "/")
// Catalog returns canonical paths already (validated by backend §6.3).

type AuthSnapshot map[string]ServicePolicy  // key = service name including "-service"
```

`internal/catalog/refresher.go`:
- Extend `Refresher` with `currentAuth AuthSnapshot` field (guarded by same `mu`).
- `Bootstrap` / `Run` build both routes and AuthSnapshot in one pass.
- Call `ListEndpoints(service_id, ANY)` only for services where `has_endpoint_overrides == true`.
- `Snapshot()` returns `(routes map[string]string, auth AuthSnapshot, source string)`.

`internal/auth/api_token.go`:
- `NewAPITokenVerifier(j, g, c, getAuth func() AuthSnapshot)` — replace `excludedRoutes` arg with `getAuth`.
- **Remove** the TODO short-circuit (lines 42-51).
- Decision tree inside `Middleware`:
  ```go
  snap := getAuth()
  sp, known := snap[service]
  policy := PolicyPublic
  if known {
      key := c.Request.Method + " /" + path
      if p, ok := sp.EndpointAuth[key]; ok {
          policy = p
      } else if _, ok := sp.PublicPaths["/"+path]; ok {
          policy = PolicyPublic
      } else {
          policy = sp.Default
      }
  }
  switch policy {
  case PolicyPublic:    c.Set("token_payload", gin.H{"sub": service, "is_excluded": true}); c.Next()
  case PolicyBearer:    // existing Bearer flow (revive lines 62-97)
  case PolicyAdminKey:  // header X-Admin-Key == cfg.GatewayAdminKey ? next : 403
  }
  ```
- Unknown service is logged at WARN once per `(service, hour)` to avoid log spam (simple in-memory `map[string]time.Time`, guarded by sync.Mutex).

`internal/config/service_map.go`:
- **Remove** `BuildExcludedRoutes` entirely.
- Update `main.go` wiring to drop the argument.

## 7. Data flow

### 7.1 Gateway boot (cold start)

1. `cfg.UseCatalog=true` → dial catalog gRPC.
2. `Refresher.Bootstrap`:
   - `ListServices(limit=1000)` builds routes + `AuthSnapshot[name]={Default, PublicPaths}`.
   - For each service with `has_endpoint_overrides=true`, call `ListEndpoints(service_id)` and fill `EndpointAuth["METHOD /path"]`.
   - On dial/error or empty response → env-fallback routes + **empty** `AuthSnapshot` (everything resolves to `PolicyPublic`).
3. Wire `getServices`, `getAuthSnapshot` closures into handlers.

### 7.2 Refresh (every 60 s)

Same algorithm as bootstrap. On failure → keep last good snapshot; log WARN. Atomic swap under RWMutex; never partial.

### 7.3 Hot path (proxied request)

```
client → gin /:service/*path
  ↓
wsHandler (WS bypasses auth — unchanged)
  ↓ HTTP
APITokenVerifier.Middleware
  ↓ decision tree (§6.5)
  ├─ PolicyPublic    → next (no token check)
  ├─ PolicyBearer    → existing JWT + Redis + DB flow
  └─ PolicyAdminKey  → X-Admin-Key match or 403
  ↓
httpHandler → downstream
```

### 7.4 Admin edit

```
ApiCatalogFormView (auth_policy changed)
  → PUT /api/v1/admin/api/{id} { authPolicy:"bearer", publicPaths:[…] }
  → account-service-backend updateHandler
  → gRPC UpdateService(id, auth_policy=BEARER, public_paths=[…])
  → api-catalog-service: UPDATE services … + audit row
[next ≤60 s] api-gateway-go Refresher tick picks up change
```

### 7.5 Endpoint override edit

```
EndpointTable inline select changed
  → PUT /api/v1/admin/api/{service_id}/endpoints/{endpoint_id} { authPolicy:"bearer" }
  → UpdateEndpoint gRPC
  → UPDATE endpoints … + recompute has_endpoint_overrides for parent service
[next ≤60 s] gateway snapshot reflects override
```

### 7.6 Staleness window

≤ refresh interval (60 s default). Acceptable for v1. Future enhancement (out of scope): catalog publishes invalidation events over gRPC stream.

## 8. Error handling

### Gateway

| Case | Behavior |
|------|----------|
| Catalog dial fails at bootstrap | Env-fallback routes, empty `AuthSnapshot` → all services treated as `PolicyPublic`. Log `WARN auth-snapshot empty; gateway running fail-open`. |
| Catalog refresh fails after bootstrap | Keep last good snapshot. Log `WARN catalog refresh failed; keeping last map+auth`. |
| `ListEndpoints` fails for one service mid-refresh | Preserve that service's previous `EndpointAuth`. Per-service error logged. |
| Service name in request not in snapshot | `policy = PolicyPublic`. Log once per `(service, hour)` at WARN. |
| `auth_policy = UNSPECIFIED` from server | Coerce to `PolicyPublic`. |
| Bearer token missing on `PolicyBearer` service | 401 `WWW-Authenticate: Bearer` + `{"detail":"Access token manquant ou invalide."}`. |
| Bearer token expired | 401 `{"detail":"Access token has expired. Please refresh."}`. |
| Bearer token revoked / not in cache+DB | 401 `{"detail":"Access token has been revoked or expired."}`. |
| Admin-key missing/wrong on `PolicyAdminKey` service | 403 `{"detail":"Invalid or missing admin key."}`. |
| `GATEWAY_ADMIN_KEY` env unset but policy = AdminKey | 403 for that service. Startup log if `len(adminKey)==0`. |

### account-service-backend

| Case | Behavior |
|------|----------|
| Invalid `authPolicy` string | 400 `{"error":"invalid_auth_policy"}`. |
| `public_paths` entry without leading `/` or containing `*`/`?` | 400 `{"error":"invalid_public_path"}`. |
| Empty `publicPaths` array | Clear list (replace-all). Audited. |
| Catalog `NotFound` on UpdateEndpoint | 404 via existing `writeGRPCError`. |

### api-catalog-service

| Case | Behavior |
|------|----------|
| Bad enum value in DB | Server returns `UNSPECIFIED`; clients coerce to PUBLIC. Log WARN. |
| `public_paths` JSON corrupt | Treat as empty; log WARN; row still listable so admins can fix. |
| Parent service deleted | `ON DELETE CASCADE` on endpoints clears overrides. |
| Concurrent edits | Last-write-wins. Audit log captures both. |

### Frontend

| Case | Behavior |
|------|----------|
| `authPolicy` missing in server response | Default to `'public'`; dropdown shows Public. |
| User clears `public_paths` field | Strip blanks; no submit when list unchanged. |
| Endpoint override save fails | Toast `"Failed to update endpoint policy: <error>"`; revert select. |

### Migration safety

- All catalog DB changes in one transaction per service.
- Rollback path: revert the single migration commit + restore `BuildExcludedRoutes` and the TODO short-circuit.
- Deploy order: (1) proto + catalog deploy → (2) seed migration runs → (3) gateway deploy with new verifier.

## 9. Testing strategy

### protos / api-catalog-service

- Repository tests: `AuthPolicy` + `PublicPaths` persistence; `has_endpoint_overrides` computed correctly for 0/1/N override rows.
- gRPC integration (bufconn): round-trip `CreateService` with policy, `UpdateEndpoint`, `ListEndpoints` reflects override.
- Migration test: empty `catalog_db` → run init-db → assert seed values.

### account-service-backend

- `createReq` / `updateReq` JSON parsing handles `"authPolicy":"bearer"`, rejects `"authPolicy":"banana"` → 400.
- Fake `CatalogClientIface`: `UpdateService` passes through `publicPaths`; `UpdateEndpoint` returns 404 on gRPC `NotFound`, 200 on success.
- Audit row written on `catalog.update_endpoint`.

### account-service-frontend

- `ApiCatalogFormView`: dropdown + public_paths editor binds; submits payload with both fields.
- `EndpointTable`: inline select emits update event; failed update reverts.
- `api/apiCatalog.spec.ts`: `updateEndpoint` URL/method/body shape.
- Type test: `ApiCatalogService.authPolicy` typed `AuthPolicy | undefined`.

### api-gateway-go

- `policy_snapshot_test.go`: decision-tree table covering empty snapshot, public default, bearer default, public_paths bypass, endpoint override winning over default, unknown service.
- `APITokenVerifier.Middleware` test matrix: 401 on missing Bearer + `PolicyBearer`, 403 on bad admin-key + `PolicyAdminKey`, allow on `public_paths` bypass.
- `catalog/refresher_test.go`: fake catalog returning `has_endpoint_overrides=true` for 1/3 services triggers exactly 1 `ListEndpoints` call.
- Integration (`httptest` + gomock catalog): edit endpoint policy → wait for refresh tick → next request enforced.
- Regression: refresher returns empty snapshot → verifier still serves (fail-open).

### Manual smoke (post-deploy)

1. `GET /graphdlq-service/dlq/queues` with no auth → 200 (public_paths bypass).
2. After `graphdlq-service.auth_policy=BEARER` set in UI: same route still 200 (public_paths wins); any other route → 401.
3. Edit policy in frontend → wait ≤60 s → behavior changes.

### Coverage targets

- proto/catalog: ≥85 % on new code.
- backend: ≥80 % on new handlers + parser.
- gateway: 100 % on decision tree (security-critical).

## 10. Rollout order

1. Merge proto + catalog-service migration. Deploy catalog. Seed migration runs idempotently on boot.
2. Merge account-service-backend changes. Deploy. Verify admin UI dropdown is round-tripping via API tests.
3. Merge account-service-frontend changes. Deploy.
4. Merge api-gateway-go changes (removes TODO short-circuit + `BuildExcludedRoutes`). Deploy.
5. Run manual smoke checks.
6. Flip `graphdlq-service.auth_policy=BEARER` in UI; verify enforcement after refresh tick.

## 11. Open questions

None. Brainstorming Q1–Q8 + approach choice all locked.

## 12. References

- `apps-microservices/api-gateway-go/CLAUDE.md`
- `apps-microservices/api-gateway-go/internal/auth/api_token.go` (lines 42-51 — TODO short-circuit)
- `apps-microservices/api-gateway-go/internal/config/service_map.go` — `BuildExcludedRoutes`
- `apps-microservices/api-catalog-service/CLAUDE.md`
- `apps-microservices/account-service-backend/internal/api/api_catalog_handlers.go`
- `apps-microservices/account-service-frontend/src/views/ApiCatalogFormView.vue`
- `apps-microservices/account-service-frontend/src/views/ApiCatalogDetailView.vue`
- `protos/grpc_stubs/api_catalog.proto`
- Prior spec: `docs/superpowers/specs/2026-05-08-api-catalog-design.md`
- Prior spec: `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`
