# API Catalog — Centralized API/Endpoint Registry

**Status:** Design approved (brainstorming session 2026-05-08).
**Date:** 2026-05-08
**Owner:** sandrianirinaharivelo@hellopro.fr
**Base branch:** `origin/features/poc` (implementation branch will be cut from this, not from the current `features/mcp-oauth2-user`).
**Related specs:** `2026-05-04-account-service-sso-design.md`, `2026-05-07-api-gateway-go-port-design.md`.

## Context

The platform exposes 90+ microservices behind `api-gateway-go`. Today the gateway derives its routing table from `SERVICE_*` environment variables at boot. There is no central record of which APIs exist, what endpoints they expose, who owns them, or which protocols (REST / WebSocket / gRPC) they support. Admins cannot see "what is the platform exposing right now" without grep'ing compose files and probing `/openapi.json` by hand.

This spec introduces a new microservice — `api-catalog-service` — that stores a registry of services + endpoints, scans them periodically, and exposes the catalog over gRPC. `account-service-{backend,frontend}` gains a new "API" admin nav that surfaces this catalog with full CRUD on metadata. `api-gateway-go` consumes the catalog as its primary routing source and falls back to its own `SERVICE_*` env when the catalog is unreachable or empty (zero-risk degradation).

The mcp-protocol authorization endpoints, the gateway's per-service downstream timeouts, the gateway's excluded-services list, mTLS between services, and rate limiting are explicitly out of scope.

## Decisions

| # | Topic | Choice |
|---|---|---|
| 1 | API granularity | Service-level rows + child endpoint rows. Endpoints derived from scan. |
| 2 | Source of truth | Hybrid — DB + auto-discovery. DB persists, scanner reconciles. |
| 3 | Discovery sources | Gateway `SERVICE_*` env (seed targets, mirrored to catalog at deploy) + network probing per service. |
| 4 | Ownership | New `api-catalog-service`. `account-service-backend` is the admin UI's broker (HTTP → gRPC). |
| 5 | Backend ↔ Catalog transport | gRPC (`api_catalog.proto` in `protos/grpc_stubs/`). |
| 6 | Catalog ↔ Gateway env sync | Same `SERVICE_*` env vars provided to catalog at deploy time. No runtime call from catalog to gateway. |
| 7 | Protocols MVP | REST + WebSocket + gRPC. |
| 8 | WebSocket discovery | Service convention `GET /api-info` (optional). Absence ≠ failure. |
| 9 | Endpoint cache | Persisted in catalog DB. Manual `Rescan` RPC + cron refreshes. |
| 10 | CRUD operations | Create, edit metadata, delete, trigger rescan. |
| 11 | Scan schedule | Cron (default 15 min) + manual rescan RPC. |
| 12 | Authorization | Read = any authenticated user. Write/Rescan = admin. |
| 13 | Catalog implementation language | Go 1.24 (matches account/gateway stack). |
| 14 | Gateway routing source | Catalog gRPC primary; `SERVICE_*` env fallback when catalog unreachable or empty (behind `GATEWAY_USE_CATALOG` flag). |
| 15 | DB instance | Reuse `gateway-mysql` instance. Separate logical DB `catalog_db`. |
| 16 | Form pages | Create/edit are full-page routes (`/admin/api/new`, `/admin/api/:id/edit`), mirroring `ServiceFormView.vue` pattern — no modal. |

## Architecture

```
account-frontend (Vue) ──HTTP──> account-backend (Go) ──gRPC──> api-catalog-service (NEW, Go)
                                                                     │
                                                                     ├──HTTP probe──> {service}/openapi.json
                                                                     ├──HTTP probe──> {service}/api-info
                                                                     ├──gRPC reflect> {service}:port
                                                                     └──MySQL──> catalog_db (services + endpoints)

                  ┌──gRPC ListServices──> api-gateway-go (consumer; env fallback)
api-catalog ──────┤
                  └──gRPC CRUD/Scan ──> account-backend
```

### Bootstrap sequence

