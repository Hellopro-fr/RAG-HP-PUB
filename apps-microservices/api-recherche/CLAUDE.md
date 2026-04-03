# api-recherche

Search API that queries Milvus vector database and generates LLM-augmented responses. Supports both REST and WebSocket streaming.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Gunicorn (8 uvicorn workers)
- **Vector DB:** Milvus (pymilvus)
- **LLM:** OpenAI, Google GenAI
- **gRPC:** Protobuf stubs for embedding/reranking services
- **Cache:** Redis (fastapi-cache2)
- **Shared libs:** `common_utils`, `grpc-stubs`

## Build / Run

- **Port:** 8510
- **Run:** `gunicorn -w 8 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8510 --timeout 120 main:app`
- **Tests:** `pytest tests/`
- **Docker build:** multi-stage, compiles protobuf stubs at build time

## Folder Structure

```
api-recherche/
  main.py                    # FastAPI app, Redis lifespan, CORS
  app/
    core/
      credentials.py         # Settings (PROJECT_NAME, etc.)
      recherche.py           # search_in_milvus, streaming variants
      ConnexionManager.py    # WebSocket connection manager
    router/
      search.py              # POST /search (REST)
      searchws.py            # WS /ws/search (streaming)
    schemas/
      search.py              # SearchRequestWs, SearchResponse
    utils/
  tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/search` | Search Milvus with optional Redis cache (7-day TTL) |
| `WS` | `/ws/search` | Streaming search via WebSocket |
| `GET` | `/` | Health check |

## Conventions

- Redis cache on search results with 7-day TTL (opt-in via `cache` field).
- WebSocket sends incremental JSON updates during search pipeline.
- Worker PID included in log format for multi-worker debugging.

## Dependencies on Other Services

- **Milvus** (vector similarity search)
- **Redis** (result caching)
- **embedding-model-service** / **reranking-model-service** (via gRPC)
- **LLM providers** (OpenAI, Google GenAI)
