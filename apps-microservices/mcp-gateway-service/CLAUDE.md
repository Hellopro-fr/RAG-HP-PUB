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

### Template Catalog (`/api/v1/`)
- `GET /templates` — list available templates (seeded: GA4, GSC) with live instance counts
- `GET /templates/{slug}` — template detail
- `GET /templates/export` — download the full catalog as JSON (active + inactive)
- `POST /templates/import` — upsert templates from JSON (slug-keyed, transactional, no instances)
- `GET/POST /template-instances` — list / create instance (POST is multipart: template_slug, name, extra_env JSON, credentials file)
- `GET/DELETE /template-instances/{id}` — detail / remove (DELETE kills runner subprocess + removes mcp_servers row)
- `POST /template-instances/{id}/restart` — respawn subprocess
- `POST /template-instances/{id}/rotate-credentials` — upload replacement SA JSON + respawn

### Runner Sync (internal, shared-secret auth via `X-Admin-Token`)
- `POST /api/v1/internal/runner/sync` — runner's boot-time pull of desired instances (returns decrypted credentials)

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
| `GOOGLE_TEMPLATES_RUNNER_URL` | — | In-cluster URL of mcp-google-templates-runner (e.g. `http://mcp-google-templates-runner:8595`). Required to spawn template instances. |
| `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` | — | Shared secret for the runner admin API (sent as `X-Admin-Token`). The runner uses the SAME value when calling back via `/api/v1/internal/runner/sync`. |
| `SLACK_WEBHOOK_URL` | — | Slack incoming-webhook URL (`https://hooks.slack.com/services/...`). Empty = notifications disabled. |
| `SLACK_ENV_LABEL` | — | Optional prefix shown on every message (e.g. `prod`, `staging`). |
| `SLACK_AUTH_ALERT_COOLDOWN` | `600` | Seconds between duplicate unauthorized alerts per (ip, endpoint). `0` disables the cooldown. |

## Database

**MySQL** with GORM auto-migration. 25 tables:

| Table | Purpose |
|---|---|
| `mcp_servers` | Backend servers (name, URL, health, capabilities) |
| `templates` | Template catalog (seed: `ga` GA4, `gsc` GSC) — defines stdio_command, default_env with `{instance_id}` placeholder, and required_extra_env schema |
| `template_instances` | One row per admin-uploaded SA JSON — encrypted credentials, credentials_hash, runner_port/status, FK to `mcp_servers.id` |
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
- Scope tokens and OAuth2 clients carry an optional **Leexi ownership filter** (`LeexiFilterMode` + `LeexiAllowedUserUUIDs` + `LeexiAllowedTeamUUIDs`). When the filter is set and the request targets the Leexi-tagged backend (`ToolPrefix == "leexi"`), the gateway adds `X-Leexi-Allowed-Participants` to the outbound MCP request. mcp-leexi-service then enforces the scope server-side. See `internal/leexiadmin/` for the user/team resolution and cache (5 min TTL).
- Scope tokens and OAuth2 clients carry an optional **BDD scope filter** (`bdd_filter.used_table_ids`). When the filter is non-empty and the request targets a backend with `ToolPrefix == "bdd"`, the gateway resolves the IDs against `bdd_used_tables` and adds `X-BDD-Allowed-Tables: [{"database_id":int,"table_name":str}, ...]` to the outbound MCP request. **Fail-closed**: if the filter is set but every referenced row was deleted, the gateway emits `[]` so the upstream BDD MCP backend denies all calls. Empty/absent filter = full access.
- The catalog (`tbl_sauvegarde_tables` / `tbl_sauvegarde_champs`) is owned by the upstream Hellopro BDD admin API at `BDD_CATALOG_BASE_URL` — gateway is read-only against it. The "used tables" registry (gateway-curated subset + descriptions) lives in the gateway DB.
- OAuth2 Authorization Server is MCP spec-compliant: OAuth 2.1, RFC 8414 (metadata), RFC 7591 (dynamic registration), PKCE (S256).
- **LLM instructions** are reusable snippets (title + body) linked to servers. Scope tokens and OAuth2 clients each pick a subset; at MCP `initialize` time, the gateway emits the composed `## <title>\n<body>` blocks (`\n\n`-joined, capped at 8 KiB) into the spec-defined `instructions` field. Picks are validated server-side: every `instruction_id` must share at least one server with the token/client's allowed set. Resolution happens once per scope-cache-miss (60 s TTL); instruction edits additionally invalidate both scope caches for immediate visibility.
- MCP endpoints return 401 + `WWW-Authenticate` header when no auth is provided, triggering Claude.ai's OAuth2 discovery flow.
- Unit tests in `internal/authserver/*_test.go`, `internal/oauth2/*_test.go`, `internal/repository/*_test.go`, `internal/db/mysql_test.go`.

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
