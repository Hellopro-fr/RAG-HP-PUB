# graph-rag-database-connector-service
gRPC service wrapping Neo4j — provides graph database operations (CRUD, Cypher queries, schema management) to all other services.

## Tech Stack
- **Language:** Python 3.10
- **Protocol:** gRPC server (grpcio + protobuf)
- **Database:** Neo4j (via `neo4j` driver + `langchain-community`)
- **Async:** uvloop
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker gRPC port:** 50055
- Build is Docker-only (proto compilation + shared libs)

## Folder Structure
```
app/
  main.py                  # Entrypoint — starts gRPC server + applies Neo4j schema
  config.py                # pydantic-settings
application/
  graph_database_use_case.py   # Business logic (Cypher execution, schema setup)
infrastructure/
  grpc_server.py           # gRPC server definition
  neo4j_connector.py       # Neo4j connection wrapper
```

## Conventions
- Hexagonal Architecture: app -> application (use cases) -> infrastructure
- Applies unique constraints and indexes on startup (race condition prevention)
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
- gRPC service on port **50055** (no REST endpoints)

## Dependencies
- **Direct:** Neo4j (bolt connection)
- **Consumed by:** All processors, all API services, retry processor
