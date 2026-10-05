# mcp-gateway-service

Central MCP (Model Context Protocol) gateway that aggregates and routes requests across multiple backend MCP servers, providing unified tool/resource/prompt discovery and scoped access control.

## Tech Stack

- Go 1.24
- `net/http` (standard library) — HTTP server
- GORM v1.25 — ORM (MySQL driver)
- AES-256-GCM — encryption for stored auth headers
- JWT (HS256 via golang-jwt/jwt/v5) — authentication (enabled by default)
- Docker (multi-stage: golang:1.24-alpine → alpine:3.20), exposed port **8592**

## Run

```bash
# Local (requires Go 1.24+)
cd apps-microservices/mcp-gateway-service
go run ./cmd/server/

# Docker
docker build -t mcp-gateway-service .
docker run -p 8592:8592 -e MYSQL_DSN="..." mcp-gateway-service
```

## Directory Structure

```
cmd/server/
  main.go                    # Entry point, route registration, graceful shutdown
internal/
  api/
    handler.go               # REST API route registration
    server_handlers.go       # Server CRUD endpoints
    token_handlers.go        # Scope token CRUD endpoints
    oauth2_handlers.go       # OAuth2 client CRUD endpoints
    import_handler.go        # Import servers from .mcp.json
    bdd_handlers.go          # BDD used-tables registry CRUD endpoints
    bdd_catalog_proxy.go     # Read-only proxy to upstream Hellopro BDD catalog
    bdd_dto.go               # BDD request/response models (used tables + fields)
    dto.go                   # Server request/response models
    token_dto.go             # Token request/response models
    oauth2_dto.go            # OAuth2 client request/response models
    middleware.go            # Logging, recovery, JSON content-type middleware
    openapi.go               # OpenAPI 3.0 spec generation
  bddcatalog/
    client.go                # Read-only HTTP client for upstream Hellopro BDD catalog
    types.go                 # Catalog DTOs (databases, tables, fields)
  auth/
    handlers.go              # Login/logout endpoints
    jwt.go                   # JWT signing & validation
    middleware.go            # Auth middleware
    session.go               # Session management
  config/
    config.go                # Env-var configuration loader
  crypto/
    encrypt.go               # AES-256-GCM encrypt/decrypt for auth headers
  db/
    models.go                # GORM models (11 tables)
    mysql.go                 # MySQL connection, pooling, auto-migration
  gateway/
    gateway.go               # Core MCP routing logic
    registry.go              # In-memory backend server registry
    scoped_gateway.go        # Scope-token filtered gateway view
    neo4j_access.go          # Service-level gate on restricted servers — Neo4j template instances and hellodata (admin OR grant)
  health/
    checker.go               # Background health check loop (30s interval)
  mcp/
    types.go                 # MCP/JSON-RPC 2.0 type definitions
    capabilities.go          # Capability aggregation across backends
  authserver/                    # OAuth2 Authorization Server (MCP spec-compliant)
    handler.go               # AuthServer struct, route registration
    metadata.go              # GET /.well-known/oauth-authorization-server (RFC 8414)
    authorize.go             # GET/POST /authorize — login + consent flow
    token_endpoint.go        # POST /token — auth code exchange, client creds, refresh
    register.go              # POST /register — dynamic client registration (RFC 7591)
    consent.go               # Consent scope helpers, CSRF token generation
    server_access.go         # Consent-screen server visibility (Neo4j / hellodata access gate)
    pkce.go                  # PKCE S256 challenge/verifier verification
    codes.go                 # Authorization code generation + SHA-256 hashing
    templates/
      login.html             # OAuth2 login form (hellopro.fr auth)
      consent.html           # Server/tool consent screen
  oauth2/                        # Resource Server (bearer token validation only)
    credentials.go           # OAuth2 client_id + client_secret generation
    token.go                 # JWT access token issuance & validation
    middleware.go            # Combined Bearer + scope token middleware (401 + WWW-Authenticate)
    cache.go                 # In-memory client scope cache
  repository/
    server_repo.go           # Server CRUD over GORM
    token_repo.go            # Token CRUD over GORM
    oauth2_repo.go           # OAuth2 client CRUD over GORM
    authcode_repo.go         # Authorization code CRUD
    consent_repo.go          # Per-client per-user consent CRUD
    refresh_repo.go          # Refresh token CRUD
    bdd_used_repo.go         # BDD used-tables + fields registry CRUD over GORM
  scopetoken/
    generate.go              # Token generation & SHA-256 hashing
    cache.go                 # In-memory token cache
    middleware.go            # Scope token validation middleware
  transport/
    sse.go                   # SSE transport (GET /sse, POST /message)
    streamable_http.go       # Streamable HTTP transport (POST /mcp)
    http_backend.go          # Backend MCP client
    types.go                 # Transport interfaces
  ui/
    handler.go               # Embedded web UI handler
    static/                  # Frontend assets (embedded via Go embed)
init-db/
  init-mcp-gateway-db.sql   # Database initialization script
go.mod                       # Module definition & dependencies
Dockerfile                   # Multi-stage build
```

## API Endpoints

