# graph-rag-milvus-service
gRPC service wrapping Milvus — provides vector database operations (insert, search, collection management) to other services.

## Tech Stack
- **Language:** Python 3.10
- **Protocol:** gRPC server (grpcio + protobuf)
- **Database:** Milvus (via `pymilvus`)
- **Async:** uvloop
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker gRPC port:** 50056
- Build is Docker-only (proto compilation + shared libs)

## Folder Structure
```
app/
  main.py                  # Entrypoint — connects to Milvus, sets up collections, starts gRPC
  config.py                # pydantic-settings
application/
  milvus_use_case.py       # Business logic (vector search, insert, upsert)
infrastructure/
  grpc_server.py           # gRPC server definition
  milvus_connector.py      # Milvus connection + collection setup
```

## Conventions
- Hexagonal Architecture: app -> application -> infrastructure
- Auto-creates collections on startup if they do not exist
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
- gRPC service on port **50056** (no REST endpoints)

## Dependencies
- **Direct:** Milvus vector database
- **Consumed by:** semantic-vigil-processor, normalize-unite-retry-processor, API recherche services
