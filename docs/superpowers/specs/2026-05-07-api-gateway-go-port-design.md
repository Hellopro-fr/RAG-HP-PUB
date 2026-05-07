# api-gateway → Go port (design)

**Date:** 2026-05-07
**Status:** Approved (brainstorming gate)
**Source service:** `apps-microservices/api-gateway/` (Python 3.10 / FastAPI / Tortoise-ORM)
**Target service:** `apps-microservices/api-gateway-go/` (Go 1.24 / Gin / GORM)

## 1. Goals

Strict 1:1 port of the existing Python api-gateway to Go, preserving:

- Every public endpoint (path, method, status code, body shape).
- Every persisted artifact (MySQL tables, Redis keys, JWT secrets and claims).
- Every observable behavior (header propagation, security headers, per-service timeouts, openapi aggregation, swagger admin UX).
- Every env var contract (`SERVICE_*`, `EXCLUDED_ROUTES_*`, `ACCOUNT_*`, `GATEWAY_*`, `MYSQL_*`, `JWT_*`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `SECURE_COOKIE`, `SERVICE_NAME`, `GATEWAY_DOCS_ADMIN_EMAILS`).

Non-goals:

- No schema migration. Same DB, same column names (French: `nom_service`, `est_actif`, `date_creation`, `ip_creation`, `date_expiration`).
- No behavior change. Existing JWTs minted by the Python gateway must remain valid against the Go gateway.
- No new endpoints, no removed endpoints.
- Old Python service stays in-tree until cutover validated. New service ships under a new folder.

## 2. Scope

### 2.1 Endpoints (all must be ported)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET\|POST\|PUT\|DELETE\|PATCH` | `/{service}/{path}` | Bearer (TODO logic preserved) | Reverse proxy + history log |
| `WS` | `/{service}/{path}` | None | Bidir WebSocket relay |
| `POST` | `/auth/token/generate` | `X-Admin-Key` | Create or reuse refresh token + emit access token |
| `POST` | `/auth/token/refresh` | Public | Exchange refresh → access |
| `POST` | `/auth/token/revoke` | `X-Admin-Key` | Deactivate refresh + all linked access tokens (DB + Redis) |
| `GET` | `/auth/token/refresh-tokens` | Public | List tokens for a service. `refresh` body included only if session present |
| `GET` | `/auth/token/all-refresh-tokens` | `X-Admin-Key` | All services |
| `GET` | `/auth/logs` | `X-Admin-Key` | Paginated history |
| `GET` | `/login` | None | Session check → `/docs` (303) or `/auth/login` (302) |
| `GET` | `/logout` | None | Clear session, 303 → `/login` |
| `GET` | `/auth/login` | None | PKCE flow start (302 → account-service) |
| `GET` | `/auth/callback` | None | PKCE callback, populates session |
| `POST` | `/auth/logout-webhook` | HMAC-SHA256 | account-service back-channel logout |
| `GET` | `/openapi.json` | DocsAuth (session) | Aggregated full spec |
| `GET` | `/openapi-public.json` | DocsAuth (session) | Aggregated spec, admin endpoints stripped |
| `GET` | `/docs` | DocsAuth (session) | Custom Swagger UI with JS injection |
| `GET` | `/redoc` | DocsAuth (session) | 301 → `/docs` |

### 2.2 External dependencies (unchanged)

- MySQL: same DB, same 3 tables (see §4).
- Redis: same key format `access_token:<token>` with TTL.
- account-service: same OAuth 2.1 + PKCE client integration (`/authorize`, `/token`, optional `/internal/credentials/<service>`).
- All registered downstream microservices (proxy targets + `/openapi.json` aggregation source).
- Nginx sidecar on port 8050: kept as-is, separate container, `nginx.conf` copied unchanged.

## 3. Architecture