1. Catalog boots → reads `SERVICE_*` env → seeds scan targets → first scan populates DB.
2. Gateway boots → gRPC `Catalog.ListServices` → builds route map.
3. If gRPC fails or returns empty → gateway falls back to its own `SERVICE_*` env (current behavior preserved).
4. Gateway re-syncs every 60 s by ticker (configurable).

### Steady-state read flow (UI list)

1. Frontend `GET /admin/api` → account-backend.
2. Backend `Catalog.ListServices` over gRPC → catalog returns DB rows.
3. Backend translates to JSON, returns to frontend.

### Steady-state scan flow

1. Cron tick (15 min) or admin clicks "Rescan all" → `Catalog.RescanAll` RPC.
2. Catalog enumerates targets: `SERVICE_*` env ∪ DB rows where `source='manual'`.
3. For each target (bounded concurrency = 16):
   - REST: `GET /openapi.json` → endpoints.
   - `GET /api-info` → optional WS list + gRPC address.
   - If gRPC enabled: server reflection → RPC list.
4. Per-service transaction: upsert service row, replace endpoint rows.
5. Stale env-sourced services no longer in env → marked `status='down'` (not deleted).
6. `RescanReport` returned with counts + per-service errors.

## Components

### `api-catalog-service` (new)

**Stack:** Go 1.24, `google.golang.org/grpc`, `gorm.io/gorm` + `gorm.io/driver/mysql`, `golang.org/x/sync/errgroup`, `google.golang.org/grpc/reflection` (server) + grpcreflect client.

**Layout:**

```
apps-microservices/api-catalog-service/
├── CLAUDE.md
├── Dockerfile                          # multi-stage golang:1.24-alpine -> alpine:3.20
├── go.mod
├── go.sum
├── cmd/
│   └── server/
│       └── main.go
├── internal/
│   ├── config/
│   │   └── config.go
│   ├── db/
│   │   ├── mysql.go
│   │   └── models.go
│   ├── repository/
│   │   ├── service_repo.go
│   │   ├── endpoint_repo.go
│   │   └── *_test.go
│   ├── scanner/
│   │   ├── scanner.go
│   │   ├── env_source.go
│   │   ├── probe_rest.go
│   │   ├── probe_ws.go
│   │   ├── probe_grpc.go
│   │   ├── cron.go
│   │   └── *_test.go
│   ├── grpcserver/
│   │   ├── server.go
│   │   ├── interceptor_auth.go
│   │   ├── mapper.go
│   │   └── *_test.go
│   └── health/
│       └── health.go
└── init-db/
    └── 01_schema.sql
```

**Configuration env vars:**

| Var | Default | Purpose |
|---|---|---|
| `MYSQL_HOST` | `gateway-mysql` | Shared DB host |
| `MYSQL_PORT` | `3306` | |
| `MYSQL_USER` | `catalog_user` | |
| `MYSQL_PASS` | (required) | |
| `MYSQL_DB`   | `catalog_db` | Separate logical DB |
| `GRPC_PORT`  | `9100` | gRPC listen port |
| `HEALTH_PORT`| `9101` | HTTP `/healthz` |
| `ADMIN_KEY`  | (required) | Bearer for write/rescan RPCs |
| `SCAN_INTERVAL` | `15m` | Cron tick |
| `SCAN_CONCURRENCY` | `16` | Max parallel probes |
| `PROBE_TIMEOUT` | `3s` | Per-probe HTTP timeout |
| `SERVICE_*` | (mirrored from gateway compose) | Seed targets |

### `account-service-backend` changes

New files in `internal/api/`:

- `api_catalog_handlers.go` — HTTP routes that call gRPC client.
- `api_catalog_handlers_test.go` — table-driven tests using mock catalog client interface.
- `api_catalog_client.go` — gRPC client wrapper (dial, deadline, retry, outbound auth metadata for write RPCs).
- `api_catalog_client_test.go` — bufconn-based tests.

Routes (auth via existing `middleware.RequireAuth`):

