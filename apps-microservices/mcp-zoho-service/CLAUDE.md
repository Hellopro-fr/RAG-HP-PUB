# mcp-zoho-service

Stateless Go proxy. The MCP gateway treats this service as a single Zoho MCP
backend. On each request, the service reads the caller's identity from
`X-End-User-Email` + `X-End-User-Login`, picks the right upstream Zoho URL
(admin's global one when the caller is in `server_authorizations`, else the
caller's imported per-user Zoho), decrypts the upstream's auth headers, and
proxies the JSON-RPC body.

## Tech Stack

- Go 1.24, `net/http` standard library (no third-party router)
- AES-256-GCM via `crypto/aes` + `crypto/cipher` — shared `ENCRYPTION_KEY` with gateway
- Reads gateway's MySQL read-only (`mcp_servers`, `server_authorizations`)
- Multi-stage Docker: `golang:1.24-alpine` → `alpine:3.20`, port **8596**

## Run

```bash
# Local (requires Go 1.24+ and a reachable MySQL with the gateway schema)
cd apps-microservices/mcp-zoho-service
ZOHO_ROUTER_PORT=8596 \
MYSQL_DSN="..." \
ENCRYPTION_KEY="..." \
ZOHO_GATEWAY_TOKEN="..." \
ZOHO_SELF_URL="http://mcp-zoho-service:8596/mcp" \
go run ./cmd/server
```

## API

| Endpoint | Purpose |
|---|---|
| `POST /mcp` | Receive MCP JSON-RPC from gateway, resolve upstream, proxy, relay response |
| `GET /health` | Liveness probe (200 once boot succeeds) |

All `POST /mcp` requests must carry `X-Admin-Token` matching `ZOHO_GATEWAY_TOKEN`.

## Resolution rules

1. Read `X-End-User-Email` + `X-End-User-Login` from request headers.
2. Look up the admin Zoho row in `mcp_servers` (`tool_prefix='zoho' AND template_slug='' AND url != ZOHO_SELF_URL AND is_active LIMIT 1`).
3. If the caller's email is in `server_authorizations` for that admin row → route to it.
4. Else look up the caller's imported Zoho (`tool_prefix LIKE 'zoho%' AND template_slug != '' AND is_active AND matches(created_by, email, login) ORDER BY created_at ASC LIMIT 1`).
5. Else return JSON-RPC error `-32001` "no_zoho_configured".

Matching tries exact-email (case-insensitive) first, then login-portion (local-part before `@`).

## Environment

| Variable | Default | Notes |
|---|---|---|
| `ZOHO_ROUTER_PORT` | `8596` | HTTP listen port |
| `MYSQL_DSN` | — | Read-only DB user recommended |
| `ENCRYPTION_KEY` | — | Hex 32-byte AES-256 key — must equal gateway's |
| `ZOHO_GATEWAY_TOKEN` | — | Shared bearer with gateway (`X-Admin-Token`) |
| `ZOHO_SELF_URL` | — | The URL the gateway calls this service on — used to exclude this service's own `mcp_servers` row when picking the admin upstream |
| `ZOHO_ROUTING_CACHE_TTL` | `60` | Seconds |
| `ZOHO_UPSTREAM_TIMEOUT` | `30` | Seconds — per outbound HTTP call to Zoho |
| `LOG_LEVEL` | `info` | `debug`/`info`/`warn`/`error` |

## Boundaries

This service does NOT:
- Store any state (no DB writes, no local files).
- Hold per-user OAuth tokens (deferred; auth headers live in `mcp_servers.auth_headers`).
- Validate JWTs (trusts the gateway-injected headers).
- Expose admin UI (operators use the gateway's `/servers` admin to register Zoho rows).

## What this provides to other services

- Single Zoho MCP endpoint that the gateway treats as one backend, hiding the per-user routing behind a stable URL.
