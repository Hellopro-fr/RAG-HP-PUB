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