### Server Management (`/api/v1/`)
- `GET/POST /servers` — List / create MCP servers
- `GET/PUT/DELETE /servers/{id}` — Get / update / delete server
- `POST /servers/{id}/enable|disable` — Toggle server state
- `POST /servers/{id}/tools/{toolName}/enable|disable` — Toggle individual tool active state
- `POST /servers/{id}/discover` — Re-discover single server capabilities
- `POST /servers/discover-all` — Re-discover all active servers
- `POST /servers/import` — Import from `.mcp.json` file

### Aggregated Views
- `GET /tags` — Distinct tags across servers
- `GET /tools` — All tools from all servers
- `GET /resources` — All resources from all servers
- `GET /prompts` — All prompts from all servers

### Scope Tokens
- `GET/POST /tokens` — List / create tokens
- `GET/PUT/DELETE /tokens/{id}` — Get / update / delete token
- `POST /tokens/{id}/revoke` — Revoke token

### OAuth2 Clients
- `GET/POST /oauth2/clients` — List / create OAuth2 clients
- `GET/PUT/DELETE /oauth2/clients/{id}` — Get / update / delete client
- `POST /oauth2/clients/{id}/revoke` — Revoke client

### LLM Instructions (`/api/v1/`)
- `GET/POST /llm-instructions` — list (optional `?server_ids=csv` filter) / create
- `GET/PUT/DELETE /llm-instructions/{id}` — detail / update / delete
- `GET /llm-instructions/{id}/usage` — list tokens + OAuth2 clients that reference this instruction

### Leexi proxy (used by token / OAuth2 client creation forms)
- `GET /api/v1/leexi/users` — List Leexi workspace users (proxied from mcp-leexi-service `/admin/users`)
- `GET /api/v1/leexi/teams` — List Leexi teams (derived from the user payload)

Both routes return 503 when the integration is not configured (LEEXI_INTERNAL_URL or LEEXI_ADMIN_TOKEN unset).

### Ringover proxy (symmetric to Leexi)
- `GET /api/v1/ringover/users` — List Ringover users (proxied from mcp-ringover-service `/admin/users`)
- `GET /api/v1/ringover/teams` — List Ringover teams (derived from the user payload; each team is `{id:int, name:string}`)

Both routes return 503 when `RINGOVER_INTERNAL_URL` or `RINGOVER_ADMIN_TOKEN` is unset.

### BDD Hellopro Registry (admin only, `/api/v1/`)
```
GET    /bdd/catalog/databases                              — Read-only proxy: 3 Hellopro DBs
GET    /bdd/catalog/databases/{db}/tables                  — Read-only proxy: catalog tables
GET    /bdd/catalog/databases/{db}/tables/{tid}/fields     — Read-only proxy: catalog fields
GET    /bdd/used/tables                                     — List registered tables (`?database_id=...&search=...&page=N&limit=M`, default page=1, limit=20, cap 100). Response: `{tables, total, page, limit}`. Ordering: `created_at DESC, table_name ASC`.
POST   /bdd/used/tables                                     — Register a table + selected fields
POST   /bdd/used/tables/bulk                                — Atomic multi-create (cap 50 items)
GET    /bdd/used/tables/export                              — JSON download of full registry
POST   /bdd/used/tables/import                              — Upsert from JSON (cap 1 MiB)
GET    /bdd/used/tables/{id}                                — Get one with fields
PATCH  /bdd/used/tables/{id}                                — Update curated description
DELETE /bdd/used/tables/{id}                                — Remove from registry (cascades fields)
POST   /bdd/used/tables/{id}/fields                         — Add a field
PATCH  /bdd/used/tables/{id}/fields/{fid}                   — Update curated description
DELETE /bdd/used/tables/{id}/fields/{fid}                   — Remove a field
```

Catalog routes return **503** when `BDD_CATALOG_BASE_URL` / `BDD_CATALOG_TOKEN` are unset. All `/api/v1/bdd/*` routes are admin-gated.

### OAuth2 Authorization Server (public, no admin auth — MCP spec-compliant)
- `GET /.well-known/oauth-authorization-server` — Server metadata discovery (RFC 8414)
- `GET/POST /authorize` — Authorization Code flow: login + consent screen
- `POST /token` — Token exchange: authorization_code (+ PKCE), client_credentials, refresh_token
- `POST /register` — Dynamic Client Registration (RFC 7591)

### MCP Transports (require `Authorization: Bearer` or `X-MCP-Scope-Token`, returns 401 with `WWW-Authenticate` if missing)
- `GET /sse` — Open SSE stream
- `POST /message?sessionId={id}` — Send JSON-RPC over SSE
- `POST /mcp` — Streamable HTTP JSON-RPC

**Auth header precedence on MCP transports:**
1. `X-MCP-Scope-Token: mcp_…` wins outright when present.
2. Otherwise `Authorization: Bearer <token>` is dispatched by prefix:
   - Starts with `mcp_` → validated as a `/tokens`-issued scope token (same pipeline as `X-MCP-Scope-Token`). Rejection emits **no** `WWW-Authenticate` header.
   - Otherwise → validated as an OAuth2 access token (JWT, HS256). Rejection emits `WWW-Authenticate: Bearer error="invalid_token"`.