```
apps-microservices/api-gateway-go/
  cmd/gateway/main.go                # entrypoint, port 8500
  internal/
    config/
      config.go                      # env-driven config struct
      service_map.go                 # SERVICE_<NAME>=URL → SERVICE_MAP, EXCLUDED_ROUTES, DOWNSTREAM_TIMEOUTS
    db/
      db.go                          # GORM init, AutoMigrate, bootstrap_refresh_tokens
      models.go                      # InfoRefreshToken, InfoAccessToken, ApiCallHistory
    cache/
      redis.go                       # go-redis/v9 client, get_json/set_json/delete_key/scan_keys_by_prefix
    auth/
      jwt.go                         # HS256 sign/verify, claims sub/rtid/iat/exp
      docs_middleware.go             # Gin middleware: session + JWT for /docs /redoc /openapi.json
      api_token.go                   # Gin middleware: Bearer JWT for proxy route
      admin_key.go                   # Gin middleware: X-Admin-Key gate
    proxy/
      http.go                        # httputil.ReverseProxy, per-service timeouts, header strip, security headers
      ws.go                          # gorilla/websocket bidir relay (2 goroutines, first-close cancel)
      history.go                     # async ApiCallHistory write (channel + worker)
    routers/
      login.go                       # /login, /logout
      sso.go                         # /auth/login, /auth/callback, /auth/logout-webhook
      tokens.go                      # /auth/token/{generate,refresh,revoke,refresh-tokens,all-refresh-tokens}, /auth/logs
      docs.go                        # /docs, /redoc, /openapi.json, /openapi-public.json
    openapi/
      base.yaml                      # gateway's own OpenAPI 3.1 spec (embedded)
      aggregator.go                  # downstream fetch + 2-pass collision-detection merge
      filter.go                      # admin-only endpoint stripping for /openapi-public.json
      swagger_assets/                # Swagger UI HTML/JS (embedded), with custom JS overlay
    sso/
      client.go                      # account-service client cred resolution (env → /internal/credentials)
      pkce.go                        # verifier/challenge/state generation
  go.mod
  go.sum
  Dockerfile                         # multi-stage: golang:1.24-alpine → distroless static
  nginx.conf                         # COPIED unchanged from Python service
  CLAUDE.md
  README.md
  tests/
    ...                              # mirror of internal/ tree
```

### 3.1 Entrypoint

`cmd/gateway/main.go` builds the Gin engine, registers all router groups in the same order as the Python `app.include_router` calls, attaches middleware in the correct order (session → DocsAuth applied only on protected paths), starts the history worker goroutine, runs `db.AutoMigrate` + `bootstrap_refresh_tokens`, listens on `0.0.0.0:8500`.

## 4. Data layer (GORM)

Same MySQL DB. GORM tags pin every Tortoise table/column name exactly to avoid migrations.

```go
// internal/db/models.go

type InfoRefreshToken struct {
    ID           uint      `gorm:"column:id;primaryKey;autoIncrement"`
    NomService   string    `gorm:"column:nom_service;size:128;index"`
    Token        string    `gorm:"column:token;size:768;index"`
    DateCreation time.Time `gorm:"column:date_creation;autoCreateTime"`
    IPCreation   string    `gorm:"column:ip_creation;size:64;default:system"`
    EstActif     bool      `gorm:"column:est_actif;default:true;index"`
}
func (InfoRefreshToken) TableName() string { return "info_refresh_token" }

type InfoAccessToken struct {
    ID              uint             `gorm:"column:id;primaryKey;autoIncrement"`
    IDRefreshToken  uint             `gorm:"column:id_refresh_token_id;index"`
    RefreshToken    InfoRefreshToken `gorm:"foreignKey:IDRefreshToken;references:ID;constraint:OnDelete:CASCADE"`
    Token           string           `gorm:"column:token;size:768;index"`
    DateCreation    time.Time        `gorm:"column:date_creation;autoCreateTime"`
    DateExpiration  time.Time        `gorm:"column:date_expiration"`
    EstActif        bool             `gorm:"column:est_actif;default:true;index"`
}
func (InfoAccessToken) TableName() string { return "info_access_token" }

type ApiCallHistory struct {
    ID              uint      `gorm:"column:id;primaryKey;autoIncrement"`
    ServiceName     string    `gorm:"column:service_name;size:128;index"`
    Method          string    `gorm:"column:method;size:10"`
    Path            string    `gorm:"column:path;type:text"`
    StatusCode      int       `gorm:"column:status_code"`
    ClientIP        string    `gorm:"column:client_ip;size:64"`
    RequestHeaders  *string   `gorm:"column:request_headers;type:text"`
    CalledAt        time.Time `gorm:"column:called_at;autoCreateTime;index"`
    DurationMs      *int      `gorm:"column:duration_ms"`
}
func (ApiCallHistory) TableName() string { return "api_call_history" }
```

