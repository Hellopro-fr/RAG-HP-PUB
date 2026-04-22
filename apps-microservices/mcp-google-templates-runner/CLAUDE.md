# mcp-google-templates-runner

Python sidecar that hosts stdio MCP servers spawned by the gateway's Templates feature. One `mcp-proxy` subprocess per uploaded service-account JSON, each on a dynamic port in the 15000–15099 pool, supervised per-instance.

## Tech Stack

- Python 3.11, FastAPI, Uvicorn, asyncio
- `mcp-proxy` wraps stdio MCP servers into SSE/HTTP
- Upstream packages: `analytics-mcp` (GA4), `mcp-gsc` (Search Console)

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_URL` | — | Base URL of mcp-gateway-service for startup sync |
| `MCP_GATEWAY_ADMIN_TOKEN` | — | Shared secret sent as `X-Admin-Token` to the gateway |
| `RUNNER_ADMIN_TOKEN` | — | Required `X-Admin-Token` on incoming `/admin/*` requests |
| `RUNNER_PORT` | `8594` | Admin API port (8590 was already taken by qc-tracking-service) |
| `RUNNER_INSTANCE_PORT_START` | `15000` | First port in the dynamic pool |
| `RUNNER_INSTANCE_PORT_END` | `15099` | Last port in the dynamic pool |
| `SECRETS_DIR` | `/tmp/secrets` | Tmpfs dir for per-instance credential files |

## Admin API (X-Admin-Token)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/health` | Liveness (no auth) |
| `GET` | `/admin/instances` | List running instances |
| `POST` | `/admin/instances` | Spawn instance |
| `DELETE` | `/admin/instances/{id}` | Kill + shred credentials |
| `POST` | `/admin/instances/{id}/restart` | Restart in place |
| `POST` | `/admin/reconcile` | Full state reconcile (used on startup) |

See `docs/superpowers/specs/2026-04-17-google-templates-dynamic-secrets-design.md` for the full design.