3. Neither present → 401 + `WWW-Authenticate: Bearer resource_metadata="…"`.

Scope-token accepts and rejects log a `source=x-mcp-scope-token|bearer` tag; Slack `UnauthorizedEvent` reasons carry the same tag.

### Template Catalog (`/api/v1/`)
- `GET /templates` — list available templates (seeded: GA4, GSC, Neo4j) with live instance counts
- `GET /templates/{slug}` — template detail
- `GET /templates/export` — download the full catalog as JSON (active + inactive)
- `POST /templates/import` — upsert templates from JSON (slug-keyed, transactional, no instances)
- `GET/POST /template-instances` — list / create instance (POST is multipart: template_slug, name, extra_env JSON, plus a credentials file (Google runner) or neo4j_uri / neo4j_username / neo4j_password / neo4j_database fields (Neo4j runner))
- `GET/DELETE /template-instances/{id}` — detail / remove (DELETE kills runner subprocess + removes mcp_servers row)
- `POST /template-instances/{id}/restart` — respawn subprocess
- `POST /template-instances/{id}/rotate-credentials` — replacement credentials (SA JSON, or Neo4j fields + optional extra_env) + respawn; a Neo4j rotate is persisted only after the runner pre-check accepted it (422 otherwise, DB and running instance untouched)
- Runner error bodies are never logged or stored verbatim: logs and `RunnerLastError` carry a summary only (status + error code, no body). The Neo4j runner's request-validation 422 does not echo request input.

### Zoho Imports Admin (`/api/v1/`)
- `GET/POST/DELETE /api/v1/zoho-imports/admin` — manage the singleton admin Zoho row consumed by `mcp-zoho-service`. POST upserts (201 on create, 200 on update); GET returns the row with `auth_headers` keys redacted; DELETE clears.
- `GET /api/v1/zoho-imports` — paginated list of all Zoho rows (admin + users). Query params: `is_admin=true|false`, `search=<substring on name or created_by>`, `page=N`, `limit=M` (default 1/20, max 100). `auth_headers` are redacted to header key names.
- `POST /api/v1/zoho-imports` — create a per-user import row. Body: `{name, url, created_by, auth_headers?, is_active?, template_slug?}`. Returns 201 + row DTO on success, 400 on missing/malformed fields, 409 when `created_by` already has a row. Singleton admin rows still use `POST /api/v1/zoho-imports/admin`.
- `GET /api/v1/zoho-imports/{id}` — fetch one row (same DTO shape as list items).
- `PATCH /api/v1/zoho-imports/{id}` — partial update. Body fields all optional: `name`, `url`, `auth_headers` (replaces blob; `{}` clears it), `is_active`. Empty body → 400. `is_admin` and `created_by` are not editable here.
- `DELETE /api/v1/zoho-imports/{id}` — hard delete a per-user row (204). Returns 400 when the target is the singleton admin row (use `/api/v1/zoho-imports/admin` for that).
- `POST /api/v1/zoho-imports/{id}/test` — server-side `POST tools/list` probe against the row's upstream URL with decrypted headers, 10s timeout. Returns `{ok, status_code?, latency_ms, error?}`. Logs only the row ID + caller email (never the URL or headers).
- `GET /api/v1/zoho-imports/{id}/tools` — list the persisted tool catalog for one row. Body: `{tools: [{name, description, input_schema, updated_at}], total}`. Returns 200 (empty list when catalog empty), 404 when the row is missing. Read-only — refresh the catalog via `POST /api/v1/zoho-imports/{id}/discover`.

### Internal Sync (shared-secret auth via `X-Admin-Token`)
- `POST /api/v1/internal/runner/sync` — a runner's pull of its desired instances — the X-Admin-Token identifies the runner (Google or Neo4j) and only that runner's instances are returned (decrypted credentials)
- `POST /api/v1/internal/users/sync` — account-service-backend pushes its users; gateway creates missing `gateway_users` (role `config-only`, `is_allowed=false`) and returns `{created, skipped}`. Token: `ACCOUNT_INTERNAL_TOKEN`.

