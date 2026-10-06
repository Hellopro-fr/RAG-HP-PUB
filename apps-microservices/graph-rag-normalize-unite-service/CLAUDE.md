# graph-rag-normalize-unite-service
gRPC service for unit normalization — converts heterogeneous measurement units into canonical forms using the `pint` library.

## Tech Stack
- **Language:** Python 3.10
- **Protocol:** gRPC server (grpcio + protobuf)
- **Unit conversion:** pint
- **Unit tables:** `libs/unit-registry` (engine + frozen fallback); live units from unit-registry-service
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker gRPC port:** 50057
- Build is Docker-only

## Folder Structure
```
app/
  main.py                          # Entrypoint — starts gRPC server
  config.py                        # pydantic-settings
application/
  normalization_use_case.py        # Business logic (unit normalization)
infrastructure/
  grpc_server.py                   # gRPC server definition
  unit_normalization_service.py    # wiring: unit_state + Normalizer (engine lives in libs/unit-registry)
  unit_state.py                    # UnitStateHolder: build-new-then-swap bundle, version/gap logic
  unit_events_consumer.py          # RabbitMQ fanout `normalization.units` consumer + resync
  registry_client.py               # ListUnits(status=ACTIVE) on unit-registry-service
  unit_metrics.py                  # unit_registry_* Prometheus metrics
```

## Live units
- Boots on the frozen fallback tables, then loads every ACTIVE unit from `unit-registry-service`
  (`UNIT_REGISTRY_GRPC_ADDR`) and follows the `normalization.units` fanout (`RABBITMQ_URL`, `UNITS_EXCHANGE`).
- Each event patches one unit, rebuilds the pint registry off to the side (~0.3 s) and swaps it; a version gap
  or a reconnect triggers a full reload. Empty `RABBITMQ_URL` = fallback tables only.
- Never add a unit in code: use the `create_unit` MCP tool / `RegisterUnit` RPC.
- Tests: `scripts/unit-registry-test.sh apps-microservices/graph-rag-normalize-unite-service -q`.

## Conventions
- Hexagonal Architecture
- Synchronous gRPC server (no uvloop — uses blocking `serve()`)
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
- gRPC service on port **50057** (no REST endpoints)

## Dependencies
- **Consumed by:** normalize-unite-processor, normalize-unite-retry-processor, API recherche services, mcp-normalize-unite-service (MCP tools, `NormalizeQuantity` only)
