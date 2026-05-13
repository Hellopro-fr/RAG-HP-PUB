# `zoho_imports` — Dedicated Table for Per-User and Admin Zoho Routing

**Date:** 2026-05-13
**Scope:** `apps-microservices/mcp-gateway-service/` + `apps-microservices/mcp-zoho-service/` + `docker-compose.yml`
**Status:** Draft
**Builds on:** `2026-05-12-mcp-zoho-service-design.md` (the proxy service this table backs)

## Problem

The shipped `mcp-zoho-service` reads Zoho upstream URLs and admin grants out of `mcp_servers` + `server_authorizations`. Two problems:

1. The service is logically distinct from the gateway's backend registry, but its data still lives in the registry's `mcp_servers` table. New Zoho imports inflate a table whose other users (gateway scope tokens, tool listing, docs) don't care about per-user routing rows.
2. Per-user rows surface in every gateway list endpoint (`/servers`, capabilities, docs) unless every consumer explicitly filters by `template_slug`. This is fragile.

## Goal

Move Zoho-specific routing data into a dedicated `zoho_imports` table co-hosted in the gateway's MySQL. The table is conceptually owned by `mcp-zoho-service` (it's the only reader at request time) but written by the gateway (sheet-import + admin REST). `mcp_servers` keeps exactly one Zoho row: the stub URL pointing at the service. `server_authorizations` rows on that stub continue to identify admin emails.

Net effect:
- `mcp_servers` carries no per-user data.
- The service has full control over the routing schema and can evolve it without touching shared gateway models.
- Pre-existing imported rows are wiped and re-imported via the existing `/templates` flow (no data migration script).

## Non-goals

- No service-owned database. Same MySQL instance, new table.
- No data migration. Operators delete existing imported rows and re-run sheet imports.
- No new frontend view in v1. Admin row is managed via REST (`POST /api/v1/zoho-imports/admin`); the per-user import wizard stays at `/templates` and dispatches by template slug.
- No multi-admin support. At most one `is_admin=1 AND is_active=1` row.
- No webhook between gateway and service. Service polls via DB read with 60 s TTL cache.

## Schema

```sql
CREATE TABLE zoho_imports (
  id            CHAR(36)      NOT NULL PRIMARY KEY,
  name          VARCHAR(255)  NOT NULL DEFAULT '',
  url           VARCHAR(2048) NOT NULL,
  auth_headers  BLOB,                                       -- AES-256-GCM ciphertext of JSON map
  created_by    VARCHAR(255)  NOT NULL DEFAULT '',          -- target user email; empty when is_admin=1
  is_admin      TINYINT(1)    NOT NULL DEFAULT 0,
  is_active     TINYINT(1)    NOT NULL DEFAULT 1,
  template_slug VARCHAR(64)   NOT NULL DEFAULT '',          -- which catalog template originated this row
  created_at    DATETIME(3)   NOT NULL,
  updated_at    DATETIME(3)   NOT NULL,
  INDEX idx_zoho_created_by   (created_by),
  INDEX idx_zoho_admin_active (is_admin, is_active),
  INDEX idx_zoho_active       (is_active)
);
```

GORM model in the gateway repo (`internal/db/models.go`). AutoMigrate creates the table on boot.

Documented constraints (not schema-enforced):
- At most one `is_admin=1 AND is_active=1` row. Gateway admin endpoint enforces this on write.
- `is_admin=1` implies `created_by=''`. Repo layer rejects otherwise with 400.
- `auth_headers` is encrypted with the gateway's `ENCRYPTION_KEY`. Service decrypts with the same key.

## Architecture

