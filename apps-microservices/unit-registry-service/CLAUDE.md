# unit-registry-service

Owns the normalization units (and unit types) in MySQL `normalization_db` and serves CRUD over gRPC
(`protos/grpc_stubs/unit_registry.proto`). Every unit write runs guards G1–G6 on the full registry, then
commits row + `registry_version` bump + outbox event in one transaction; a relay publishes the event to
the RabbitMQ fanout `normalization.units`, and every `graph-rag-normalize-unite-service` replica hot-reloads.
Spec: `docs/superpowers/specs/2026-10-06-unit-registry-combined-design.md`. Shared logic: `libs/unit-registry`.

## Tech Stack
Python 3.10, grpcio (sync server), SQLAlchemy 2 + PyMySQL, pika, prometheus-client, pydantic-settings, pint 0.24.4.

## Ports / Env
- gRPC **50059**, HTTP **8571** (`/health` = DB reachable, `/metrics`). Compose `expose` only.
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` (`normalization_user`) / `MYSQL_PASSWORD` / `MYSQL_DB` (`normalization_db`)
- `RABBITMQ_URL`, `UNITS_EXCHANGE` (`normalization.units`), `UNITS_ADMIN_KEY` (≥ 16 chars; Bearer for write RPCs)

## Database bootstrap
`init-db/10_normalization_db.sh` creates the database and user. It is **NOT** auto-mounted into `mysql`: a single-file
bind inside the read-only `docker-entrypoint-initdb.d` mount stops mysql from starting. Run it once by hand in every
environment (fresh or existing volume) before the service's first start:
```bash
docker exec -i -e NORMALIZATION_MYSQL_PASS="$NORMALIZATION_MYSQL_PASS" mysql bash < apps-microservices/unit-registry-service/init-db/10_normalization_db.sh
```
Tables are created at startup (`create_all`); `bootstrap()` seeds the 36 dimensions, the 233 legacy units and the
`DIMENSION`/`CAPACITY` types when their tables are empty.

## Folder Structure
```
app/            config.py (Settings), main.py (wiring)
application/    unit_service.py, types_service.py, errors.py, models.py, clock.py
infrastructure/ db/ (models, repository, bootstrap), grpc/ (servicer, auth, server),
                messaging/ (publisher, relay), http_server.py
init-db/        10_normalization_db.sh
```

## Rules
- Write RPCs: RegisterUnit, UpdateUnit, DeleteUnit, CreateUnitType, UpdateUnitType, DeactivateUnitType, SetDimensionTypes.
- Unit types are metadata: they never bump `registry_version` and emit no event.
- P2-only fields (`kind`, `case_sensitive`, `rewrite_expression`, `label_condition`, `canonical_override`) are rejected.
- The fanout drops events published while no replica queue is bound; replicas therefore resync with ListUnits on every (re)connect.

## Tests
`scripts/unit-registry-test.sh apps-microservices/unit-registry-service -q` (SQLite). The real-MySQL collation test:
see `tests/test_mysql.py` (`MYSQL_TEST_URL`).

## Dependencies
- **Consumed by:** `mcp-normalize-unite-service` (gRPC), `graph-rag-normalize-unite-service` (`ListUnits` resync + events).
- **Depends on:** MySQL (`mysql` compose service), RabbitMQ.