| Method | Path | minRole | Calls (gRPC) |
|---|---|---|---|
| GET | `/admin/api` | user | `ListServices` |
| GET | `/admin/api/:id` | user | `GetService` + `ListEndpoints` |
| POST | `/admin/api` | admin | `CreateService` |
| PUT | `/admin/api/:id` | admin | `UpdateService` |
| DELETE | `/admin/api/:id` | admin | `DeleteService` |
| POST | `/admin/api/rescan` | admin | `RescanAll` |
| POST | `/admin/api/:id/rescan` | admin | `RescanService` |

Audit log: existing `audit_repo.go` records Create/Update/Delete/Rescan with `actor_email`, target id, action.

New env vars on account-backend: `API_CATALOG_GRPC=api-catalog-service:9100`, `CATALOG_ADMIN_KEY=...`.

### `account-service-frontend` changes

New files:

```
src/
├── api/
│   └── apiCatalog.ts
├── types/
│   └── apiCatalog.ts
├── views/
│   ├── ApiCatalogListView.vue
│   ├── ApiCatalogDetailView.vue
│   └── ApiCatalogFormView.vue
└── components/
    └── api-catalog/
        ├── ProtocolBadge.vue
        ├── EndpointTable.vue
        └── ScanStatusBadge.vue
```

Router additions in `src/router/index.ts`:

```ts
{ path: '/admin/api',          name: 'api-list',   component: () => import('@/views/ApiCatalogListView.vue'),   meta: { requiresAuth: true, title: 'API' } },
{ path: '/admin/api/new',      name: 'api-create', component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, minRole: 'admin', title: 'Nouvelle API' } },
{ path: '/admin/api/:id',      name: 'api-detail', component: () => import('@/views/ApiCatalogDetailView.vue'), meta: { requiresAuth: true, title: 'Détail API' } },
{ path: '/admin/api/:id/edit', name: 'api-edit',   component: () => import('@/views/ApiCatalogFormView.vue'),   meta: { requiresAuth: true, minRole: 'admin', title: 'Modifier API' } },
```

Sidebar nav: new "API" entry between "Services" and "Paramètres". Visible to all authenticated users; admin-only buttons (Create/Edit/Delete/Rescan) hidden when `!authStore.isAdmin`.

**List view UX:** columns `Name | Protocols | Status | Source | Last Scan | Endpoints`. Filters: protocol, status, source. Search by name/tag. Top-right: `Rescan all` (admin), `+ Create` (admin).

**Detail view UX:** header with name/base_url/status/last_scanned_at. Tabs `REST | WebSocket | gRPC` (only shown when endpoints exist for that protocol). Per-tab `EndpointTable` (method, path, summary, filterable). Side panel: metadata (owner, tags, description) + Edit/Delete/Rescan buttons (admin).

**Form view UX:** full-page route. Mode determined by `route.params.id` presence (mirrors `ServiceFormView.vue`). Fields editable: name (create only), description, owner, tags, status, protocols, base_url, api_info_url, grpc_address (last three for `source='manual'` rows only — readonly otherwise).

### `api-gateway-go` changes (catalog consumer)

New files:

- `internal/catalog/client.go` — gRPC client to `api-catalog-service`.
- `internal/catalog/client_test.go` — bufconn tests.
- `internal/catalog/refresher.go` — periodic ticker that rebuilds the route map atomically.
- `internal/catalog/refresher_test.go` — verifies fallback on dial failure, atomic swap behavior.
- `internal/config/service_map.go` (modified) — adds `BuildServiceMapFromCatalog(ctx, client) (map[string]string, error)`.

Routing source decision (in `cmd/gateway/main.go` boot path):

```
if GATEWAY_USE_CATALOG && client.Dial(ctx, 3s) ok:
    services, err := client.ListServices(ctx)
    if err == nil && len(services) > 0:
        useMap = buildFromCatalog(services)
        startRefresher(client, ticker)
        return
useMap = config.BuildServiceMap()  // env fallback
```

Map shape preserved: `map[string]string` from `/<name>-service` → `base_url`. Catalog `Service.name` already includes `-service` suffix → `prefix = "/" + name`.

Feature flag:

- `GATEWAY_USE_CATALOG=false` (default at first deploy): existing env-only path, zero behavior change.
- `GATEWAY_USE_CATALOG=true` + catalog reachable: catalog wins.
- `GATEWAY_USE_CATALOG=true` + catalog unreachable at boot: env fallback.
- Refresh failure mid-flight: keep last good map, log WARN, increment metric.

