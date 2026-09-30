# mcp-template-neo4j-service

Python sidecar that hosts the Neo4j template instances spawned by the gateway's Templates feature. One `mcp-proxy -- mcp-neo4j-cypher` subprocess per instance, each on a dynamic port in the 15100–15199 pool, supervised per-instance. Same admin API contract as `mcp-google-templates-runner`.

## Tech Stack

- Python 3.11, FastAPI, Uvicorn, asyncio
- `mcp-proxy` wraps the stdio MCP server into SSE/HTTP
- Upstream package: `mcp-neo4j-cypher>=0.6.0`; `neo4j` driver for the pre-check

## Credentials

The gateway sends `credentials_json` = `{"uri","username","password","database"}` (decrypted from `template_instances.encrypted_credentials`). The runner never writes it to disk: it becomes `NEO4J_URI/USERNAME/PASSWORD/DATABASE` in the child env, set after the template env so nothing can override them. `NEO4J_URL`, `NEO4J_TRANSPORT` and `NEO4J_MCP_SERVER_*` are stripped from the template env (`NEO4J_URL` wins over `NEO4J_URI` upstream), and connection/transport CLI flags (`--db-url`, `--password`, `--transport`, `--server-*`, …, including argparse abbreviations such as `--pass`) in `stdio_args` are rejected with `neo4j_invalid_credentials` (CLI flags win over env vars upstream). The password is replaced by `***` in the stderr tail. `NEO4J_READ_ONLY` comes from the instance `extra_env`; `true` removes `write_neo4j_cypher` from `tools/list`.

## Pre-check

`POST /admin/instances` (gateway create / rotate) first opens a session on the configured database (`RETURN 1`, timeout `NEO4J_PRECHECK_TIMEOUT_SEC`, default 5 s). Failure → 422 `{"detail":{"code","message"}}` with code `neo4j_invalid_credentials`, `neo4j_invalid_uri`, `neo4j_auth_failed`, `neo4j_database_not_found`, `neo4j_unreachable` or `neo4j_error`; nothing is spawned and a running instance with the same id keeps serving. `/admin/reconcile` and the boot/periodic sync skip the pre-check so a Neo4j blip never orphans instances.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_URL` | — | Base URL of mcp-gateway-service for sync |
| `MCP_GATEWAY_ADMIN_TOKEN` | — | Sent as `X-Admin-Token` to the gateway; must equal the gateway's `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` (the gateway uses it to pick this runner's instances) |
| `RUNNER_ADMIN_TOKEN` | — | Required `X-Admin-Token` on incoming `/admin/*` requests |
| `RUNNER_PORT` | `8598` | Admin API port (8595 Google runner, 8596 Zoho, 8597 HelloData) |
| `RUNNER_INSTANCE_PORT_START` / `_END` | `15100` / `15199` | Dynamic pool (the Google runner owns 15000–15099) |
| `NEO4J_PRECHECK_TIMEOUT_SEC` | `5` | Pre-check timeout |

## Admin API (X-Admin-Token)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/health` | Liveness (no auth) |
| `GET` | `/admin/instances` | List running instances |
| `POST` | `/admin/instances` | Pre-check + spawn instance |
| `DELETE` | `/admin/instances/{id}` | Kill instance |
| `POST` | `/admin/instances/{id}/restart` | Restart in place |
| `POST` | `/admin/reconcile` | Full state reconcile (no pre-check) |

## Tests

    docker run --rm=true -v "$PWD/apps-microservices/mcp-template-neo4j-service":/src -w /src python:3.11-slim \
      sh -c "pip install -q -r requirements.txt pytest pytest-asyncio && python -m pytest -q -p no:cacheprovider tests"

See `docs/superpowers/specs/2026-09-29-mcp-template-neo4j-design.md`.
