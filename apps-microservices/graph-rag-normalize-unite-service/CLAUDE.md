# graph-rag-normalize-unite-service
gRPC service for unit normalization — converts heterogeneous measurement units into canonical forms using the `pint` library.

## Tech Stack
- **Language:** Python 3.10
- **Protocol:** gRPC server (grpcio + protobuf)
- **Unit conversion:** pint
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
  unit_normalization_service.py    # pint-based unit conversion
```

## Conventions
- Hexagonal Architecture
- Synchronous gRPC server (no uvloop — uses blocking `serve()`)
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
- gRPC service on port **50057** (no REST endpoints)

## Dependencies
- **Consumed by:** normalize-unite-processor, normalize-unite-retry-processor, API recherche services
