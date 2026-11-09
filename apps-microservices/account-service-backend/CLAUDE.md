# account-service-backend

Centralized SSO and OAuth2 Authorization Server for the Hellopro platform.

## Tech Stack

- Go 1.25
- net/http (standard library)
- GORM v1.31 (MySQL via go-sql-driver/mysql)
- JWT HS256 (golang-jwt/jwt/v5)
- AES-256-GCM (crypto/aes)
- Docker (multi-stage golang:1.25-alpine -> alpine:3.20), exposed port 8600

## Run

```bash
cd apps-microservices/account-service-backend
go run ./cmd/server/
```

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-04-account-service-sso-design.md`
- Plan: `docs/superpowers/plans/2026-05-04-account-service-sso.md`

## Admin API Routes (selected)

- `POST /api/v1/admin/users/{email}/sync-mcp` — push one user to the MCP gateway (`config-only`, skip-existing). Admin only.
- `POST /api/v1/admin/users/sync-mcp` — push all `is_allowed` users. Admin only. Both return `{created, skipped}`; 503 when `MCP_GATEWAY_INTERNAL_URL` unset, 502 on gateway failure.
- `GET|POST /api/v1/admin/groups`, `GET|PUT|DELETE /api/v1/admin/groups/{id}`, `POST /api/v1/admin/groups/{id}/members` (`{email}`), `DELETE /api/v1/admin/groups/{id}/members/{email}` — groups (teams). Admin only, audited (`group.*`). Tables `user_groups` / `user_group_members` (not `groups`: reserved word in MySQL 8). A member must exist in `users` (signed in once), else 404 `unknown_user`.
- `GET /internal/directory` — `X-Admin-Token`. Every user (`email`, `display_name`, `is_allowed`) and every group with its member emails. Read by apps that attach their own permissions to groups (agent task board); they cache it, so a group change reaches them within their cache TTL.

## Environment Variables (selected)

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_INTERNAL_URL` | — | In-cluster mcp-gateway base URL (e.g. `http://mcp-gateway-service:8592`). Empty = MCP user sync disabled. Auth reuses `INTERNAL_ADMIN_TOKEN`. |

## Known test debt

- Integration tests (`-tags integration`) import testcontainers, which is not in `go.mod` and needs Go >= 1.26; its MySQL wait strategy also times out on slow hosts. To run them, point `setupTestDB` at a plain `mysql:8.0` via DSN (wait for TCP, not the socket: init takes minutes on a slow disk).
- `account-service-frontend` `src/router/index.spec.ts` expects `minRole: admin` on `/admin/services`, but services are open to any authenticated user by design (comment in `router/index.ts`): the test is stale.