New env vars: `GATEWAY_USE_CATALOG`, `API_CATALOG_GRPC`, `CATALOG_REFRESH_INTERVAL=60s`.

Metrics:

- `gateway_catalog_refresh_total{result="ok|fail"}` (counter).
- `gateway_route_source{source="catalog|env"}` (gauge, value = number of routes from each source).

Per-service downstream timeouts and excluded-services maps stay in `internal/config` for now; deferred migration.

## Data model

```sql
-- catalog_db.catalog_services
CREATE TABLE catalog_services (
  id              CHAR(36)     PRIMARY KEY,
  name            VARCHAR(128) NOT NULL UNIQUE,
  base_url        VARCHAR(512) NOT NULL,
  protocols       JSON         NOT NULL,             -- ["rest","ws","grpc"]
  source          ENUM('env','manual','scan') NOT NULL,
  status          ENUM('active','deprecated','down') NOT NULL DEFAULT 'active',
  description     TEXT,
  owner           VARCHAR(128),
  tags            JSON,
  api_info_url    VARCHAR(512),
  grpc_address    VARCHAR(512),
  last_scanned_at DATETIME,
  last_scan_ok    BOOLEAN,
  last_scan_error TEXT,
  created_by      VARCHAR(255),
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL
);

-- catalog_db.catalog_endpoints
CREATE TABLE catalog_endpoints (
  id           CHAR(36) PRIMARY KEY,
  service_id   CHAR(36) NOT NULL,
  protocol     ENUM('rest','ws','grpc') NOT NULL,
  method       VARCHAR(16),
  path         VARCHAR(512) NOT NULL,
  summary      VARCHAR(512),
  operation_id VARCHAR(255),
  tags         JSON,
  deprecated   BOOLEAN  NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_endpoint_service FOREIGN KEY (service_id) REFERENCES catalog_services(id) ON DELETE CASCADE,
  INDEX idx_endpoint_service (service_id),
  INDEX idx_endpoint_proto   (service_id, protocol)
);
```

**Source semantics:** `env` = derived from `SERVICE_*`; `manual` = admin-created in UI; `scan` = discovered by network probe outside of env (currently unused; reserved for future). Manual edits to `description/owner/tags/status` are preserved across rescans — scanner only updates `base_url`, `protocols`, `last_scanned_at`, `last_scan_ok`, `last_scan_error`, `api_info_url`, `grpc_address`.

**Cascade:** deleting a service cascades endpoints. If a deleted service reappears in `SERVICE_*` env on next scan, it is re-added with `source='env'` and a new id.

## gRPC contract

`protos/grpc_stubs/api_catalog.proto`:

