# api-gateway-go

Reverse-proxy gateway that authenticates requests (JWT + API key) and routes them to downstream microservices. Also aggregates OpenAPI specs from all registered services. Strict 1:1 Go port of `api-gateway/` (Python/FastAPI) — lives side-by-side until cutover.

## Tech Stack

- **Language:** Go 1.24
- **Framework:** Gin (HTTP router)
- **ORM:** GORM (`gorm.io/gorm`)
- **DB:** MySQL via `gorm.io/driver/mysql`
- **Cache:** Redis via `redis/go-redis/v9`
- **Proxy:** Nginx sidecar (port 8050) for crawler/comparator routes
- **Shared lib:** none (Go binary is self-contained)

## Build / Run

- **Port:** 8500 (Gin), 8050 (Nginx)
- **Build:** `go build ./cmd/gateway && ./gateway`
- **Docker build context:** monorepo root (Dockerfile at `apps-microservices/api-gateway-go/Dockerfile`)

## Folder Structure

```
api-gateway-go/
  cmd/
    gateway/
      main.go              # Entry point: wire deps, start Gin server
  internal/
    config/
      config.go            # Env-driven config (SERVICE_MAP, timeouts, secrets)
    db/
      db.go                # GORM MySQL setup
      models.go            # ApiCallHistory, InfoRefreshToken, InfoAccessToken
      schemas.go           # Response structs
    auth/
      middleware.go        # DocsAuthMiddleware, VerifyAPIToken
      token_service.go     # JWT generation helpers
    proxy/
      proxy.go             # Reverse-proxy handler
    routers/
      login.go             # GET/POST /login, /logout (session-based)
      tokens.go            # /auth/token/* endpoints
      logs.go              # GET /auth/logs
    openapi/
      aggregator.go        # Fetches /openapi.json from all downstream services
    sso/
      sso.go               # hellopro.fr auth integration
  nginx.conf               # Nginx reverse-proxy config
  go.mod
  go.sum
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `*` | `/{service}/{path}` | Bearer | Proxy to downstream service |
| `WS` | `/{service}/{path}` | None | WebSocket proxy |
| `POST` | `/auth/token/generate` | AdminCle | Create refresh + access token |
| `POST` | `/auth/token/refresh` | Public | Exchange refresh for access token |
| `POST` | `/auth/token/revoke` | AdminCle | Revoke a service's tokens |
| `GET` | `/auth/token/refresh-tokens` | Public | List refresh tokens for a service |
| `GET` | `/auth/token/all-refresh-tokens` | AdminCle | List all refresh tokens |
| `GET` | `/auth/logs` | AdminCle | Paginated audit log |
| `GET` | `/login` | None | Login page |
| `GET` | `/docs` | Session | Swagger UI (admin/public split) |

## Conventions

- Service routing is env-driven: `SERVICE_<NAME>=http://url` registers `/<name>-service`.
- Sensitive headers are redacted before persisting to `ApiCallHistory`.
- Admin endpoints require `X-Admin-Key` header matching `GATEWAY_ADMIN_KEY` env var.
- All config via environment variables — no hardcoded URLs, secrets, or connection strings.
- `internal/` packages are unexported by default; expose only what Gin route handlers need.
- Error strings are lowercase, no trailing punctuation (Go convention).

## Auth Policy (catalog-driven)

The verifier reads per-service `AuthPolicy` and `public_paths` from the catalog
`Refresher` snapshot (`internal/auth/policy_snapshot.go` + `internal/catalog/refresher.go`)
— there is no longer any hardcoded auth state in the gateway. Decision order per request
(`AuthSnapshot.PolicyFor`):

1. Endpoint override (`Endpoint.auth_policy` in catalog) wins.
2. Else service `public_paths` exact match → `PUBLIC`.
3. Else service `auth_policy` default (`public` / `bearer` / `admin-key`).
4. Unknown service → `PUBLIC` (fail-open; logged once per hour per service).

`PUBLIC` → no auth; `BEARER` → JWT + Redis/DB check; `ADMIN_KEY` → `X-Admin-Key` == `GATEWAY_ADMIN_KEY`.
Edit policies in account-service-frontend → catalog persists → ≤`CATALOG_REFRESH_INTERVAL` (60s default)
for the gateway snapshot to pick up the change. Snapshot empty (catalog down) → every service is `PUBLIC`.

Spec: `docs/superpowers/specs/2026-05-28-apitokenverifier-catalog-driven-design.md`.

## Per-Service Downstream Timeouts

The gateway applies per-service HTTP timeouts via `config.BuildDownstreamTimeouts()` in `internal/config/service_map.go` (wired into the proxy as `HTTPDeps.DownstreamTimeout` in `cmd/gateway/main.go`). The map value is the **total** timeout in seconds; the connect timeout is a fixed 10s (`internal/proxy/http.go` `clientForService`). Services NOT in the map use `timeout=0` (no timeout — current behavior preserved, zero blast radius on unlisted services).

Currently configured:
- `api-detection-langue-fr-service`: 180s total, 10s connect
- `extractor-service`: 60s total, 10s connect (content-extractor-api-service; route `/extractor-service/...`)

Add a service to the map only after understanding its request-duration profile. On timeout, the gateway returns `504` to the caller. Downstream `503` responses (typically from admission middleware load-shedding) are logged at WARNING and passed through with `Retry-After` intact.

Spec: `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`.

## Dependencies on Other Services

- All registered microservices (fetches their `/openapi.json` for spec aggregation)
- MySQL (GORM for token + history storage)
- Redis (access-token TTL cache)
- External: `hellopro.fr` auth endpoint for docs login
