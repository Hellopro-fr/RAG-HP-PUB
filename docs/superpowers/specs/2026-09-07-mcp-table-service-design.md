# Design — `mcp-table-service`: MCP tools over the BDD used-tables registry

- **Date:** 2026-09-07
- **Services:** new `apps-microservices/mcp-table-service` (Go 1.24), plus two small changes in `apps-microservices/mcp-gateway-service`
- **Status:** Approved design — pending implementation plan
- **Author:** Claude (pair) + sandrianirinaharivelo@hellopro.fr

## 1. Problem

The "Tables BDD" admin pages of `mcp-gateway-frontend` (`/bdd-tables`,
`/bdd-tables/new`, `/bdd-tables/:id/fields`) let a gateway admin curate which
Hellopro MySQL tables are exposed to MCP clients: register tables from the
upstream catalog, expose a subset of their fields, write the descriptions used
in the LLM doc, set metadata (notes, default order by, relations, row count),
activate / deactivate / delete tables. All of this is only reachable through the
browser UI.

We want the same actions available as MCP tools, so an LLM client connected to
the gateway can list, inspect, complete, activate and delete registry tables —
**with exactly the privileges the calling user holds on the gateway**.

## 2. What already exists (measured 2026-09-07)

- The pages call the gateway REST routes under `/api/v1/bdd/` (`internal/api/bdd_handlers.go`).
  Role gating lives in `internal/api/handler.go` `isAdminOnly`: every write and
  the catalog proxy are **admin**-only; `GET /api/v1/bdd/used/*` (except
  export) is **read-only or higher**; `config-only` gets 403.
- Roles come from `gateway_users.role` (`admin` / `read-only` / `config-only`,
  `internal/auth/role.go`). `auth.Middleware` resolves the role through
  `injectRole(ctx, email, userRepo)`; unknown email → `config-only`.
- Registry rows: `bdd_used_tables` (+ `bdd_used_fields`). `is_active` defaults
  to **true** on insert (`BulkCreate`, `CreateTable`). The UI status is
  derived: `!is_active` → **Inactive**; `is_active && fields == 0` →
  **Brouillon** (draft); `is_active && fields > 0` → **Active**. The fields
  page banner says "Ajoutez au moins un champ pour l'activer". The public
  runner endpoints (`/api/v1/public/bdd/*`) filter on `is_active` only.
- Editable table data (fields page "Configuration de la table"):
  `description` (LLM doc), `notes`, `default_order_by`, `rows` (manual override
  or refreshed from catalog), `relations` (stored as `[]` or
  `{"<target_table>": "<self>.<col> -> <target_table>.<col>"}`),
  `primary_key` (only via `POST /{id}/refresh-catalog`), fields (add from
  catalog with `field_type` + `upstream_field_id`, patch description, delete,
  `POST /{id}/sync-field-types`).
- Tool prefix `bdd` is already taken by the PHP BDD MCP backend
  (`X-BDD-Allowed-Tables` injection). The new backend uses prefix **`tables`**.
- Sibling custom MCP servers are Go stdlib (`mcp-ringover-service`,
  `mcp-leexi-service`, `mcp-zoho-service`). The gateway forwards the end-user
  identity (`X-End-User-Email`, `X-End-User-Login`) **only** to Zoho-tagged
  backends today (`scoped_gateway.go` `injectZohoIdentity`).
- Internal machine-to-machine auth pattern: `X-Admin-Token` shared secret,
  constant-time compared (`internal_handlers.go`, `mcp-zoho-service`
  `adminTokenMiddleware`).

## 3. Decisions taken during brainstorming

| Question | Decision |
|---|---|
| Privilege model | **Gateway role.** Email from the OAuth2 access token → `gateway_users.role`. admin = all tools; read-only = list/get only; config-only or unknown = denied. Mirrors the UI exactly. |
| Catalog browsing | **Yes.** Tools to list the 3 databases, catalog tables (flagged "already registered") and catalog fields, so an LLM can find what to add. |
| Architecture | **A — thin MCP façade over the gateway REST API.** The gateway stays the single writer; the service never touches MySQL. |
| Activation rule | A table is only considered activatable when it has **≥ 1 exposed field**. `set_tables_active` refuses activation of zero-field tables. `add_fields` is the step that turns a draft into an active table. |
| Completeness | Tools cover every attribute the fields page can set: description, notes, default order by, rows, relations, primary key / rows refresh, fields + field descriptions + field type sync. |

