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
2. Check `server_authorizations` for the gateway's stub server (UUID in `ZOHO_STUB_SERVER_ID`) + caller email. Granted?
3. Granted → `SELECT … FROM zoho_imports WHERE is_admin = 1 AND is_active = 1 LIMIT 1`. Hit → admin row's URL + decrypted headers. Miss → JSON-RPC `-32001` `no_admin_zoho_configured`.
4. Not granted → `SELECT … FROM zoho_imports WHERE is_admin = 0 AND is_active = 1 AND matches(created_by, email, login) ORDER BY created_at ASC LIMIT 1`. Hit → user row. Miss → JSON-RPC `-32001` `no_zoho_configured`.

Matching tries exact-email (case-insensitive) first, then login-portion (local-part before `@`).

## Environment

| Variable | Default | Notes |
|---|---|---|
| `ZOHO_ROUTER_PORT` | `8596` | HTTP listen port |
| `MYSQL_DSN` | — | Read-only DB user recommended |
| `ENCRYPTION_KEY` | — | Hex 32-byte AES-256 key — must equal gateway's |
| `ZOHO_GATEWAY_TOKEN` | — | Shared bearer with gateway (`X-Admin-Token`) |
| `ZOHO_SELF_URL` | — | The URL the gateway calls this service on — used to exclude this service's own `mcp_servers` row when picking the admin upstream |
| `ZOHO_STUB_SERVER_ID` | — | UUID of the gateway's `mcp_servers` stub row (the one whose URL points at this service). Required at boot; used by `IsAdminGranted` against `server_authorizations`. |
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

## Rollout

The new `zoho_imports` table replaces per-user data that previously lived in
`mcp_servers`. Operators run these steps after deploy:

1. Deploy: gateway boots, AutoMigrate creates `zoho_imports`.
2. Wipe prior Zoho imports from `mcp_servers` (stub row stays):
   ```sql
   DELETE FROM mcp_servers WHERE LOWER(tool_prefix) LIKE 'zoho%' AND template_slug <> '';
   ```
3. Register the admin Zoho via REST on the gateway:
   ```bash
   curl -X POST https://<gateway>/api/v1/zoho-imports/admin \
        -H "Authorization: Bearer <admin-jwt>" \
        -H "Content-Type: application/json" \
        -d '{"name":"Zoho CRM","url":"https://mcp.zoho.eu/<admin-id>","auth_headers":{"Authorization":"Bearer <admin-zoho-token>"}}'
   ```
4. Capture the stub row UUID:
   ```sql
   SELECT id FROM mcp_servers WHERE tool_prefix='zoho' AND template_slug='' AND url='http://mcp-zoho-service:8596/mcp' LIMIT 1;
   ```
   Paste into `.env` as `ZOHO_STUB_SERVER_ID=<uuid>` and restart `mcp-zoho-service`.
5. Re-run the `/templates` sheet-import wizard for the Zoho catalog row to recreate per-user rows.
6. Smoke: end-user A connects → tools come from A's row; admin-granted user → tools come from admin row.