### Other
- `GET /health` — Health probe
- `GET /openapi.json` — OpenAPI spec

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_PORT` | `8592` | Server listen port |
| `MCP_GATEWAY_NAME` | `hellopro-mcp-gateway` | Gateway display name |
| `MCP_GATEWAY_VERSION` | `0.1.0` | Reported version |
| `MCP_BACKEND_SERVERS` | — | Comma-separated legacy backend URLs |
| `MYSQL_DSN` | — | MySQL connection string |
| `ENCRYPTION_KEY` | — | Hex-encoded 32-byte AES-256 key |
| `HEALTH_CHECK_INTERVAL` | `30` | Seconds between health checks |
| `JWT_SECRET` | — | JWT signing secret |
| `JWT_ALGO` | `HS256` | JWT algorithm |
| `JWT_AUDIENCE` | `https://www.hellopro.fr` | JWT audience claim |
| `AUTH_URL` | — | External auth redirect URL |
| `AUTH_ENABLED` | `true` | Require login (set to "false" to disable) |
| `GATEWAY_PUBLIC_URL` | — | Public URL for OAuth2 metadata issuer and WWW-Authenticate header (required for OAuth2) |
| `OAUTH2_ACCESS_TOKEN_TTL` | `3600` | Default access token lifetime in seconds (overridable per client) |
| `OAUTH2_REFRESH_TOKEN_TTL` | `2592000` | Refresh token lifetime in seconds (default 30 days) |
| `ALLOW_INTERNAL_URLS` | `false` | Set to `true` to allow Docker-internal/private IP ranges (172.x.x.x, 10.x.x.x, etc.) as backend URLs — required when gateway and backends share a Docker network |
| `LEEXI_INTERNAL_URL` | — | In-cluster URL of mcp-leexi-service (e.g. `http://mcp-leexi-service:8589`). Required for Leexi-scoped tokens. |
| `LEEXI_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to mcp-leexi-service `/admin/*`. Must match `MCP_LEEXI_ADMIN_TOKEN` on the Leexi side. |
| `RINGOVER_INTERNAL_URL` | — | In-cluster URL of mcp-ringover-service (e.g. `http://mcp-ringover-service:8586`). Required for Ringover-scoped tokens. |
| `RINGOVER_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to mcp-ringover-service `/admin/*`. Must match `MCP_RINGOVER_ADMIN_TOKEN` on the Ringover side. |
| `BDD_CATALOG_BASE_URL` | — | Read-only upstream Hellopro BDD catalog URL (e.g. `https://test.hellopro.fr/admin/repertoire_test/moulinettes_interne/api_mcp`). Required for catalog proxy. |
| `BDD_CATALOG_TOKEN`    | — | Shared secret sent as `X-Admin-Token` to the upstream catalog. Required alongside `BDD_CATALOG_BASE_URL`. |
| `GOOGLE_TEMPLATES_RUNNER_URL` | — | In-cluster URL of mcp-google-templates-runner (e.g. `http://mcp-google-templates-runner:8595`). Required to spawn Google-runner template instances (ga, gsc). |
| `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for the runner admin API (sent as `X-Admin-Token`). The runner uses the SAME value when calling back via `/api/v1/internal/runner/sync`. |
| `NEO4J_TEMPLATES_RUNNER_URL` | — | In-cluster URL of mcp-template-neo4j-service (e.g. `http://mcp-template-neo4j-service:8598`). Required to spawn Neo4j template instances. |
| `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for the Neo4j runner (both directions). **Must differ** from `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` — the sync endpoint uses it to tell the runners apart; equal tokens disable the Neo4j runner at boot. |
| `SLACK_WEBHOOK_URL` | — | Slack incoming-webhook URL (`https://hooks.slack.com/services/...`). Empty = notifications disabled. |
| `SLACK_ENV_LABEL` | — | Optional prefix shown on every message (e.g. `prod`, `staging`). |
| `SLACK_AUTH_ALERT_COOLDOWN` | `600` | Seconds between duplicate unauthorized alerts per (ip, endpoint). `0` disables the cooldown. |
| `ZOHO_INTERNAL_URL` | — | In-cluster URL of mcp-zoho-service (e.g. `http://mcp-zoho-service:8596`). Reserved for future health checks. |
| `ZOHO_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to mcp-zoho-service. Must match `ZOHO_GATEWAY_TOKEN` on the service side. |
| `ZOHO_STUB_SERVER_ID` | — | UUID of the gateway's `mcp_servers` row whose URL points at `mcp-zoho-service`. Captured by the operator and pasted into `.env`; required by the service to gate admin grants. |

## Database

**MySQL** with GORM auto-migration. 25 tables:

| Table | Purpose |
|---|---|
| `mcp_servers` | Backend servers (name, URL, health, capabilities, `min_role` access gate) |
| `templates` | Template catalog (seed: `ga` GA4, `gsc` GSC, `neo4j` Neo4j) — stdio_command, default_env with `{instance_id}` placeholder, required_extra_env schema, and runner (`google` or `neo4j`) |
| `template_instances` | One row per template instance — encrypted credentials (SA JSON or Neo4j connection JSON), credentials_hash, runner_port/status, FK to `mcp_servers.id` |
| `server_tools` | Tools per server (name, description, inputSchema, is_active) |
| `server_resources` | Resources per server (URI, name, mimeType) |
| `server_prompts` | Prompts per server |
| `prompt_arguments` | Arguments for each prompt |
| `server_tags` | Tags for organizing servers |
| `scope_tokens` | Access tokens (SHA-256 hashed) |
| `scope_token_servers` | Join table: token ↔ allowed servers |
| `scope_token_tools` | Join table: token ↔ allowed tools per server |
| `oauth2_clients` | OAuth2 clients (client_id, secret, redirect_uris, grant_types, scope) |
| `oauth2_client_servers` | Join table: client ↔ allowed servers |
| `oauth2_client_tools` | Join table: client ↔ allowed tools per server |
| `oauth2_authorization_codes` | Short-lived auth codes (PKCE, 10-min expiry, single-use) |
| `oauth2_refresh_tokens` | Refresh tokens (SHA-256 hashed, 30-day TTL, rotation) |
| `oauth2_consents` | Per-client per-user consent decisions |
| `llm_instructions` | Reusable LLM instruction snippets (title, body, description) rendered into the MCP `initialize` response |
| `llm_instruction_servers` | Many-to-many: which servers an instruction applies to |
| `scope_token_instructions` | Many-to-many: which instructions a scope token injects |
| `oauth2_client_instructions` | Many-to-many: which instructions an OAuth2 client injects |
| `bdd_used_tables` | Gateway-curated registry of MySQL tables exposed to MCP (one per DB) |
| `bdd_used_fields` | Per-table field selection with curated descriptions |
| `scope_token_bdd_tables` | Join: scope token ↔ allowed BDD used-tables |
| `oauth2_client_bdd_tables` | Join: OAuth2 client ↔ allowed BDD used-tables |
| `zoho_imports` | Per-user (and admin singleton) Zoho upstream URLs consumed by mcp-zoho-service for routing |

Connection pooling: max 25 open, 5 idle connections.

## Conventions

- Standard library `net/http` for routing (no third-party router).
- Repository pattern for database access over GORM.
- In-memory registry for fast tool/resource/prompt → backend lookup.
- Middleware chain: logging → recovery → JSON content-type → auth → combined OAuth2/scope token.
- Context propagation for scope tokens and auth state.
- Graceful shutdown (10s drain) on SIGINT/SIGTERM.
- Encryption is optional: runs without `ENCRYPTION_KEY`, but auth headers are stored in plaintext.
- Tools have an `is_active` flag (default `true`). Inactive tools are excluded from token scope selection in the UI. Tool active state is preserved across server rediscovery.
- **Server-level full-access grants (admin)**: the `server_authorizations` table joins (`mcp_servers.id`, `email`). A grant carries two meanings depending on the backend. On **filtered** backends (Leexi, Ringover, BDD) it means "unfiltered access". On **identified** backends (Zoho, hellodata) and on Neo4j template instances it means "right of access". When a request's bearer-token email has a row for the targeted backend, the gateway skips ALL filter-header injection (Leexi, Ringover, BDD, Zoho) — the backend receives only the static auth headers and treats the call as unrestricted. Exceptions that keep identity headers on a grant: Zoho (`injectZohoIdentity`) and hellodata (`injectHellodataIdentity` with `X-End-User-Granted: true`). Grants are managed via the admin-only `/api/v1/server-authorizations` REST endpoints and the "Serveur Autorisation" Vue admin page. Per-server granularity (a grant on `srv-1` does not affect `srv-2`). Client-credentials grants (no email) never match a row → grant table is irrelevant to non-human flows. Resolution order at `requestHeadersFor`: Step 0 server-authorization grant → Step 1 auto-self override → Step 2 admin-configured filter.
- **Per-server access gate (`mcp_servers.min_role`)**: empty (the default, and the value every pre-existing server carries) means public. Set to `config-only` / `read-only` / `admin` to require at least that `gateway_users.role` — **or** a `server_authorizations` grant on that server: access is "role >= min_role OR grant" (`gateway.GateOrGrantAllowsEmail`, `ScopedGateway.minRoleAllows`; the consent screens get the grant repo via `AuthServer.SetGrantChecker`). A grant needs an end-user email, so scope tokens and `client_credentials` stay gated. Enforced by one fail-closed predicate (`gateway.GateAllowsEmail` / `gateway.GateAllows`, `internal/gateway/access_gate.go`): `renderConsent` and `buildServerList` drop the server from the OAuth2 consent screen; `ScopedGateway.handleToolsList`, `handleResourcesList` and `handlePromptsList` omit its tools/resources/prompts; `ScopedGateway.handleToolsCall`, `handleResourcesRead` and `handlePromptsGet` each return an MCP error (logged with the resolved backend, required role and caller email) instead of forwarding the call. A gated server is unreachable — across all six of those verbs — for **every** `mcp_…` scope token and **every** `client_credentials` grant, because neither ever carries an end-user email on the request context — the single condition that also excludes them. An unwired user repository, a missing/unknown email, an unrecognised `min_role` value, or a repository error all deny; only an empty `min_role` allows without a successful role lookup. Granularity is the server, never the tool; `isAdminOnly` / `isReadOnlyPlus` on the browser REST API are untouched — this gates the MCP surface only. Editable from the Servers form ("Niveau d'accès requis", admin-only session). **Maintenance note:** the gate reads `BackendServer.MinRole` off the in-memory registry, not the DB row, so `min_role` must be re-pushed at every path that (re-)registers a backend or the gate silently falls open. This is an invariant, not a fixed count — the count has been wrong here three times as registration paths were added without updating it, so it is not restated as a number. Known re-registration paths at time of writing: the health checker's periodic re-discovery (`internal/health/checker.go` `checkOne`, which pushes `MinRole` unconditionally after every successful (re-)discovery — this also covers the case where the registry had no prior entry at all, e.g. a gated server created with auto-discover unchecked), and the call sites in `internal/api/server_handlers.go` — `handleCreateServer`, `handleUpdateServer` (**PUT only**, not PATCH: once immediately on the request, and again after its own URL/auth-header-triggered re-discovery, since `Unregister` drops the registry's `prev` entry), `handleEnableServer`, `handleDiscoverServer` — plus `handleDiscoverAll` in `internal/api/handler.go`. Three further call sites (`internal/api/import_handler.go`, `internal/api/google_handlers.go`, `internal/api/template_handlers.go`) register backends without pushing `MinRole`; this is harmless today because none of those import/template flows can set `min_role` in the first place (DB value and registry both default to `""`), but each carries a code comment flagging it as a known gap. **Anyone adding a new path that registers or re-registers a backend must add a `SetMinRole` push there, or update one of these comments if `min_role` becomes settable on a path that currently can't set it.** Tests: `internal/gateway/access_gate_test.go`, `internal/gateway/min_role_grant_test.go`, `internal/gateway/registry_min_role_test.go`, `internal/gateway/scoped_gateway_gate_test.go`, `internal/authserver/consent_gate_test.go`, `internal/api/min_role_dto_test.go`, `internal/api/min_role_registration_regression_test.go`, `internal/health/min_role_regression_test.go`.
- **Neo4j template instance and hellodata access gate**: a backend whose `mcp_servers.template_slug` names a template with `runner = "neo4j"` (inactive templates included), or whose `tool_prefix` is `hellodata` (mcp-hellodata-service, buyer exports — spec `docs/superpowers/specs/2026-09-28-mcp-hellodata-server-authorizations-design.md`), is visible and callable only by gateway admins (`gateway_users.role = "admin"` with `is_allowed = true` — an admin disabled on the Users page is not treated as admin) and by emails holding a `server_authorizations` row for that exact instance — for Neo4j instances a grant therefore *opens* access, on top of its "unfiltered" meaning for filtered backends. Everybody else, including every caller without an end-user email (`mcp_…` scope tokens, `client_credentials`), gets the instance omitted from `tools/list` / `resources/list` / `prompts/list` and a JSON-RPC `-32600` `access denied: this server requires an admin role or a server authorization` on `tools/call` / `resources/read` / `prompts/get` (never forwarded, logged with backend id, template slug and email). The OAuth2 consent screens (`renderConsent`, `buildServerList`) hide the instance, and both consent submissions (`POST /authorize`, `POST /api/v1/oauth2/authorize/consent`) drop it from the stored scope. `initialize` omits every `per_server` LLM instruction none of whose linked servers is visible to the caller (so a hidden instance's schema text never leaks); `general` instructions are kept. Fail-closed: lookup errors make the instance restricted: only admins and holders of a grant on it get through; a user-lookup error means not-admin. A `template_slug` with no template row is restricted too (cached like a real answer, logged once per TTL). The slug and the tool prefix are read from `mcp_servers` by id (`ServerRepo.AccessKeysByID`) because the registry's `BackendServer.TemplateSlug` is empty after a successful discovery and the consent submissions only hold a server id. Caches (60 s): server id → (slug, tool prefix), slug → is-Neo4j; roles and grants are read on every request, so revoking a grant applies on the next request. Unrelated to the per-instance `NEO4J_READ_ONLY` flag (database-level) and to the static `mcp-neo4j-service` (no `template_slug`, unaffected). Implementation: `gateway.Neo4jAccess`, wired in `internal/app/app.go` into `Gateway.SetNeo4jAccess` and `AuthServer.SetServerAccess`.
- **hellodata backend** (`tool_prefix == "hellodata"`, mcp-hellodata-service): access is decided by the gate above. `min_role` may be `admin`: a grant satisfies `min_role` on its server, so a `config-only` grant holder (the role `users/sync` gives by default) still gets through, and only admins pass without a grant. Email-less paths stay excluded either way. Beware `readonly` (no hyphen, not a role): it denies everyone without a grant, admins included. Its catalog depends on the caller, so `handleToolsList` live-fetches it with the caller's identity (`fetchHellodataTools`) and falls back to an **empty** list on error — never to the registry cache, which is always empty for this backend (discovery runs without identity). The **DB** catalog shown on `/servers` is different: when an admin drives a discovery through the admin API (create, update, enable, discover, discover-all, import, templates), `saveBackendCapabilities` re-fetches the list with that admin's `X-End-User-Email` + `X-End-User-Role: admin` and persists it (`internal/api/hellodata_catalog.go`); a non-admin caller, a failed fetch or an empty answer keep the tools already stored, so they are never wiped and no ToolsRegression fires. The registry is not touched by this. Tests: `internal/api/hellodata_catalog_test.go`. For the same reason `handleToolsCall` routes a `hellodata_*` name that misses the registry to the in-scope hellodata backend (`findHellodataFallback`), before the Zoho fallback; min_role and the access gate then apply. Headers sent: `X-End-User-Email`, `X-End-User-Role` (only when resolved) and `X-End-User-Granted: true` (only when the caller holds a grant on that server, also on the Step 0 path). The service re-checks `admin || granted`. Tests: `internal/gateway/hellodata_access_test.go`, `hellodata_identity_test.go`, `hellodata_toolslist_test.go`, `internal/authserver/consent_hellodata_test.go`.
- **Auto-self filter override (OAuth2 only)**: when an OAuth2 access token's `email` claim resolves to a user in the target backend (Leexi or Ringover), the gateway injects that user's UUID/ID into the outbound header automatically — bypassing whatever filter mode the admin set on the OAuth2 client. Per-backend independent: a user might exist in Leexi but not Ringover; each backend resolves on its own. When the email is present but has no match in this backend: gateway admins (`gateway_users.role = "admin"`) fall back to the admin-configured filter; non-admin users get the deny-sentinel (`00000000-0000-0000-0000-000000000000` for Leexi, `0` for Ringover). Client-credentials grants (no email) bypass the override and use the admin-configured mode as before.
- Scope tokens and OAuth2 clients carry an optional **Leexi ownership filter** (`LeexiFilterMode` + `LeexiAllowedUserUUIDs` + `LeexiAllowedTeamUUIDs`). When the filter is set and the request targets the Leexi-tagged backend (`ToolPrefix == "leexi"`), the gateway adds `X-Leexi-Allowed-Participants` to the outbound MCP request. mcp-leexi-service then enforces the scope server-side. See `internal/leexiadmin/` for the user/team resolution and cache (5 min TTL).
  - Filter modes: `none` (unrestricted), `users`, `teams`, `creator` (frozen at create time from creator email), `self` (per-request, OAuth2 clients only — resolves the access-token `email` claim via `leexiadmin.FindUserByEmail` on every call). `self` is rejected for scope tokens (no end-user identity) and fails closed for `client_credentials` grants (no email claim).
- Scope tokens and OAuth2 clients carry an optional **Ringover ownership filter** mirroring the Leexi one — same five modes (`none`/`users`/`teams`/`creator`/`self`), but Ringover identifies users via integer `user_id` instead of UUIDs. When set on a request to a Ringover-tagged backend (`ToolPrefix == "ringover"`), the gateway adds `X-Ringover-Allowed-User-IDs` (comma-separated ints, deny-sentinel `0`). See `internal/ringoveradmin/` for the user/team resolution and cache (5 min TTL).
- Scope tokens and OAuth2 clients carry an optional **BDD scope filter** (`bdd_filter.used_table_ids`). When the filter is non-empty and the request targets a backend with `ToolPrefix == "bdd"`, the gateway resolves the IDs against `bdd_used_tables` and adds `X-BDD-Allowed-Tables: [{"database_id":int,"table_name":str}, ...]` to the outbound MCP request. **Fail-closed**: if the filter is set but every referenced row was deleted, the gateway emits `[]` so the upstream BDD MCP backend denies all calls. Empty/absent filter = full access.
- **Zoho ownership filter**: scope tokens and OAuth2 clients carry an optional Zoho filter (`ZohoFilterMode` + `ZohoAllowedEmails`). Resolution at `requestHeadersFor`: Step 0 server-authorization grant → **Step 1 imported-server auto-filter** (when `backend.ToolPrefix == "zoho"` AND `backend.TemplateSlug != ""` AND `backend.CreatedBy != ""`, inject `X-Zoho-Allowed-User: <created_by>`) → Step 2 admin-configured filter (modes: `none` no header, `users` comma-joined emails, `creator` single email = token/client `created_by`). Deny sentinel `deny-all@hellopro.fr.deny` is injected when an admin filter resolves to an empty allow-list. The Zoho MCP backend enforces the header server-side. **Per-user routing** to the user's imported Zoho instance is handled by the dedicated `mcp-zoho-service` (port 8596) — the gateway sees that service as one Zoho backend and the service picks the right upstream from `X-End-User-Email` / `X-End-User-Login` headers the gateway always injects on Zoho-tagged calls. The per-user Zoho upstream URLs now live in the dedicated `zoho_imports` table (managed by the sheet-import handler and the admin endpoint `POST /api/v1/zoho-imports/admin`); `mcp_servers` keeps only the stub row pointing at `mcp-zoho-service`. **Per-user `tools/list`**: when the request carries an end-user identity AND the scope contains a Zoho-tagged backend, `handleToolsList` live-fetches the tool catalog from `mcp-zoho-service` with the identity headers so the client sees the user's own Zoho tools (catalog scoped to the user's upstream) instead of the cached admin catalog. Non-Zoho tools still come from the registry merge; the Zoho live-fetch fails open back to the cached admin tools on upstream error. **Per-user consent screen**: the OAuth2 `/authorize` consent UI applies the same override — `buildServerList` (JSON API) and `renderConsent` (HTML) call `Gateway.FetchZohoToolsForUser(ctx, email)` once after assembling the cached server list, then substitute the per-user tools for every Zoho-tagged server. The catalog is sourced from the persisted `zoho_import_tools` table via `gateway.ZohoUserCatalog` (wired in `app.go` to a `*repository.ZohoImportRepo` adapter that resolves email → user row → admin row fallback). Discovery refreshes the catalog on (1) sheet-import row create, (2) successful `POST /api/v1/zoho-imports/{id}/test`, and (3) manual `POST /api/v1/zoho-imports/{id}/discover`. Anonymous browsers, missing rows, and empty catalogs all leave the cached admin tools in place.
- The catalog (`tbl_sauvegarde_tables` / `tbl_sauvegarde_champs`) is owned by the upstream Hellopro BDD admin API at `BDD_CATALOG_BASE_URL` — gateway is read-only against it. The "used tables" registry (gateway-curated subset + descriptions) lives in the gateway DB.
- OAuth2 Authorization Server is MCP spec-compliant: OAuth 2.1, RFC 8414 (metadata), RFC 7591 (dynamic registration), PKCE (S256).
- **OAuth2 `/authorize` login**: three-tier session resolution.
  1. Valid `mcp_session` cookie → render consent.
  2. Otherwise, valid `gw_session` cookie pointing to a non-expired `sso_sessions` row → bridge: mint `mcp_session` from the admin SSO row's email, render consent. No SSO roundtrip — admin already logged in.
  3. Otherwise, 303 to `/sso/login?purpose=oauth2&return_to=<full-authorize-URL>`. The same SSO `client_id`/`client_secret` as the admin UI is reused; the `purpose` query parameter tells `/sso/callback` to skip the admin upsert + `IsAllowed` check + `SSOSession` persistence + `gw_session` cookie, and instead set the `mcp_session` cookie via `internal/auth.SetSession` before redirecting back to the original `/authorize` URL so the consent screen can render.
  `client_credentials` grants are unaffected (they never hit `/authorize`).
- **LLM instructions** are reusable snippets (title + body) linked to servers. Scope tokens and OAuth2 clients each pick a subset; at MCP `initialize` time, the gateway emits the composed `## <title>\n<body>` blocks (`\n\n`-joined, capped at 8 KiB) into the spec-defined `instructions` field. Picks are validated server-side: every `instruction_id` must share at least one server with the token/client's allowed set. Resolution happens once per scope-cache-miss (60 s TTL); instruction edits additionally invalidate both scope caches for immediate visibility.
- **Instruction delivery via tool descriptions** (`oauth2_clients.inject_instructions_into_tools`, default `false`): some MCP hosts ignore the `initialize` `instructions` field (claude.ai web does; Claude Code honors it). When the flag is set on an OAuth2 client, the gateway instead appends the composed instruction blocks to tool descriptions in `tools/list` — `general` rows to every tool, `per_server` rows only to the owning server's tools (per-tool suffix capped at 4 KiB) — and omits the `initialize` field so spec-compliant hosts never see the text twice. Exposed as `inject_instructions_into_tools` on the OAuth2 client REST API and as a checkbox in the frontend's "Instructions LLM" section. Scope tokens do not support the flag. Implementation: `gateway.DecorateToolsWithInstructions` + `Registry.ToolServerIndex`.
- MCP endpoints return 401 + `WWW-Authenticate` header when no auth is provided, triggering Claude.ai's OAuth2 discovery flow.
- Unit tests in `internal/authserver/*_test.go`, `internal/oauth2/*_test.go`, `internal/repository/*_test.go`, `internal/db/mysql_test.go`, `internal/gateway/*_test.go`. Tests using `gorm.io/driver/sqlite` need cgo; new SQLite-backed tests use the pure-Go `github.com/glebarez/sqlite` with hand-written DDL (see `internal/authserver/consent_neo4j_test.go`) so they also run in `golang:1.24-alpine`.

### Slack notifications (`internal/slack/`)

Posts six event types to a Slack incoming webhook when `SLACK_WEBHOOK_URL` is set. Empty URL = silently disabled (local dev and existing deployments untouched).

| Event | Trigger |
|---|---|
| `ServerDown` | Health checker detects a backend transitioning to `unhealthy`. |
| `ServerUp` | Health checker detects a backend recovering (`unhealthy`/`unknown` → `healthy`), includes downtime duration. |
| `ToolsRegression` | `SaveDiscoveredCapabilities` sees `prevToolCount > 0 && len(newTools) == 0` for a server — fires from `api.Handler.saveBackendCapabilities`. |
| `Unauthorized` | OAuth2 or scope-token middleware returns 401/403 on an MCP endpoint (`/sse`, `/mcp`, `/message`). Rate-limited per (ip, endpoint) by `SLACK_AUTH_ALERT_COOLDOWN`. |
| `GatewayShutdown` | SIGINT/SIGTERM received in `main.go` before drain. |
| `GatewayPanic` | Best-effort: deferred recover() in the HTTP-server goroutine posts synchronously before exit. |

**Limitation:** The gateway cannot self-report SIGKILL, OOM, or hardware death — the process is already gone. For those, pair with an external watcher (Kubernetes liveness probe + alertmanager, or an uptime monitor polling `/health`).

**Dispatch:** `Notify` is non-blocking (buffered channel, size 64; overflow drops with a log line). `NotifySync` posts inline with a 2 s timeout — used only by panic / shutdown paths where the worker goroutine is about to die.

## What This Provides to Other Services

- **Unified MCP interface**: clients connect to one gateway instead of N individual MCP servers.
- **Capability aggregation**: merges tools, resources, and prompts from all registered backends.
- **Smart routing**: forwards `tools/call`, `resources/read`, `prompts/get` to the owning backend.
- **Access control**: scope tokens restrict which servers (and capabilities) a client can access.
- **Health monitoring**: background checks track backend availability and mark unhealthy servers.
- **Admin API**: REST endpoints to register, discover, enable/disable, and monitor MCP servers.