```proto
syntax = "proto3";
package api_catalog;
option go_package = "rag-hp/api_catalog;api_catalog";

import "google/protobuf/timestamp.proto";

service ApiCatalog {
  rpc ListServices(ListServicesRequest)   returns (ListServicesResponse);
  rpc GetService(GetServiceRequest)       returns (Service);
  rpc ListEndpoints(ListEndpointsRequest) returns (ListEndpointsResponse);

  rpc CreateService(CreateServiceRequest) returns (Service);
  rpc UpdateService(UpdateServiceRequest) returns (Service);
  rpc DeleteService(DeleteServiceRequest) returns (DeleteServiceResponse);

  rpc RescanAll(RescanAllRequest)         returns (RescanReport);
  rpc RescanService(RescanServiceRequest) returns (RescanReport);
}

enum Protocol { PROTOCOL_UNSPECIFIED = 0; REST = 1; WS = 2; GRPC = 3; }
enum Source   { SOURCE_UNSPECIFIED   = 0; ENV  = 1; MANUAL = 2; SCAN = 3; }
enum Status   { STATUS_UNSPECIFIED   = 0; ACTIVE = 1; DEPRECATED = 2; DOWN = 3; }

message Service {
  string id = 1;
  string name = 2;
  string base_url = 3;
  repeated Protocol protocols = 4;
  Source source = 5;
  Status status = 6;
  string description = 7;
  string owner = 8;
  repeated string tags = 9;
  string api_info_url = 10;
  string grpc_address = 11;
  google.protobuf.Timestamp last_scanned_at = 12;
  bool   last_scan_ok = 13;
  string last_scan_error = 14;
  google.protobuf.Timestamp created_at = 15;
  google.protobuf.Timestamp updated_at = 16;
}

message Endpoint {
  string id = 1;
  string service_id = 2;
  Protocol protocol = 3;
  string method = 4;
  string path = 5;
  string summary = 6;
  string operation_id = 7;
  repeated string tags = 8;
  bool deprecated = 9;
}

message ListServicesRequest   { int32 limit = 1; int32 offset = 2; string filter = 3; }
message ListServicesResponse  { repeated Service items = 1; int64 total = 2; }
message GetServiceRequest     { string id = 1; }
message ListEndpointsRequest  { string service_id = 1; Protocol protocol = 2; }
message ListEndpointsResponse { repeated Endpoint items = 1; }

message CreateServiceRequest {
  string name = 1;
  string base_url = 2;
  repeated Protocol protocols = 3;
  string description = 4;
  string owner = 5;
  repeated string tags = 6;
  string api_info_url = 7;
  string grpc_address = 8;
  string created_by = 9;
}
message UpdateServiceRequest {
  string id = 1;
  optional string description = 2;
  optional string owner = 3;
  repeated string tags = 4;
  optional Status status = 5;
}
message DeleteServiceRequest  { string id = 1; }
message DeleteServiceResponse { bool deleted = 1; }

message RescanAllRequest      { bool force = 1; }
message RescanServiceRequest  { string id = 1; }
message RescanReport {
  int32 services_scanned = 1;
  int32 services_ok = 2;
  int32 services_failed = 3;
  repeated string errors = 4;
  google.protobuf.Timestamp finished_at = 5;
}
```

**Auth model:**

| Caller | RPC group | Auth |
|---|---|---|
| account-backend (read) | List/Get/ListEndpoints | none (internal network) |
| account-backend (write) | Create/Update/Delete/Rescan* | metadata `authorization: Bearer <CATALOG_ADMIN_KEY>` |
| api-gateway-go | ListServices | none |
| Any other peer | — | rejected by interceptor |

Frontend → backend auth = existing session cookie + `minRole`. Backend translates user role into "may call write RPCs".

## Service convention `/api-info`

Each service may optionally expose `GET /api-info` (no auth, internal network) returning:

```json
{
  "service": "graph-rag-api-recherche-rust-service",
  "version": "1.0.3",
  "rest": { "openapi_url": "/openapi.json" },
  "ws":   { "endpoints": [
              { "path": "/ws/search", "summary": "streaming RAG search" },
              { "path": "/ws/health" }
            ] },
  "grpc": { "address": "graph-rag-api-recherche-rust-service:50051", "reflection": true }
}
```

Rules:

- All sub-objects optional. `{service, version, rest:{...}}` is valid.
- `rest.openapi_url` defaults to `/openapi.json` if absent.
- `ws.endpoints[].path` required when `ws` present.
- `grpc.address` required when `grpc` present.
- 404 from `/api-info` is OK; scanner falls back to REST-only inference.

A reference helper added to `libs/common-utils` (Python) registers `/api-info` on any FastAPI app via a single import. Service-by-service adoption handled in follow-up PRs (out of scope of this spec).

## Scanner internals

```go
// pseudo
func Run(ctx context.Context) Report {
    targets := mergeEnvAndManual(env, repo.ListAll())
    sem := make(chan struct{}, cfg.Concurrency)
    var wg errgroup.Group
    for _, t := range targets {
        sem <- struct{}{}
        t := t
        wg.Go(func() error {
            defer func() { <-sem }()
            scanOne(ctx, t)
            return nil
        })
    }
    _ = wg.Wait()
    return report
}

func scanOne(ctx context.Context, t target) {
    rest := probeREST(ctx, t.baseURL)             // GET /openapi.json
    info := probeAPIInfo(ctx, t.baseURL)          // GET /api-info (optional)
    grpc := []Endpoint{}
    if info.grpc.address != "" {
        grpc = probeGRPCReflection(ctx, info.grpc.address)
    }
    ws := info.ws.endpoints
    upsertServiceAndReplaceEndpoints(t, rest, ws, grpc)
}
```