```
[ Operator ]  ───POST /api/v1/zoho-imports/admin────►  [ mcp-gateway-service ]  ──INSERT/UPDATE──►  zoho_imports (is_admin=1)
            ───/templates sheet-import (Zoho)────►                            ──INSERT────────►  zoho_imports (is_admin=0, created_by=<email>)
            ───POST /api/v1/server-authorizations──►                          ──INSERT────────►  server_authorizations (mcp_server_id=<stub-id>)

[ Claude.ai ] ──POST /mcp────────────►  [ mcp-gateway-service ]  ──route to tool_prefix='zoho' backend──►  http://mcp-zoho-service:8596/mcp
                                                                  ──inject X-End-User-Email + X-End-User-Login──►

[ mcp-zoho-service ]  ──SELECT zoho_imports────►  pick admin or user row
                       ──SELECT server_authorizations(stub_id)──►  admin gate
                       ──proxy JSON-RPC body + decrypted auth_headers──►  mcp.zoho.eu/<...>
```

### Resolution

Service-side, on each `POST /mcp`:

1. Read `email` from `X-End-User-Email`, `login` from `X-End-User-Login`.
2. If `email == ""` → 400 `missing_end_user_email`.
3. Cache check (60 s TTL keyed by lowered email). Hit → reuse `(upstream_url, decrypted_headers)`.
4. **Admin gate**: `IsAdminGranted(stubServerID, email)` against `server_authorizations`.
   - If granted → `FindAdminZohoImport()` over `zoho_imports WHERE is_admin=1 AND is_active=1 ORDER BY created_at ASC LIMIT 1`.
     - Hit → use that row's URL + decrypted headers.
     - Miss → JSON-RPC `-32001` with `category="no_admin_zoho_configured"`.
5. **User lookup**: `FindUserZohoImport(email, login)` over `zoho_imports WHERE is_admin=0 AND is_active=1 AND (LOWER(created_by) = ? OR LOWER(created_by) LIKE CONCAT(?, '@%')) ORDER BY created_at ASC LIMIT 1`.
   - Hit → use that row's URL + decrypted headers.
   - Miss → JSON-RPC `-32001` with `category="no_zoho_configured"`.
6. Defensive Go-side `matchesUserEmail` check on the SELECTed row before proxying.

Step 4 and Step 5 are mutually exclusive — admin grants short-circuit user lookup.

### Sheet-import dispatch (gateway side)

`handleImportInstancesFromSheet` (and the http_batch variant if relevant) gains a single dispatch point:

```go
if detectZohoTemplate(tpl) {
    zohoImportRepo.Create(&db.ZohoImport{ ... })
} else {
    mcpServerRepo.Create(&db.MCPServer{ ... })
}
```

`detectZohoTemplate(tpl)` returns true when `tpl.Slug` matches the regex `^zoho(-.*)?$`. Anchored on the catalog row's slug — not on the sheet content — so operators can't accidentally route by data.

### Admin REST endpoints (gateway side)

`POST /api/v1/zoho-imports/admin` — admin-only:
- Request body: `{ "name": "...", "url": "...", "auth_headers": { "Authorization": "Bearer ..." } }`.
- Encrypts `auth_headers` with the gateway's `ENCRYPTION_KEY`.
- Singleton: if a row with `is_admin=1` exists, UPDATE; else INSERT.
- `created_by` is force-set to empty.

`GET /api/v1/zoho-imports/admin` — admin-only:
- Returns the current admin row (decrypted `auth_headers` redacted; only key names listed).
- 404 if no admin row.

`DELETE /api/v1/zoho-imports/admin` — admin-only:
- Hard-deletes the singleton admin row.

These endpoints are gated by the existing admin middleware.

## File impact

