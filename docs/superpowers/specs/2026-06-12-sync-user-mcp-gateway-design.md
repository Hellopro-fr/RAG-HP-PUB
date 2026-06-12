# Sync Account-Service Users to MCP Gateway — Design

**Date:** 2026-06-12
**Branch:** `features/sync-user-mcp-portal` (from `origin/features/poc`)
**Status:** Approved

## Goal

Let an account-service admin push users from the SSO user base into the MCP gateway's
`gateway_users` table, pre-provisioning them with the `config-only` role. Two entry
points in the admin/users UI: a per-row button (sync one user) and a global button
(sync all allowed users). Sync is idempotent: users that already exist in the gateway
are skipped, never modified.

## Decisions

| Question | Decision |
|---|---|
| Sync target | Per-row button + global "sync all" button |
| Existing gateway users | Skipped untouched (no role/flag overwrite) |
| Role for created users | `config-only` (gateway default) |
| `is_allowed` for created users | `false` (gateway default; gateway admin grants access later) |
| Bulk scope | Only account-service users with `is_allowed = true` |
| Per-row on blocked account user | Allowed (explicit admin intent; gateway row inert with `is_allowed=false`) |
| Auth between services | Reuse existing shared secret: account `INTERNAL_ADMIN_TOKEN` = gateway `ACCOUNT_INTERNAL_TOKEN`, header `X-Admin-Token`. No new secret. |
| Data carried over | `email`, `display_name` |

## Architecture

```
account-service-frontend (Vue)
  AdminUsersView.vue  ── per-row button ──►  POST /api/v1/admin/users/{email}/sync-mcp
                      ── global button  ──►  POST /api/v1/admin/users/sync-mcp
                                                  │ (cookie session, requireAdmin)
account-service-backend (Go)
  gateway sync client ───────────────────►  POST /api/v1/internal/users/sync
        X-Admin-Token: INTERNAL_ADMIN_TOKEN       │ (auth-middleware skip-list)
mcp-gateway-service (Go)
  validates token == cfg.AccountInternalToken (constant-time)
  UserRepo.SyncUsers: create-if-missing, role=config-only, is_allowed=false
```

All browser traffic stays on the account-service backend; the gateway is only reached
server-to-server. This mirrors the existing internal-endpoint patterns:
gateway `/api/v1/internal/runner/sync` (X-Admin-Token + skip-list) and
account `/internal/credentials/{name}` (same header, same secret pair).

## Component Changes

### 1. mcp-gateway-service (Go)

**New endpoint:** `POST /api/v1/internal/users/sync`

- Mounted in `internal/api/handler.go` next to the runner sync route; handler lives in
  `internal/api/internal_handlers.go` (same file as `handleRunnerSync`).
- Path added to the auth-middleware skip-list (`internal/auth/middleware.go`, the map at
  line ~67) so the JWT/session middleware does not intercept it.
- Auth: header `X-Admin-Token` compared to `cfg.AccountInternalToken` with
  `subtle.ConstantTimeCompare`. Empty configured token ⇒ always 401 (same rule as
  runner sync). Method other than POST ⇒ 405.

**Request body:**

```json
{ "users": [ { "email": "user@hellopro.fr", "display_name": "User Name" } ] }
```

**Response (200):**

```json
{ "created": ["a@hellopro.fr"], "skipped": ["b@hellopro.fr"] }
```

- Emails are normalized (trim + lowercase) before lookup, matching existing
  `UserRepo` conventions.
- Any entry with an empty email (after trim) ⇒ 400 for the whole batch. Strict
  contract; the account backend never sends empty emails, so this only guards
  misuse.

**New repository method:** `UserRepo.SyncUsers(users []SyncUserInput) (created, skipped []string, err error)`

- For each input: `SELECT` by email; found ⇒ append to `skipped`; not found ⇒ `INSERT`
  with `Role: "config-only"`, `IsAllowed: false`, `LoginCount: 0`, `DisplayName` from
  input. Existing rows are never updated.
