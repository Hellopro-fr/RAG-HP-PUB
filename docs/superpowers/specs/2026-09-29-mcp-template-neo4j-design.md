# MCP Template — Neo4j (`mcp-template-neo4j-service`)

**Date:** 2026-09-29
**Status:** Approved design, pending implementation plan
**Related:** `2026-04-17-google-templates-dynamic-secrets-design.md` (the Google template flow this mirrors)

## Goal

Let an admin create, from the gateway's Templates page, any number of named Neo4j MCP
instances — each with its own connection (URI / user / password / database) and its own
access mode (read-only or read-write) — hosted by a dedicated runner and exposed through
`mcp-gateway-service` exactly like the GA4 / GSC template instances.

The LLM sees each instance as a separate backend with its own tool prefix, e.g.
`neo4jprod_read_neo4j_cypher`, `neo4jstaging_write_neo4j_cypher`.

## Current state (verified 2026-09-29)

- Neo4j access through the gateway works: `neo4j_get_neo4j_schema` returns the live graph
  (`Produit` 34 089, `Fournisseur` 1 374, `CaracteristiqueTechnique` 77 385, `Categorie`,
  `Pays`, `ZoneGeo`).
- It is served by one static container, `mcp-neo4j-service` (port 8587): `mcp-proxy`
  wrapping `mcp-neo4j-cypher`, single credential set from `.env`, registered as a plain
  server with prefix `neo4j`.
- The template flow is Google-specific in five places:
  1. `internal/api/template_handlers.go` — create requires a `credentials` file and rejects
     anything that is not a Google service-account JSON (`ValidateServiceAccountJSON`).
  2. `mcp-google-templates-runner/app/supervisor.py` — always sets
     `GOOGLE_APPLICATION_CREDENTIALS` to the written secret file.
  3. `internal/config/config.go` / `internal/app/app.go` — one runner client only
     (`GOOGLE_TEMPLATES_RUNNER_URL`).
  4. `internal/api/template_handlers.go` (`createInstanceFromSpec`) — the instance URL host
     is derived from `GoogleTemplatesRunnerURL`.
  5. `internal/api/internal_handlers.go` (`handleRunnerSync`) — returns **every** instance and
     authenticates only the Google runner token.
- `extra_env` is stored as plaintext JSON; only `EncryptedCredentials` is encrypted.

## Decisions

| Topic | Decision |
|---|---|
| What an instance is | One named connection: URI + user + password + database + read-only flag. Covers several databases and several access profiles on one database. |
| Credentials input | Form fields in the frontend; the gateway serializes them to JSON and stores them in `EncryptedCredentials` (same encryption as Google). Never in `extra_env`. |
| Access control | Per-instance `NEO4J_READ_ONLY` flag, applied to every user of that instance. No per-user differentiation; `min_role` is out of scope. |
| Architecture | Separate runner service `mcp-template-neo4j-service` + runner routing in the gateway (approach A). |
| Static `mcp-neo4j-service` | Left untouched. Migrating it to a template instance is out of scope. |

## Architecture

```
Admin (mcp-gateway-frontend)
   │  Neo4j form: name, tool_prefix, URI, user, password, database, [x] Lecture seule
   ▼
mcp-gateway-service (Go, 8581)
   │  templates.runner = "neo4j"  → neo4j runner client
   │  credentials {uri,username,password,database} → EncryptedCredentials
   │  extra_env {"NEO4J_READ_ONLY":"true"|"false"}
   ▼  POST /admin/instances (X-Admin-Token)
mcp-template-neo4j-service (Python, 8598)
   │  port pool 15100–15199, supervisor, reconcile
   ├─ mcp-proxy :15100 -- mcp-neo4j-cypher   (neo4jprod,    read-only)
   └─ mcp-proxy :15101 -- mcp-neo4j-cypher   (neo4jstaging, read-write)
   ▲
   gateway registers each port as an mcp_servers backend (own tool_prefix)
```

## Components

### 1. `apps-microservices/mcp-template-neo4j-service/` (new)

Same layout as `mcp-google-templates-runner`: `app/{config,auth,models,port_pool,supervisor,gateway_sync,main}.py`,
`app/api/admin.py`, `Dockerfile`, `entrypoint.sh`, `requirements.txt`, `CLAUDE.md`, `tests/`.

- Same admin API contract (`GET /admin/health`, `GET|POST /admin/instances`,
  `DELETE /admin/instances/{id}`, `POST /admin/instances/{id}/restart`, `POST /admin/reconcile`),
  same `SpawnRequest` shape — the gateway's `runnerclient` is reused unchanged.