Rejected: **B** direct MySQL like `mcp-zoho-service` (duplicates identifier
regex, DB-id whitelist, bulk caps, field-type normalisation, cascade rules;
two writers on the same tables; catalog secret copied). **C** virtual backend
inside the gateway (contradicts the request, grows the gateway further).

## 4. Goals / Non-goals

**Goals**
- 13 MCP tools (section 6) over SSE + Streamable HTTP, registered in the
  gateway as one backend with tool prefix `tables`.
- Privileges enforced by the gateway's existing role gate, via an "act-as"
  internal auth path. `created_by` on new rows is the real user's email.
- Fail-closed: no end-user identity → write **and** read tools refuse.
- Clear MCP error texts for 403 / 404 / 409 / 4xx / 5xx / unreachable.

**Non-goals**
- Scope tokens (`mcp_…`) carry no end user → `tools/call` fails closed for
  them. Machine access goes through an OAuth2 client with a real user.
- No per-role hiding in `tools/list`: the gateway serves the cached discovery
  catalog (only Zoho has a live per-user `tools/list`), so hiding would not
  reach the client. Admins keep per-tool scoping on tokens / clients.
- No registry-wide `_meta` (description / usage) editing, no export / import,
  no moving a table between databases, no frontend change.

## 5. Architecture

### 5.1 Privilege flow, one `tools/call`

```
claude.ai ──OAuth2 access token (email claim)──▶ mcp-gateway-service
   │  ScopedGateway.requestHeadersFor(backend tool_prefix="tables")
   │    + static auth_headers of the mcp_servers row  (X-Admin-Token: <secret>)
   │    + X-End-User-Email / X-End-User-Login          (NEW for prefix "tables")
   ▼
mcp-table-service  POST /mcp
   1. X-Admin-Token == MCP_TABLE_GATEWAY_TOKEN  else 401 (health exempt)
   2. tools/call requires X-End-User-Email        else MCP error (fail closed)
   3. calls gateway REST with
        X-Admin-Token: <same secret>
        X-Act-As-Email: <end-user email>
   ▼
mcp-gateway-service  /api/v1/bdd/...
   auth.Middleware NEW branch (only when TABLE_SERVICE_TOKEN set):
     path has prefix /api/v1/bdd/ AND X-Admin-Token matches AND X-Act-As-Email != ""
       → ctx email = act-as email, ctx role = injectRole(email)  (unknown → config-only)
   roleCheckMiddleware / isAdminOnly / isReadOnlyPlus — UNCHANGED
   handlers — UNCHANGED (CreatedBy = auth.UserEmailFromContext)
```

`initialize` and `tools/list` do not require an end-user email so gateway
discovery and health probes keep working.

### 5.2 Gateway change 1 — act-as branch (`internal/auth/middleware.go`)

Inserted before the `Authorization: Bearer` branch. All conditions required:
`cfg.TableServiceToken != ""`, `strings.HasPrefix(path, "/api/v1/bdd/")`,
`subtle.ConstantTimeCompare(X-Admin-Token, token) == 1`, `X-Act-As-Email`
non-empty. On match: set `ContextKeyUserEmail`, `ContextKeyUserName` (= email),
role via `injectRole`, log `[auth] act-as email=<email> path=<path>`, continue.
Any non-match falls through to the existing branches (→ 401 as today).

New config: `Config.TableServiceToken` (`TABLE_SERVICE_TOKEN`) in
`internal/config/config.go`, plumbed into `auth.Config`.

### 5.3 Gateway change 2 — identity forwarding (`internal/gateway/scoped_gateway.go`)

- `const tablesToolPrefix = "tables"`.
- `requestHeadersFor`: the `switch backend.ToolPrefix` gains
  `case tablesToolPrefix: sg.injectEndUserIdentity(ctx, headers, backend)`.
  The identity helper is the existing email/login injection factored out of
  `injectZohoIdentity` (Zoho behaviour byte-identical).