- Unique-constraint race (user logs in mid-sync): treat duplicate-key insert error as
  `skipped`.

### 2. account-service-backend (Go)

**New config field:** `MCPGatewayInternalURL` from env `MCP_GATEWAY_INTERNAL_URL`
(no default; empty ⇒ sync endpoints return 503 "MCP gateway sync not configured").
Outbound token reuses the existing `InternalAdminToken` config field.

**New client:** `internal/gatewaysync/client.go` — small HTTP client modeled on
`internal/logout/broadcaster.go`: `http.Client` with timeout (5 s), POSTs the batch
to `${MCP_GATEWAY_INTERNAL_URL}/api/v1/internal/users/sync` with `X-Admin-Token`,
decodes `{created, skipped}`.

**New routes** (both behind existing `requireAdmin` middleware):

| Route | Behavior |
|---|---|
| `POST /api/v1/admin/users/{email}/sync-mcp` | Look up the user (404 if unknown), sync that single user regardless of their account-service `is_allowed` state. Implemented as a new `{op}` in the existing `AdminUserHandler` op dispatch. |
| `POST /api/v1/admin/users/sync-mcp` | Load all users with `is_allowed = true`, send as one batch. Registered as an explicit pattern — Go 1.22 ServeMux precedence keeps it from colliding with `{email}/{op}`. |

**Responses:** relay the gateway's `{created, skipped}` JSON. Gateway unreachable /
non-200 ⇒ 502 `{"error":"mcp gateway sync failed: …"}`.

### 3. account-service-frontend (Vue 3)

**`src/api/users.ts`:**

```typescript
export interface McpSyncResult { created: string[]; skipped: string[] }
export function syncUserToMcp(email: string): Promise<McpSyncResult>
export function syncAllUsersToMcp(): Promise<McpSyncResult>
```

**`src/views/AdminUsersView.vue`:**

- Per-row icon button (lucide icon, e.g. `ArrowRightLeft` or `CloudUpload`) in the
  existing actions column, wired through the existing `action()` confirm-wrapper:
  confirm text `Sync <email> vers MCP gateway ?`.
- Global button "Sync MCP" next to the existing header controls, with its own confirm
  (`Sync tous les utilisateurs autorisés vers MCP gateway ?`).
- On success, show an info line: `MCP sync : N créé(s), M déjà présent(s)` (new
  non-error status message, same styling slot as the existing error display).
- No table reload needed (sync does not change account-service rows).

## Error Handling

- Sync is idempotent and re-runnable: skip-existing semantics mean a failed bulk run
  can simply be retried.
- Per-user insert errors other than duplicate-key abort the batch with 500 (surfaced
  to UI via the 502 relay); already-created users from the partial run are reported
  as skipped on retry.
- Frontend surfaces backend error messages through the existing `error.value` path.

## Testing

TDD (red-green) per repo conventions; local = unit tests only (remote-only infra).

- **Gateway:** table-driven handler tests mirroring `internal_handlers_test.go`
  (auth: missing/wrong/empty-configured token ⇒ 401; method ⇒ 405; create vs skip;
  duplicate-key race ⇒ skipped; email normalization). Repo tests for `SyncUsers`.
- **Account backend:** handler tests mirroring `admin_user_handlers_test.go`
  (admin gating, 404 unknown email, single + bulk happy paths with a fake gateway
  server, 502 on gateway failure, 503 when URL unconfigured, bulk filters
  `is_allowed=true`).
- **Frontend:** Vitest for the two new api functions (fetch mock) and button wiring
  (confirm + result message) following existing view test patterns.

## Deployment

- `docker-compose.yml`: add `MCP_GATEWAY_INTERNAL_URL=http://mcp-gateway-service:8592`
  to the account-service-backend service env. No new secret to provision.
- No DB migration: gateway table and defaults already exist.

## Out of Scope

- Updating existing gateway users (role/flag changes stay in the gateway admin UI).
- Reverse sync (gateway → account-service).
- Auto-sync on login or on user creation (manual admin action only).
- Deleting gateway users when account users are removed.