**Failure isolation:** one service failing never aborts the scan. Errors aggregated into `RescanReport.errors`. Per-service partial failure → `last_scan_ok=false` with concatenated message.

**Idempotency:** rescan is safe to re-run; manual metadata preserved by partial UPDATE.

**Stale detection:** services with `source='env'` no longer in env → `status='down'`. `source='manual'` rows untouched.

## Error handling

Per `golang-error-handling` guidance:

- gRPC server returns `status.Errorf(codes.X, ...)` with `NotFound`, `AlreadyExists`, `InvalidArgument`, `Unauthenticated`, `Unavailable`.
- Internal errors wrapped with `%w` for logs; clean message surfaced to client.
- Scanner errors collected in `RescanReport.errors`; never panic.
- Account-backend translates gRPC codes to HTTP: `NotFound→404`, `AlreadyExists→409`, `InvalidArgument→400`, `Unauthenticated→401`, `Unavailable→503`.

## Testing strategy

Per `golang-testing`:

- **Repository:** SQLite in-memory or testcontainers MySQL.
- **Scanner:** `httptest.Server` for REST/api-info; in-process gRPC server for reflection.
- **gRPC server:** `bufconn` listener + table-driven cases per RPC.
- **Account-backend handlers:** mock catalog client (interface), table-driven per route.
- **Gateway refresher:** mock catalog with bufconn; verify env fallback on dial failure, atomic map swap.
- **Frontend:** Vitest for `apiCatalog.ts` API wrappers; smoke tests for List/Detail/Form views.

## CI/CD

- New workflow `ci_services_api_catalog.yml` (lint, `go vet`, `go test`).
- New workflow `cd_build_push_api_catalog.yml` (Docker build + push).
- Update `account-service-backend` and `api-gateway-go` workflows if dependency graph requires (proto stubs).
- `protos/` change → run `/proto-sync` to regenerate Python stubs. Go stubs are generated per consumer Go module (no shared `libs/grpc-stubs-go` exists today): each Go service runs `protoc --go_out=internal/genproto --go-grpc_out=internal/genproto` at build time. Stubs live under each module's `internal/genproto/api_catalog/`. Future consolidation into a shared module is out of scope.

## Rollout phases

1. Land catalog service + proto + helper (no consumer changes). Boot, scan, RPCs callable. Smoke test against staging.
2. Land account-backend handlers + frontend "API" nav. Read-only verified. `GATEWAY_USE_CATALOG=false`.
3. Enable CRUD writes. Verify rescan flow.
4. Land gateway refresher behind `GATEWAY_USE_CATALOG=false`. Code present but inactive.
5. Flip `GATEWAY_USE_CATALOG=true` in staging. Verify routes match env-derived map.
6. Flip prod. Monitor `gateway_route_source` metric for catalog/env split.
7. (Future) Migrate `excluded_services` and `downstream_timeouts` into catalog DB columns.

## Out of scope (deferred)

- mTLS between services.
- Endpoint-level rate limits / per-service auth scopes.
- Reading rate limits from catalog at the gateway.
- Gateway push-based refresh (replacing pull).
- WS endpoint introspection without `/api-info`.
- Per-service adoption of `/api-info` (handled in follow-up PRs per service).
- Code-annotation parsing for static endpoint discovery.

## References

- Project conventions: `CLAUDE.md`, `protos/CLAUDE.md`, `apps-microservices/api-gateway-go/CLAUDE.md`, `apps-microservices/account-service-backend/CLAUDE.md`, `apps-microservices/account-service-frontend/CLAUDE.md`.
- Skills referenced for implementation: `golang-pro`, `golang-project-layout`, `golang-grpc`, `golang-naming`, `golang-error-handling`, `golang-testing`, `golang-security`, `golang-code-style`, `superpowers:test-driven-development`, `superpowers:writing-plans`.
