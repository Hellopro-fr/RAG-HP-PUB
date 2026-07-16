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

## Auth Policy fields

Services + endpoints carry auth metadata consumed by api-gateway-go's verifier:

- `Service.auth_policy` (public/bearer/admin-key) + `Service.public_paths` (exact-match bypass list).
- `Endpoint.auth_policy` — optional per-endpoint override (NULL = inherit service default).
- `Service.has_endpoint_overrides` — server-computed hint; lets the gateway refresher skip
  `ListEndpoints` for services with no overrides.
- `UpdateEndpoint(UpdateEndpointRequest)` RPC sets/clears a single endpoint's override.
- DB columns seeded via `init-db/02_seed_auth_policy.sql` (all existing services → PUBLIC;
  `graphdlq-service` keeps `/dlq/queues` as a public path).

Spec: `docs/superpowers/specs/2026-05-28-apitokenverifier-catalog-driven-design.md`.

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-08-api-catalog-design.md`
- Plan: `docs/superpowers/plans/2026-05-08-api-catalog.md`
