# account-service-backend

Centralized SSO and OAuth2 Authorization Server for the Hellopro platform.

## Tech Stack

- Go 1.24
- net/http (standard library)
- GORM v1.25 (MySQL via go-sql-driver/mysql)
- JWT HS256 (golang-jwt/jwt/v5)
- AES-256-GCM (crypto/aes)
- Docker (multi-stage golang:1.24-alpine -> alpine:3.20), exposed port 8600

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

## Environment Variables (selected)

| Variable | Default | Description |
|---|---|---|
| `MCP_GATEWAY_INTERNAL_URL` | — | In-cluster mcp-gateway base URL (e.g. `http://mcp-gateway-service:8592`). Empty = MCP user sync disabled. Auth reuses `INTERNAL_ADMIN_TOKEN`. |
