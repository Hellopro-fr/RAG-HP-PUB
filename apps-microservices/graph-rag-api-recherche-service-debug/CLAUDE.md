# graph-rag-api-recherche-service-debug
Debug variant of the Graph RAG search API — same codebase as `graph-rag-api-recherche-service`, deployed on a separate port for debugging/testing.

## Tech Stack
- Same as `graph-rag-api-recherche-service` (Python 3.10, FastAPI, Uvicorn)

## Build & Run
```bash
# Docker-only build — shares source from graph-rag-api-recherche-service
```
- **Docker port:** 8526
- Uses the same Dockerfile pattern, same source code, different exposed port

## Folder Structure
- Contains only a `Dockerfile`
- Source code is copied from `graph-rag-api-recherche-service/app/`

## Conventions
- Dedicated instance for debugging without impacting production traffic
- No separate source files — purely a deployment-level separation

## API Endpoints
- Same as `graph-rag-api-recherche-service`

## Dependencies
- Same as `graph-rag-api-recherche-service`