- Step 0 (server-authorization bypass) also injects identity for
  `tablesToolPrefix`, as it does for Zoho — otherwise a granted user would
  reach the service without identity and be denied.
- No filter header for this backend: the role decides, not an allow-list.

### 5.4 Service (`apps-microservices/mcp-table-service`)

```
mcp-table-service/
  cmd/server/main.go            # boot, mux, graceful shutdown (from ringover)
  internal/config/config.go     # env loading
  internal/mcp/types.go         # JSON-RPC / MCP types (from ringover)
  internal/transport/
    streamable_http.go, sse.go  # transports (from ringover)
    identity.go                 # X-Admin-Token check middleware; X-End-User-Email → ctx
  internal/gateway/
    client.go                   # typed HTTP client, one method per gateway route, act-as header
    types.go                    # DTOs mirroring gateway bdd_dto.go
    errors.go                   # APIError{Status int, Message string}
  internal/tools/
    registry.go, handler.go     # registration + dispatch (from ringover)
    read_tools.go               # list_registered_tables, get_table_info
    catalog_tools.go            # list_databases, list_catalog_tables, list_catalog_fields
    table_tools.go              # add_tables, update_table_info, set_tables_active, delete_tables, sync_table_catalog
    field_tools.go              # add_fields, update_fields, remove_fields
    status.go                   # status + missing checklist
    relations.go                # relation rows <-> stored map shape
    errors.go                   # APIError -> MCP error text
  Dockerfile, go.mod (module github.com/hellopro/mcp-table), CLAUDE.md
```

Module has **no external dependencies** (stdlib only), like ringover.

## 6. Tools

Names below are the service-local names; the gateway exposes them as
`tables_<name>`. "Role" is the minimum `gateway_users.role`, enforced by the
gateway's own gate on the wrapped route.

### 6.1 Read — role `read-only`

| Tool | Args | Wraps | Output |
|---|---|---|---|
| `list_registered_tables` | `database_id?` (1/5/10), `search?`, `page?` (≥1), `limit?` (1..100, default 20) | `GET /bdd/used/tables` | `{tables:[{id, database_id, table_name, description, is_active, status, field_count, primary_key, rows, created_by, updated_at}], total, page, limit}` |
| `get_table_info` | `table_id` **or** (`database_id` + `table_name`) | `GET /bdd/used/tables/{id}` (name → resolved via list+search, exact match) | full table DTO + `fields[]` + `status` + `missing[]` |

`status`: `inactive` (`!is_active`), `draft` (`is_active && 0 fields`),
`active`. `missing[]` values: `no_fields`, `empty_description`,
`fields_without_description:<n>`, `unknown_primary_key`, `unknown_rows`.

### 6.2 Catalog — role `admin`

| Tool | Args | Wraps | Output |
|---|---|---|---|
| `list_databases` | — | `GET /bdd/catalog/databases` | `{databases:[{id,name}]}` |
| `list_catalog_tables` | `database_id`, `search?` | `GET /bdd/catalog/databases/{db}/tables` + registry pages for that db (limit 100, loop until `total`, cap 50 pages) | `{tables:[{upstream_table_id, table_name, description, field_count, registered:bool, registered_table_id?}]}` |
| `list_catalog_fields` | `database_id` + `table_name` | catalog tables (search=name, exact match) → `GET .../tables/{tid}/fields`; registry lookup for exposure flag | `{table_name, upstream_table_id, primary_key, fields:[{upstream_field_id, field_name, field_type, is_nullable, description, exposed:bool}]}` |

### 6.3 Write — role `admin`