- **No secret file.** `credentials_json` is parsed as `{uri, username, password, database}` and
  mapped to `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` in the subprocess
  environment. `NEO4J_READ_ONLY` comes from `env` (the gateway's merged `default_env` + `extra_env`).
  Credential-derived variables are applied **after** the template env so they cannot be overridden;
  `NEO4J_URL` (which wins over `NEO4J_URI` upstream), `NEO4J_TRANSPORT` and `NEO4J_MCP_SERVER_*`
  are stripped from the template env. Connection/transport CLI flags in `stdio_args` (`--db-url`,
  `--password`, `--transport`, `--server-*`, … and their argparse abbreviations such as `--pass`)
  are rejected, because upstream CLI flags win over env vars. The password is replaced by `***`
  in the stderr tail shown in the instance detail view.
- **Connectivity pre-check** on `POST /admin/instances` only (gateway create / rotate), never on
  reconcile: open a session on the configured database and run `RETURN 1` (timeout
  `NEO4J_PRECHECK_TIMEOUT_SEC`, default 5 s; `verify_connectivity()` alone would not detect a
  missing database). Failure → HTTP 422 `{"detail":{"code","message"}}` with code
  `neo4j_invalid_credentials`, `neo4j_invalid_uri`, `neo4j_auth_failed`, `neo4j_database_not_found`,
  `neo4j_unreachable` or `neo4j_error`; no process started, no port consumed, and a running
  instance with the same id keeps serving. Skipping it on reconcile means a Neo4j blip while the
  runner restarts never orphans instances.
- Command: `mcp-proxy --port <p> --host 0.0.0.0 --pass-environment --stateless -- mcp-neo4j-cypher`
  (same flags as the static `mcp-neo4j-service`, minus `--allow-origin *`, which the gateway does not need).
- Env: `MCP_GATEWAY_URL`, `MCP_GATEWAY_ADMIN_TOKEN`, `RUNNER_ADMIN_TOKEN`, `RUNNER_PORT=8598`,
  `RUNNER_INSTANCE_PORT_START=15100`, `RUNNER_INSTANCE_PORT_END=15199`.
- `requirements.txt`: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `httpx`,
  `mcp-proxy`, `mcp-neo4j-cypher>=0.6.0`, `neo4j`. Verified in 0.6.0: `utils.py` reads
  `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` / `NEO4J_READ_ONLY`, and
  `server.py` registers `write_neo4j_cypher` with `enabled=not read_only` — read-only mode removes
  the write tool from `tools/list`, it does not merely reject writes.
- Non-root user, `python:3.11-slim`, `curl` for the healthcheck.

### 2. Gateway — templates catalog

- New column `templates.runner varchar(16) NOT NULL DEFAULT 'google'` (GORM field `Runner`, JSON `runner`).
  Existing `ga` / `gsc` rows get `google` via the default.
- Seed row in `init-db/init-mcp-gateway-db.sql`:
  `slug='neo4j'`, `name='Neo4j'`, `stdio_command='mcp-neo4j-cypher'`, `stdio_args='[]'`,
  `default_env='{"NEO4J_READ_ONLY":"true"}'`,
  `required_extra_env='[{"key":"NEO4J_READ_ONLY","label":"Lecture seule","required":false}]'`,
  `icon='/images/servers/neo4j.svg'`, `tool_prefix=''`, `tags='["database","neo4j","graph"]'`,
  `kind='stdio'`, `runner='neo4j'`.
- `tool_prefix` is empty on purpose: the static `mcp-neo4j-service` already owns `neo4j` and the
  gateway has no tool-name collision check, so every Neo4j instance must set its own prefix
  (e.g. `neo4jprod`); create returns 400 for an empty prefix or `neo4j`.
- Template export/import carries `runner`; an import row without `runner` defaults to `google`.
  The import refuses (409) to change the runner of a template that has instances.

### 3. Gateway — runner routing

- Config: `NEO4J_TEMPLATES_RUNNER_URL`, `NEO4J_TEMPLATES_RUNNER_ADMIN_TOKEN` (must differ from the
  Google token; equal tokens disable the Neo4j runner and make the sync endpoint refuse both).
- `app.go` passes the non-Google runners to `Handler.SetRunners(map[string]RunnerEndpoint)`
  (`RunnerEndpoint{Client, URL, AdminToken}`); the Google runner stays the one given to `NewHandler`.
- `runnerForTemplate` / `runnerForInstance` replace every direct `h.runner.X` call: create
  (`createInstanceFromSpec`), rotate, restart, delete, list (detail view stderr tail), and the
  server-delete cascade in `server_handlers.go`. Unconfigured runner → HTTP 503
  `runner <name> not configured`. A runner 422 pre-check failure → HTTP 422 `"<code>: <message>"`
  (`runnerclient.StatusError.Detail()`).
- Instance URL host is derived from the selected runner's URL, not `GoogleTemplatesRunnerURL`.

### 4. Gateway — credentials validation

- `handleCreateInstance` / `handleRotateCredentials` branch on `tpl.Runner`:
  - `google`: unchanged (file upload, `ValidateServiceAccountJSON`).
  - `neo4j`: multipart fields `neo4j_uri`, `neo4j_username`, `neo4j_password`, `neo4j_database`
    → `validation.ValidateNeo4jCredentials`: URI scheme in `bolt`, `bolt+s`, `bolt+ssc`, `neo4j`,
    `neo4j+s`, `neo4j+ssc` with a non-empty host; username and password non-empty; database
    defaults to `neo4j`, matches `^[A-Za-z0-9._-]{1,63}$`. Serialized to canonical JSON, then the
    existing encrypt + SHA-256 path.
- Neo4j `extra_env` accepts only `NEO4J_READ_ONLY` = `"true"` | `"false"` (400 otherwise): any
  other `NEO4J_*` key could redirect the connection.
- Rotate on a Neo4j instance accepts the same fields and an optional `extra_env`, so toggling
  read-only or changing the password is one call. Unlike Google (DB first), a Neo4j rotate
  persists the new credentials only **after** the runner accepted them: a rejected rotate returns
  422 without touching the DB, and a reconcile racing with it keeps the previous credentials.
- Google Sheets instance import is refused for non-Google runners.

### 5. Gateway — runner sync isolation (required fix)

`handleRunnerSync` identifies the caller by comparing `X-Admin-Token` (constant time) against each
configured runner token, then returns **only instances whose template has that `runner`**.
Without this, each runner's reconcile would try to spawn the other's instances (the Google image has
no `mcp-neo4j-cypher`, and vice versa) and would kill-loop.

### 6. Frontend — `mcp-gateway-frontend`

`TemplateInstanceFormView.vue`: when `template.runner === 'neo4j'`, render URI, user, password
(`type="password"`, never pre-filled on edit), database (placeholder `neo4j`) and a "Lecture seule"
checkbox checked by default, instead of the SA JSON file upload, and require a tool prefix other
than `neo4j`. `RotateCredentialsModal.vue` reuses the same fields. `TemplateDetailView.vue` hides
"Import depuis Sheets" for Neo4j templates. `TemplatesView.vue` shows the Neo4j card from the catalog.

### 7. `docker-compose.yml`

New service `mcp-template-neo4j-service`, profile `mcp`, `expose:` 8598 and 15100–15199 (no host
`ports:`), healthcheck on `/admin/health`, `json-file` logging (`max-size: 10m`, `max-file: 3`),
same network as the gateway. Gateway service gets the two `NEO4J_TEMPLATES_RUNNER_*` variables.

## Data flow — create

1. Admin submits the Neo4j form → `POST /api/v1/template-instances` (multipart).
2. Gateway validates fields and `extra_env`, serializes + encrypts credentials, inserts the
   `template_instances` row.
3. `runnerFor(tpl).Spawn(...)` → runner pre-check → subprocess start → port returned.
4. Gateway waits for TCP-ready, inserts the `mcp_servers` row (URL on the neo4j runner host),
   registers the backend, auto-discovers tools (3 tools, or 2 when read-only hides `write_neo4j_cypher`).

## Error handling

| Case | Behaviour |
|---|---|
| Invalid URI / empty field / bad `NEO4J_READ_ONLY` | 400 from the gateway, nothing persisted |
| Neo4j refuses the pre-check | Runner 422 `{"detail":{"code","message"}}` → gateway returns 422 `"<code>: <message>"`; create rolls back the row (existing spawn-failure path), rotate leaves the DB and the running instance untouched |
| Missing or `neo4j` tool prefix | 400 from the gateway (collision with the static Neo4j server) |
| Catalog import changes the runner of a template with instances | 409, nothing imported |
| Neo4j runner not configured | 503 on create/rotate/restart; Google templates unaffected |
| Subprocess crash | Inherited supervisor backoff; `runner_status=failed` + `stderr_tail` in the detail view |
| Runner restart | `gateway_sync` → filtered sync → re-spawn on the stored `RunnerPort` |
| Logging | Password never logged; `CredentialsJSON` redacted on both sides as for Google |

## Testing

- **Runner (pytest, mocks):** credentials → env mapping; credential vars override template env;
  `NEO4J_READ_ONLY` propagated; pre-check failure → 422 and no spawn; malformed credentials JSON →
  422; port pool bounds; reconcile kills unknown and spawns missing instances.
- **Gateway (go test):** `runnerFor` for google / neo4j / unconfigured; `ValidateNeo4jCredentials`
  table test; `NEO4J_READ_ONLY` validation; runner sync filtered by token (Google token sees no
  Neo4j instance and vice versa; unknown token → 401); instance URL uses the selected runner host;
  regression: `ga` / `gsc` still require an SA JSON file.
- **Frontend (vitest):** Neo4j template renders the connection fields and the read-only checkbox,
  not the file upload; Google templates unchanged.
- **Manual (remote server):** create a read-only and a read-write instance on the same database;
  `tools/list` shows `write_neo4j_cypher` only on the read-write one;
  `MATCH (p:Produit) RETURN count(p)` through the read-only instance returns the same count as the
  static `neo4j` backend.

## Out of scope

- Per-user access differences inside one instance, and `min_role` on template instances.
- Migrating the static `mcp-neo4j-service` to a template instance.
- Google Sheets batch import for Neo4j instances.