Note the Tortoise FK column convention: `id_refresh_token` exposes a `<name>_id` column (`id_refresh_token_id`). The Go model uses the same column name to match.

### 4.1 Bootstrap

`db.BootstrapRefreshTokens()` runs once on startup after AutoMigrate. Walks `SERVICE_MAP`, derives `service_name = strings.TrimPrefix(api_path, "/")`, creates `InfoRefreshToken` if no active row exists. JWT-encoded with `{sub: service_name, type: refresh, iat: now}` (no `exp`).

### 4.2 Access token pruning

Same rule as Python: keep at most `MAX_ACTIVE_ACCESS_TOKENS = 10` most-recent active non-expired access tokens per refresh token; deactivate the rest. Also flip `est_actif = false` on any expired-but-still-active rows. Called after every `generate` and `refresh`.

## 5. Auth

### 5.1 JWT helpers (`internal/auth/jwt.go`)

`golang-jwt/jwt/v5`. HS256 with `JWT_SECRET`. Functions:

- `GenerateRefreshToken(service string) string` → claims `{sub, type:"refresh", iat}` (no exp).
- `GenerateAccessToken(service string, rtid uint) string` → claims `{sub, rtid, iat, exp}`, exp = now + `ACCESS_TOKEN_EXPIRE_MINUTES`.
- `VerifyAccessToken(raw string) (Claims, error)` → returns parsed claims or `ExpiredError`/`InvalidError`.

Existing tokens minted by Python remain valid because secret + algo + claim names are identical.

### 5.2 `verifyAPIToken` middleware (`internal/auth/api_token.go`)

Mirrors `app/core/auth.py:verify_api_token` exactly, including the current TODO short-circuit:

```
service := c.Param("service")
if service != "graphdlq-service" {
    c.Set("token_payload", map[string]any{"sub": service, "is_excluded": true})
    c.Next()
    return
}
// only graphdlq-service hits the real auth path
```

For `graphdlq-service`:

1. Check `EXCLUDED_ROUTES[service]`; if request path matches, bypass.
2. Parse `Authorization: Bearer <jwt>`, return 401 if missing/malformed.
3. Verify JWT (signature + exp). Map `ExpiredError` → 401 with FR detail, `InvalidError` → 401.
4. Redis fast path: `GET access_token:<raw>`. If hit, accept.
5. DB fallback: query `InfoAccessToken` where `token=raw AND est_actif AND date_expiration >= now`, preload `InfoRefreshToken`, reject if either inactive.

All 401 responses include `WWW-Authenticate: Bearer` header.

### 5.3 `requireAdminKey` middleware (`internal/auth/admin_key.go`)

Reads `X-Admin-Key` header, compares to `GATEWAY_ADMIN_KEY` env. 403 on mismatch.

### 5.4 `DocsAuthMiddleware` (`internal/auth/docs_middleware.go`)

