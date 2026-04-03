# mcp-gateway-service

Central MCP (Model Context Protocol) gateway that aggregates and routes requests across multiple backend MCP servers, providing unified tool/resource/prompt discovery and scoped access control.

## Tech Stack

- Go 1.24
- `net/http` (standard library) — HTTP server
- GORM v1.25 — ORM (MySQL driver)
- AES-256-GCM — encryption for stored auth headers
- JWT (HS256 via golang-jwt/jwt/v5) — authentication (enabled by default)
- Docker (multi-stage: golang:1.24-alpine → alpine:3.20), exposed port **8581**

## Run

```bash
# Local (requires Go 1.24+)
cd apps-microservices/mcp-gateway-service
go run ./cmd/server/

# Docker
docker build -t mcp-gateway-service .
docker run -p 8581:8581 -e MYSQL_DSN="..." mcp-gateway-service
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
    import_handler.go        # Import servers from .mcp.json
    dto.go                   # Server request/response models
    token_dto.go             # Token request/response models
    middleware.go            # Logging, recovery, JSON content-type middleware
    openapi.go               # OpenAPI 3.0 spec generation
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
    models.go                # GORM models (8 tables)
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
  repository/
    server_repo.go           # Server CRUD over GORM
    token_repo.go            # Token CRUD over GORM
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

### MCP Transports (optionally require `X-MCP-Scope-Token`)
- `GET /sse` — Open SSE stream
- `POST /message?sessionId={id}` — Send JSON-RPC over SSE
- `POST /mcp` — Streamable HTTP JSON-RPC

### Other
- `GET /health` — Health probe
- `GET /openapi.json` — OpenAPI spec

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_PORT` | `8581` | Server listen port |
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
| `SCOPE_TOKEN_REQUIRED` | `true` | Require scope token on MCP endpoints (set to "false" to disable) |
| `GATEWAY_PUBLIC_URL` | — | Public URL for generated .mcp.json snippets |

## Database

**MySQL** with GORM auto-migration. 8 tables:

| Table | Purpose |
|---|---|
| `mcp_servers` | Backend servers (name, URL, health, capabilities) |
| `server_tools` | Tools per server (name, description, inputSchema) |
| `server_resources` | Resources per server (URI, name, mimeType) |
| `server_prompts` | Prompts per server |
| `prompt_arguments` | Arguments for each prompt |
| `server_tags` | Tags for organizing servers |
| `scope_tokens` | Access tokens (SHA-256 hashed) |
| `scope_token_servers` | Join table: token ↔ allowed servers |

Connection pooling: max 25 open, 5 idle connections.

## Conventions

- Standard library `net/http` for routing (no third-party router).
- Repository pattern for database access over GORM.
- In-memory registry for fast tool/resource/prompt → backend lookup.
- Middleware chain: logging → recovery → JSON content-type → auth → scope token.
- Context propagation for scope tokens and auth state.
- Graceful shutdown (10s drain) on SIGINT/SIGTERM.
- Encryption is optional: runs without `ENCRYPTION_KEY`, but auth headers are stored in plaintext.
- No unit tests currently — tested via integration/E2E against running backends.

## What This Provides to Other Services

- **Unified MCP interface**: clients connect to one gateway instead of N individual MCP servers.
- **Capability aggregation**: merges tools, resources, and prompts from all registered backends.
- **Smart routing**: forwards `tools/call`, `resources/read`, `prompts/get` to the owning backend.
- **Access control**: scope tokens restrict which servers (and capabilities) a client can access.
- **Health monitoring**: background checks track backend availability and mark unhealthy servers.
- **Admin API**: REST endpoints to register, discover, enable/disable, and monitor MCP servers.