| Layer | File | Change |
|---|---|---|
| Gateway model | `apps-microservices/mcp-gateway-service/internal/db/models.go` | New `ZohoImport` GORM struct |
| Gateway DB boot | `apps-microservices/mcp-gateway-service/internal/db/mysql.go` | Add `&db.ZohoImport{}` to AutoMigrate |
| Gateway repo | `apps-microservices/mcp-gateway-service/internal/repository/zoho_import_repo.go` (new) | CRUD: `Create`, `UpdateOrCreateAdmin`, `GetAdmin`, `DeleteAdmin`, `CreateUserImport`, `FindUserImportByEmail` (used by tests only) |
| Gateway sheet handler | `apps-microservices/mcp-gateway-service/internal/api/google_handlers.go` | `detectZohoTemplate` + dispatch; existing non-Zoho path untouched |
| Gateway admin handler | `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_handlers.go` (new) | `POST/GET/DELETE /api/v1/zoho-imports/admin` |
| Gateway router | `apps-microservices/mcp-gateway-service/internal/api/handler.go` | Register the three new routes |
| Gateway DTO | `apps-microservices/mcp-gateway-service/internal/api/zoho_admin_dto.go` (new) | Request/response shapes |
| Service queries | `apps-microservices/mcp-zoho-service/internal/db/queries.go` | Swap to `zoho_imports` SELECTs; `IsAdminGranted` keeps using `server_authorizations` |
| Service model | `apps-microservices/mcp-zoho-service/internal/db/models.go` | Replace `ServerRow` with `ImportRow` (same fields semantically: id, url, auth_headers, created_by) |
| Service config | `apps-microservices/mcp-zoho-service/internal/config/config.go` | Required env `ZOHO_STUB_SERVER_ID` |
| Service resolver | `apps-microservices/mcp-zoho-service/internal/routing/resolver.go` | New error category `no_admin_zoho_configured`; queries swap |
| docker-compose | gateway block | Add `ZOHO_STUB_SERVER_ID` env (default empty; operator fills after step 3 of rollout) |
| docker-compose | service block | Pass `ZOHO_STUB_SERVER_ID` env |
| CLAUDE.md | both services | Document new table, new endpoint, rollout order |
| Tests | see "Tests" below | gateway repo + handler tests; service queries + resolver tests |

## Operational rollout

1. Deploy: gateway boots, AutoMigrate creates `zoho_imports`.
2. Operator wipes prior Zoho imports:

   ```sql
   DELETE FROM mcp_servers WHERE LOWER(tool_prefix) LIKE 'zoho%' AND template_slug <> '';
   ```

   The stub row (`tool_prefix='zoho' AND template_slug=''`) stays.
3. Operator registers the admin Zoho:

   ```bash
   curl -X POST https://<gateway>/api/v1/zoho-imports/admin \
        -H "Authorization: Bearer <admin-jwt>" \
        -H "Content-Type: application/json" \
        -d '{"name":"Zoho CRM","url":"https://mcp.zoho.eu/<admin-id>","auth_headers":{"Authorization":"Bearer <admin-zoho-token>"}}'
   ```

4. Operator captures the stub row's UUID:

   ```sql
   SELECT id FROM mcp_servers WHERE tool_prefix='zoho' AND template_slug='' AND url='http://mcp-zoho-service:8596/mcp' LIMIT 1;
   ```

   Pastes it into `.env` as `ZOHO_STUB_SERVER_ID=<uuid>` and restarts `mcp-zoho-service`.
5. Operator re-runs the `/templates` sheet-import wizard for the Zoho catalog row to recreate per-user rows.
6. Smoke: end-user A connects → call hits A's row; end-user with admin grant → call hits admin row.

## Validation rules

| Condition | Behaviour |
|---|---|
| Caller email empty | 400 `missing_end_user_email` |
| Caller in `server_authorizations(stub)`, admin row exists | Route to admin row |
| Caller in `server_authorizations(stub)`, admin row missing | JSON-RPC `-32001`, `category="no_admin_zoho_configured"` |
| Caller not admin, matching user import | Route to user row |
| Caller not admin, multiple user matches | Oldest `created_at` wins, WARN log |
| Caller not admin, no match | JSON-RPC `-32001`, `category="no_zoho_configured"` |
| Service started with empty `ZOHO_STUB_SERVER_ID` | Boot fails fast |
| Admin POST with non-empty `created_by` | Gateway repo rejects, 400 |
| Admin POST when admin row already exists | UPDATE in place |
| `auth_headers` decrypt fails | JSON-RPC `-32603`, `category="upstream_error"`, log decrypt error |
| Upstream Zoho 4xx/5xx | Relay verbatim |
| Upstream Zoho timeout (30 s) | JSON-RPC `-32603`, `category="upstream_timeout"` |