Triggers only on paths in `{ "/docs", "/redoc", "/openapi.json" }` (the same set as Python's `DOCS_PROTECTED_PATHS`; note `/openapi-public.json` is intentionally NOT in this set in the current Python — preserve that). For protected paths:

1. Read `session.user`. None → 302 `/login`.
2. Read `user.token`. None → 302 `/login`.
3. `jwt.Parse(token, JWT_SECRET, options={skipAudience})`. Expired/invalid → clear session, 302 `/login`.
4. Else next.

## 6. Proxy (`internal/proxy/http.go`)

Built on `net/http/httputil.ReverseProxy` constructed per-request from `SERVICE_MAP[/{service}]`.

Steps per request:

1. Resolve `baseURL`. None → `404 {"detail": "Service not found"}`.
2. Build `targetURL = baseURL + "/" + path + "?" + rawQuery`.
3. Strip excluded headers from request: `host, content-length, transfer-encoding, connection` (case-insensitive).
4. Determine timeout: `serviceKey = service-suffix-corrected`; `t = DOWNSTREAM_TIMEOUTS[serviceKey]`. Build `http.Client` with `Timeout=t` and dialer `Connect=10s` if `t>0`, else no timeout.
5. Issue request via `http.Client.Do`. On `errors.Is(err, context.DeadlineExceeded)`/timeout → log warn, return 504 with FR detail. On dial/connection error → 503 FR detail. Pass-through 503 from upstream with `Retry-After`.
6. Strip excluded response headers, then add: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
7. Copy status, body, content-type to client.
8. Compute `duration_ms` and enqueue `historyEvent` on the buffered channel (non-blocking; drop on full buffer with warn log to match the Python `fire-and-forget` semantics).

### 6.1 WebSocket proxy (`internal/proxy/ws.go`)

`gorilla/websocket`. Steps:

1. Resolve baseURL like HTTP. None → `1008` close.
2. Convert scheme `http→ws`, `https→wss`.
3. Strip headers `connection, upgrade, host, sec-websocket-{key,version,protocol,extensions}`.
4. `websocket.DefaultDialer.Dial(target, fwdHeaders)`.
5. Two goroutines: client→backend (text), backend→client (text). First close cancels both. Log info on each close path.

Token auth is intentionally NOT enforced on WS — matches current Python behavior.

### 6.2 History worker (`internal/proxy/history.go`)

Single buffered channel (cap 1024) drained by N goroutines (default `N = max(2, runtime.NumCPU()/2)`). Each event:

- Skip if `service_name in EXCLUDED_SERVICES = {crawling-service, image_comparator-service, graphadmin-service}`.
- Sanitize headers: `Authorization, Cookie, X-Api-Key, Set-Cookie` → `[REDACTED]`. Marshal to JSON.
- `INSERT INTO api_call_history`. Errors logged at warn, swallowed.

## 7. SSO (PKCE) — `internal/routers/sso.go`

### 7.1 Client cred resolution (`internal/sso/client.go`)

Mirrors `common_utils.sso.get_account_credentials` precedence:

1. `ACCOUNT_CLIENT_ID_<SERVICE_NAME_UPPER>` + `ACCOUNT_CLIENT_SECRET_<SERVICE_NAME_UPPER>` (e.g. `API_GATEWAY`).
2. `ACCOUNT_CLIENT_ID` + `ACCOUNT_CLIENT_SECRET`.
3. HTTP fallback: `GET ${ACCOUNT_BASE_URL}/internal/credentials/<service-name>` returning `{client_id, client_secret, redirect_uris}`.

Cached after first resolution.

### 7.2 `/auth/login`

- Generate `verifier = base64url(rand 32 bytes)`, `challenge = base64url(sha256(verifier))`, `state = base64url(rand 16 bytes)`.
- Build URL: `${ACCOUNT_PUBLIC_URL}/authorize?response_type=code&client_id=...&redirect_uri=...&code_challenge=...&code_challenge_method=S256&state=...`.
- Set cookies `auth_verifier`, `auth_state`: HttpOnly, SameSite=Lax, Secure if `SECURE_COOKIE=true`, MaxAge=600, Path=/.
- 302.

### 7.3 `/auth/callback`

- Validate `state` query == `auth_state` cookie. Read `auth_verifier` cookie. Reject 400 on mismatch/missing.
- POST `${ACCOUNT_BASE_URL}/token` with form `grant_type=authorization_code, code, redirect_uri, code_verifier`, Basic auth `(client_id, client_secret)`. 10s timeout.
- Non-200 → 502.
- Decode JWT payload (no signature check — same as Python). Read `name`, `sub`, `email`, `sid`, `iss`, `exp`.
- Populate session:
  ```go
  user := map[string]any{
      "display_name": name (fallback sub),
      "email":        sub (fallback email),
      "token":        access_token,
      "sso": map[string]any{
          "sid": sid, "iss": iss, "exp": exp,
          "refresh_token": refresh_token,
      },
  }
  ```
- Delete PKCE cookies. 303 → `/docs`.

### 7.4 `/auth/logout-webhook`

- Read body bytes.
- `expected = "sha256=" + hex(hmacSha256(client_secret, body))`. `hmac.Equal(presented, expected)` else 401.
- Parse JSON; verify `|now - iat| <= 300s`, else 401.
- Log `sub`, `sid`. Return 204.

## 8. Token endpoints (`internal/routers/tokens.go`)

Behavior 1:1 with Python `app/routers/tokens.py`. Highlights:

- `POST /auth/token/generate` (admin): reuse active refresh if exists else create; emit new JWT access; insert `InfoAccessToken`; mirror in Redis with TTL = `ACCESS_TOKEN_EXPIRE_MINUTES * 60`; prune.
- `POST /auth/token/refresh` (public): match `nom_service AND token AND est_actif`; 401 on miss; emit JWT, insert, mirror in Redis, prune.
- `POST /auth/token/revoke` (admin): flip all matching refresh + access rows to `est_actif=false`; delete each `access_token:<token>` Redis key.
- `GET /auth/token/refresh-tokens` (public): list by `nom_service`. `refresh` body included only when `session.user` exists (browser caller).
- `GET /auth/token/all-refresh-tokens` (admin): all services, `active_only` optional ternary (`true`/`false`/absent=both).
- `GET /auth/logs` (admin): paginated, descending `called_at`, optional `service_name` filter.

Response shapes match `app/db/schemas.py` exactly (field names + types).

## 9. OpenAPI aggregator (`internal/openapi/`)

### 9.1 Base spec

`internal/openapi/base.yaml` is an OpenAPI 3.1 document hand-authored to mirror the Python-generated spec for the gateway's own endpoints (`/auth/token/*`, `/auth/logs`, `/login`, `/logout`, `/auth/login`, `/auth/callback`, `/auth/logout-webhook`). Embedded via `//go:embed`. Loaded once at startup by `kin-openapi/openapi3`.

Includes the same `info.description` Markdown block and the `<!-- ADMIN_SECTION -->` sentinel marker.

### 9.2 Downstream fetch + merge

On every `GET /openapi.json` request:

1. `errgroup.WithContext` to fetch `<url>/openapi.json` for each `(prefix, url)` in `SERVICE_MAP`. Per-request timeout (5s default). Failures logged + skipped (non-fatal — same as Python).
2. **Pass 1 — collision detection**: walk every fetched `components.schemas` map, build `schemaTracker map[string][]string` of `{schemaName → []prefix}`. Names in ≥2 prefixes go into `conflictingSchemas set`.
3. **Pass 2 — merge**:
   - For each fetched spec, compute `schemaPrefix = TitleCase(prefix without "/" and "-service", "-" → "_")` (e.g. `/classification-v2-service` → `ClassificationV2`).
   - Walk paths: for every operation, prefix `operationId` with `<service-snake>_`.
   - Walk all `$ref` strings inside the fetched spec's paths and components: if `$ref` ends with a name in `conflictingSchemas`, prefix with `schemaPrefix`; else leave as-is.
   - For each path, write back as `<prefix><path>` into the merged spec.
   - Merge components: schemas in `conflictingSchemas` get key prefixed with `schemaPrefix` and value with refs rewritten; other components copied if absent.
4. Inject security schemes into `components.securitySchemes`:
   - `Bearer Token`: `{type: http, scheme: bearer, bearerFormat: JWT, description: ...}`
   - `AdminCle`: `{type: apiKey, in: header, name: X-Admin-Key, description: ...}`
   - Global `security: [{Bearer Token: []}]`.
5. Append admin description (the `_ADMIN_DESCRIPTION_EXTRA` block in `main.py:441-463`) to `info.description`.

### 9.3 Public-spec filter (`internal/openapi/filter.go`)

Deep-copy aggregated spec, then:

- Drop every operation where `security` array contains `{AdminCle: []}`.
- Drop empty paths.
- Remove `AdminCle` from `components.securitySchemes`.
- Truncate `info.description` at `\n<!-- ADMIN_SECTION -->`.

### 9.4 `/docs` Swagger UI (`internal/routers/docs.go`)

- Embed Swagger UI HTML + JS via `//go:embed` (pinned version, distroless-friendly).
- Determine admin: `email = session.user.email.lower()`; `is_admin = email != "" AND email in GATEWAY_DOCS_ADMIN_EMAILS_SET`.
- Pick `openapi_url = is_admin ? "/openapi.json" : "/openapi-public.json"`.
- Inject the `common_js` block (auto-bearer token capture from `/auth/token/generate` and `/auth/token/refresh` 200 responses, fallback DOM fill).
- If admin: also inject `admin_js` block (MutationObserver fills `AdminCle` input, requestInterceptor adds `X-Admin-Key` header).
- Both JS blobs are byte-identical to Python output (use the same string constants moved into Go raw string literals).

### 9.5 `/redoc`

301 redirect to `/docs`. (Identical to Python.)

## 10. Sessions

`gin-contrib/sessions` cookie store keyed by `JWT_SECRET`. Cookie name `session` (Starlette default). Options: HttpOnly, SameSite=Lax, Secure if `SECURE_COOKIE=true`, Path=/.

Cutover invalidates existing sessions because Starlette's `itsdangerous` signing scheme is not byte-compatible with `gorilla/securecookie`. Users re-login once. Documented in cutover runbook.

## 11. Config (`internal/config/config.go`)

Loaded from env at startup (no `.env` file dependency at runtime; docker-compose injects env directly). `dotenv` only used in dev mode if file present.

| Env | Default | Purpose |
|-----|---------|---------|
| `JWT_SECRET` | (required) | HS256 signing key |
| `JWT_ALGO` | `HS256` | Algorithm |
| `JWT_AUDIENCE` | `hellopro` | Reserved (not currently checked) |
| `GATEWAY_ADMIN_KEY` | (required) | X-Admin-Key value |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `MYSQL_HOST/PORT/USER/PASS/DB` | `gateway-mysql/3306/gateway_user/gateway_pass/gateway_db` | DB conn |
| `REDIS_URL` (or HOST/PORT) | per common-utils | Cache |
| `SERVICE_<NAME>=URL` | — | Dynamic SERVICE_MAP |
| `ACCOUNT_BASE_URL` | `http://account-service-backend:8600` | In-cluster account-service URL |
| `ACCOUNT_PUBLIC_URL` | = ACCOUNT_BASE_URL | Public origin for redirects |
| `ACCOUNT_REDIRECT_URI` | (optional) | Override registered redirect_uri |
| `ACCOUNT_CLIENT_ID[_<SERVICE>]` | — | Static cred lookup |
| `ACCOUNT_CLIENT_SECRET[_<SERVICE>]` | — | Static cred lookup |
| `SECURE_COOKIE` | `false` | Cookie Secure flag |
| `SERVICE_NAME` | `api-gateway` | Used to derive ACCOUNT_CLIENT_*_API_GATEWAY |
| `GATEWAY_DOCS_ADMIN_EMAILS` | `""` | Comma-separated admin email list |
| `UVICORN_WORKERS` | (ignored) | Replaced by GOMAXPROCS |

Hard-coded constants (preserved from Python):

- `DOWNSTREAM_TIMEOUTS_S = {"api-detection-langue-fr-service": 180}`.
- `EXCLUDED_ROUTES_LIST = {"graphdlq-service": ["/dlq/queues"]}`.
- `MAX_ACTIVE_ACCESS_TOKENS = 10`.
- `EXCLUDED_SERVICES = {"crawling-service", "image_comparator-service", "graphadmin-service"}`.

## 12. Dockerfile

```Dockerfile
# apps-microservices/api-gateway-go/Dockerfile

FROM golang:1.24-alpine AS builder
WORKDIR /src

COPY apps-microservices/api-gateway-go/go.mod apps-microservices/api-gateway-go/go.sum ./
RUN go mod download

COPY apps-microservices/api-gateway-go/ ./
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/gateway \
    ./cmd/gateway

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /
COPY --from=builder /out/gateway /gateway
EXPOSE 8500
USER nonroot:nonroot
ENTRYPOINT ["/gateway"]
```

No healthcheck endpoint added — Python service has none and the strict 1:1 scope forbids new endpoints. Compose `healthcheck` block (if added later) would have to reuse an existing route (e.g. `/login` with `expect_status: 302`).

## 13. Tests

All packages get unit tests (TDD per project rule). Stack:

- `httptest.Server` for proxy + WS targets.
- `go-sqlmock` for GORM unit tests.
- `miniredis` for Redis path.
- `gorilla/websocket` test client for WS proxy.
- Integration: docker-compose up with `mysql:8` + `redis:7` + a stubbed downstream service; Go tests hit real DB.

Coverage targets:

- `internal/auth/*`: 90%+ (security-sensitive).
- `internal/proxy/*`: 80%+ (header strip, timeout, error path, WS bidir).
- `internal/openapi/*`: 80%+ (collision detection edge cases — same name in 2 vs 3 services, refs in nested arrays/maps).
- `internal/db/*`: 70%+.
- `internal/routers/*`: 70%+ end-to-end with miniredis + sqlmock.

## 14. Cutover plan

1. Build + push `api-gateway-go` image to registry. Tag: `api-gateway-go:0.1.0`.
2. Add new compose service `api-gateway-go` on port `8501` (parallel run). Wire same env vars. Old `api-gateway` keeps `8500`.
3. Smoke test new service:
   - Curl `/auth/token/generate` with admin key → JWT issued.
   - Curl proxy through new gateway with that JWT → downstream reached.
   - Browser `/login` → SSO flow → `/docs` loads with merged spec.
   - WebSocket end-to-end test against a known WS service.
4. Compare aggregated `/openapi.json` from old vs new (diff schemas + paths). Investigate any drift before flipping traffic.
5. Flip compose port mapping: `api-gateway-go` → 8500. Old service stopped (kept in repo for one release in case rollback needed).
6. Decommission Python service in a follow-up PR after ≥1 week of stable operation.

## 15. Risks + mitigations

| Risk | Mitigation |
|------|-----------|
| Session cookie incompatibility | Documented; users re-login once at cutover. |
| OpenAPI aggregation drift (schema name collisions) | Side-by-side diff during smoke phase. Unit tests cover collision rules. |
| Tortoise vs GORM column name mismatch | Explicit `gorm:"column:..."` tags and integration test validates AutoMigrate is a no-op against existing schema. |
| JWT incompatibility | Same secret + algo + claim names. Verified by issuing token from Python and verifying in Go in a unit test fixture. |
| WebSocket header semantics differ | Adopt the same exclusion list, test with a real WS downstream. |
| `kin-openapi` lossy round-trip on edge cases | Use `interface{}` map walks for the merge step instead of typed marshaling, to preserve unknown fields in downstream specs. |

## 16. Out of scope

- Changing endpoint contracts.
- Replacing Nginx sidecar.
- Dropping or adding env vars.
- Migrating MySQL schema or Redis keys.
- Adding observability beyond what Python has (Prometheus `/metrics` already absent in Python; not adding now).

---

**Approval:** Strict 1:1 port confirmed (Q1), Gin + GORM stack confirmed (Q2), new folder + Python kept confirmed (Q3), Nginx kept as sidecar confirmed (Q4), cookie sessions confirmed (Q5).
