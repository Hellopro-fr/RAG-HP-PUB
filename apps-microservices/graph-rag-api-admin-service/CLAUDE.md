# graph-rag-api-admin-service
Admin API for graph database management — product CRUD, supplier data, node operations, and Cypher query execution.

## Tech Stack
- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **gRPC:** grpcio (via shared `grpc-stubs` + `common-utils` libs)
- **LLM:** LangGraph, LangChain-core
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8527
```
- **Docker port:** 8527
- Build is Docker-only (proto compilation + shared libs)

## Folder Structure
```
app/
  main.py              # FastAPI app + router registration
  config.py            # pydantic-settings
  domain/models.py     # DTOs
  routers/             # admin, fournisseur, nodes, product
  services/            # cypher_builder, fournisseur/node/product_service
  infrastructure/      # clients, llm_service
```

## Conventions
- Same Clean Architecture pattern as `graph-rag-api-recherche-service`
- No query/recommendation routers — admin-only subset
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
| Method | Path | Tag |
|--------|------|-----|
| * | `/produits/` | Produits |
| * | `/fournisseur/` | Fournisseur |
| * | `/nodes/` | Admin |
| * | `/admin/` | Admin |
| GET | `/health` | Health |

## Dependencies
- **gRPC:** database-connector (50055), other gRPC services via shared clients