## Tests

**Gateway (Go):**

1. `repository/zoho_import_repo_test.go`:
   - `CreateUserImport` round-trips.
   - `UpdateOrCreateAdmin` creates first time, updates second time.
   - `UpdateOrCreateAdmin` with `created_by != ""` returns validation error.
   - `GetAdmin` returns oldest active admin row.
   - `DeleteAdmin` clears the singleton.

2. `api/zoho_admin_handlers_test.go`:
   - `POST /api/v1/zoho-imports/admin` creates (201) then updates (200) the singleton.
   - `POST` without admin auth → 401/403.
   - `GET` returns row with redacted auth_headers; 404 when empty.
   - `DELETE` clears; subsequent GET → 404.

3. `api/google_handlers_test.go` extension:
   - Sheet import with template slug `zoho-crm` → row lands in `zoho_imports`, `mcp_servers` unchanged.
   - Sheet import with non-Zoho template → existing path: row lands in `mcp_servers`.
   - `detectZohoTemplate("zoho")`, `detectZohoTemplate("zoho-crm")`, `detectZohoTemplate("zoho-mail")` → true. `detectZohoTemplate("zohoesque-other")` (any non-matching slug) → false.

**Service (Go):**

1. `internal/db/queries_test.go`:
   - `FindAdminZohoImport` returns the active admin row.
   - `FindUserZohoImport` matches by exact email and by login portion.
   - Both skip `is_active=0`.

2. `internal/routing/resolver_test.go`:
   - Admin-grant + admin row exists → admin URL.
   - Admin-grant + no admin row → `ErrNoAdminZohoConfigured` (new sentinel).
   - Non-admin + matching user row → user URL.
   - Non-admin + no match → `ErrNoZohoConfigured`.
   - Cache hit count unchanged after second call within TTL.

## Impact summary

| Component | LOC estimate |
|---|---|
| Gateway model + migration | ~30 |
| Gateway repo | ~120 |
| Gateway admin handler + DTO + router | ~150 |
| Gateway sheet-import dispatch | ~30 |
| Gateway tests | ~200 |
| Service queries + model + config | ~60 |
| Service resolver | ~20 |
| Service tests | ~100 |
| docker-compose + CLAUDE.md | ~50 |
| Total | ~760 LOC |

## Risks

- **Stub server ID drift.** Service boot validates `ZOHO_STUB_SERVER_ID`; if the operator forgets step 4 of the rollout, the service refuses to start. Acceptable: fail-fast beats silent admin-gate misfire.
- **Wipe step is destructive.** Operator must execute the DELETE consciously. Documented in CLAUDE.md rollout section; the SQL is anchored to `tool_prefix LIKE 'zoho%' AND template_slug <> ''` to avoid hitting the stub or non-Zoho rows.
- **Two writers, one key.** Both gateway and service hold `ENCRYPTION_KEY`. Key rotation must rotate both simultaneously. Same risk as today; no new exposure.
- **Slug-based detection.** A future non-Zoho template whose slug starts with "zoho" would mis-route. Mitigation: detection lives in one helper (`detectZohoTemplate`) and is unit-tested. Add a catalog comment requesting Zoho-namespaced slugs.
- **Admin row vs gateway stub coupling.** The stub UUID is referenced from `server_authorizations`. If an operator deletes the stub `mcp_servers` row without thinking, all admin grants point at a stale ID. Mitigation: document the stub's permanence; add an `ON DELETE RESTRICT` or note in CLAUDE.md.

## Open questions (resolved before merge)

- Admin REST shape: chose `POST /api/v1/zoho-imports/admin` returning the row. Alternative `PUT` would have been more REST-pure but the singleton semantics make POST-as-upsert more idiomatic for this codebase (see `/api/v1/bdd/used/tables/import`).
- Auth_headers redaction on GET: returns key names only, not values. Same pattern as `mcp_servers` GET in this repo.
- Frontend view: deferred to v1.1. REST-only for v1.
