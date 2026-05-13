# api-catalog-service

Centralized registry of platform services + endpoints. Owns scanner, DB, and gRPC API. Consumed by account-service-backend (CRUD) and api-gateway-go (routing source).

## Tech Stack

- Go 1.24
- google.golang.org/grpc
- GORM v2 + MySQL (gateway-mysql, DB `catalog_db`)
- HTTP client (REST + /api-info probes)
- jhump/protoreflect (gRPC reflection client)

## Run

```bash
cd apps-microservices/api-catalog-service
go run ./cmd/server/
```

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-08-api-catalog-design.md`
- Plan: `docs/superpowers/plans/2026-05-08-api-catalog.md`