| Tool | Args | Behaviour |
|---|---|---|
| `add_tables` | `database_id`, `tables:[{table_name, description?}]` (1..50), `refresh_catalog?` (default true) | Resolve each name in the catalog (search + exact match → `upstream_table_id`; not found → per-item error). `POST /bdd/used/tables/bulk`. Then, best effort, `POST /{id}/refresh-catalog` per created row (max 5 in parallel, 10 s each). Result: `{ok:[{...table, status:"draft", catalog_refreshed:bool}], errors:[{table_name, error}], note:"tables are drafts until fields are added (add_fields)"}` |
| `add_fields` | `table_id` \| (`database_id`+`table_name`), `fields:[{field_name, description?}]` (1..50) **or** `all_fields:true` | Fetch catalog fields for the table's `upstream_table_id`; unknown name → per-item error. `POST /{id}/fields` per field with `field_type` + `upstream_field_id` from catalog. Result `{ok:[field], errors:[...], status_after}` — this is the activation step for drafts. |
| `update_table_info` | `table_id` \| (db+name), `description?`, `notes?`, `default_order_by?`, `rows?` (≥0), `relations?:[{self_col, target_table, target_col}]` | At least one attribute required. Relations: empty list → `[]`; else `{target_table: "<table_name>.<self_col> -> <target_table>.<target_col>"}`; every `target_table` must be a registered table with ≥1 field (UI rule) else error. `PATCH /bdd/used/tables/{id}`. Returns updated table + `status` + `missing[]`. |
| `update_fields` | `table_id` \| (db+name), `fields:[{field_name, description}]` (1..50) | Resolve field ids from the table; `PATCH /{id}/fields/{fid}` each. `{ok, errors}` |
| `remove_fields` | `table_id` \| (db+name), `field_names:[...]` (1..50) | `DELETE /{id}/fields/{fid}` each. Result adds `warning:"table is now a draft (0 fields)"` when applicable. |
| `set_tables_active` | `table_ids:[...]` (1..50), `active:bool` | `active=true`: `GET` each table; zero-field tables are **refused** (`errors:[{table_id, error:"cannot activate: table has no exposed field"}]`); remaining ids → `PATCH /bdd/used/tables/bulk {ids, is_active}`. `active=false`: no guard. `{affected, errors}` |
| `delete_tables` | `table_ids:[...]` (1..50) | `DELETE /bdd/used/tables/bulk {ids}`. Tool annotation `destructiveHint: true`. `{affected}` |
| `sync_table_catalog` | `table_id` \| (db+name) | `POST /{id}/refresh-catalog` then `POST /{id}/sync-field-types`. `{primary_key, rows, field_types_updated, total_fields}` |

### 6.4 Conventions

- `database_id` ∈ {1, 5, 10}; tool descriptions name them Hellopro BO / Data / IA.
- Batch arrays capped at 50 (gateway bulk limit). Batch tools return
  `{ok:[...], errors:[{item, error}]}`; `isError` only when nothing succeeded.
- Results are pretty-printed JSON text blocks (`jsonResult`, as in ringover).
- Identifiers echo the gateway regex `^[a-zA-Z0-9_]{1,128}$`; the service
  trims and forwards, the gateway validates.

## 7. Error handling

| Condition | MCP result (`isError: true`) |
|---|---|
| No `X-End-User-Email` on `tools/call` | "No end-user identity. Connect through the gateway with an OAuth2 user login; scope tokens are not supported by this service." |
| Gateway 403 | "Your gateway role does not allow this action (requires `<admin\|read-only>`). Ask a gateway admin." |
| Gateway 401 | "The table service is not authorized on the gateway (shared secret mismatch)." + `log.Printf` configuration error |
| Gateway 404 | "Table not found" / "Field not found" |
| Gateway 409 | gateway `error` passed through (e.g. "table already registered for this database") |
| Gateway 400 / 422 | gateway `error` passed through |
| Gateway 502 / 503 | "Upstream BDD catalog unavailable: <gateway error>" |
| Timeout / connection error | "Gateway unreachable: <err>" |
| Bad tool args | "invalid arguments: <detail>" (before any gateway call) |

Timeouts: 15 s per gateway call (`MCP_GATEWAY_TIMEOUT`), 10 s for
refresh-catalog calls, `add_tables` bounded at 120 s overall.

## 8. Configuration

### Service

