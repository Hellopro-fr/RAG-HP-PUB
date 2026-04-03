# api-classification

Product classification API (v1) that automatically categorizes products using LLM and vector search. Supports single and batch classification with distributed processing.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **LLM:** via `common_utils.grpc_clients.llm_client` (gRPC)
- **Search:** Embeds `api-recherche` code as `api_recherche_lib` at build time
- **Cache:** Redis (classification cache)
- **Metrics:** Prometheus (`/metrics` via WSGI mount)
- **Shared libs:** `common_utils`, `grpc-stubs`

## Build / Run

- **Port:** 8577
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8577`
- **Docker build:** copies `api-recherche/app` as `api_recherche_lib`, rewrites imports via `sed`

## Folder Structure

```
api-classification/
  main.py                        # FastAPI app, Redis lifespan, replica ID
  app/
    core/
      classifier.py              # ProductClassifier logic
      search.py                  # Search API connection test
    router/
      classification.py          # All classification endpoints
    schemas/
      classification.py          # ProductInput, BatchProductsInput, etc.
    utils/
  nginx-classification.conf      # Nginx config for load balancing
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/classification/...` | Single/batch product classification |
| `GET` | `/` | Root info |
| `GET` | `/health` | Health check |

## Conventions

- Replica ID (container hostname) added to response headers (`X-Replica-ID`).
- In-memory distribution metrics track request counts per replica.
- Redis used for classification result caching.

## Dependencies on Other Services

- **api-recherche** (code embedded at build time as `api_recherche_lib`)
- **LLM service** (via gRPC `llm_client`)
- **Redis** (classification cache)
- **Milvus** (via recherche lib)