| Variable | Default | Description |
|---|---|---|
| `MCP_PORT` | `8597` | HTTP listen port |
| `MCP_SERVICE_NAME` | `mcp-table` | MCP `serverInfo.name` |
| `MCP_SERVICE_VERSION` | `0.1.0` | MCP `serverInfo.version` |
| `MCP_GATEWAY_URL` | — (required) | In-cluster gateway base URL, e.g. `http://mcp-gateway-service:8592` |
| `MCP_TABLE_GATEWAY_TOKEN` | — (required) | Shared secret: checked on inbound `X-Admin-Token`, sent on outbound `X-Admin-Token`. Must equal gateway `TABLE_SERVICE_TOKEN`. Service refuses to boot when empty. |
| `MCP_GATEWAY_TIMEOUT` | `15` | Seconds per gateway call |

### Gateway

| Variable | Default | Description |
|---|---|---|
| `TABLE_SERVICE_TOKEN` | — | Enables the act-as branch on `/api/v1/bdd/*`. Empty = branch disabled. Must equal `MCP_TABLE_GATEWAY_TOKEN`. |

`.env` carries a single `MCP_TABLE_SERVICE_TOKEN`, mapped to both.

### Registration (admin, existing Servers UI — no frontend change)

URL `http://mcp-table-service:8597/mcp`, tool prefix `tables`, auth header
`X-Admin-Token: <MCP_TABLE_SERVICE_TOKEN>`. Discovery yields the 13 tools.

## 9. Deployment

- `Dockerfile`: `golang:1.24-alpine` builder → `alpine:3.20`, binary
  `/bin/mcp-table`, `EXPOSE 8597`, non-root user, `ca-certificates` + `curl`
  for the healthcheck.
- `docker-compose.yml`: `mcp-table-service` under profile `mcp`, port 8597,
  `depends_on: mcp-gateway-service`, healthcheck `curl -f http://localhost:8597/health`,
  `networks: services-net`, `logging: *logging_defaults`. Gateway block gains
  `TABLE_SERVICE_TOKEN=${MCP_TABLE_SERVICE_TOKEN}`.

## 10. Testing

**Gateway**
- `internal/auth/middleware_actas_test.go`: valid token + email on `/api/v1/bdd/used/tables` injects email and role from a fake `UserRepo`; unknown email → `config-only`; wrong token → 401; valid pair on `/api/v1/servers` → ignored (401); empty `TableServiceToken` → branch disabled.
- `internal/gateway/scoped_gateway_tables_test.go`: identity headers present for prefix `tables` with email in ctx; absent without email; present inside the server-authorization bypass; absent for an unrelated prefix; Zoho behaviour unchanged.

**Service** (all against `httptest.Server` fakes, no network)
- `internal/gateway/client_test.go`: act-as + token headers on every call; status → `APIError`; timeout.
- `internal/tools/*_test.go`: status derivation; `missing[]`; relations round-trip (both stored shapes); `set_tables_active` refuses zero-field tables; `add_fields` pulls type / upstream id from catalog and rejects unknown names; `update_table_info` rejects relation targets without fields; 403 → role message; missing identity → error; batch partial results; `list_catalog_tables` registered flag across pages.
- `internal/transport/identity_test.go`: token check, `/health` exempt, email into ctx.

**Commands** (both modules): `go vet ./...`, `go build ./...`, `go test ./...`.

## 11. Documentation

- New `apps-microservices/mcp-table-service/CLAUDE.md` (stack, run, tool table with roles, env, privilege flow, boundaries).
- `apps-microservices/mcp-gateway-service/CLAUDE.md`: env var row `TABLE_SERVICE_TOKEN`; convention bullet describing the act-as branch and the `tables` identity injection; test file names.
- Root `CLAUDE.md`: no change (MCP services are not listed individually).

## 12. Acceptance (feeds the unlazy `GATES.md`)

1. `go vet`, `go build`, `go test` clean in `mcp-gateway-service` and `mcp-table-service`.
2. Service `tools/list` returns exactly the 13 names of section 6.
3. Fake-gateway smoke: read-only user → `list_registered_tables` succeeds, `add_tables` returns the role error text; admin user → `add_tables` then `add_fields` yields `status: "active"`; `set_tables_active` on a zero-field table is refused.
4. `docker compose --profile mcp config` validates with the new service.
5. Both CLAUDE.md files mention `TABLE_SERVICE_TOKEN` / `MCP_TABLE_GATEWAY_TOKEN`.
