# api-classification-v2

Product classification API (v2 -- test variant) with updated classification logic. Same architecture as v1 but without Prometheus metrics.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **LLM:** via `common_utils.grpc_clients.llm_client` (gRPC)
- **Search:** Embeds `api-recherche` code as `api_recherche_lib` at build time
- **Cache:** Redis (classification cache)
- **Shared libs:** `common_utils`, `grpc-stubs`

## Build / Run

- **Port:** 8578
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8578`
- **Docker build:** same pattern as v1 -- copies `api-recherche/app`, rewrites imports

## Folder Structure

```
api-classification-v2/
  main.py                        # FastAPI app, Redis lifespan
  compare-v1-v2.py               # Script to compare v1 vs v2 results
  deploy-v2.sh                   # Deployment script
  app/
    core/
      classifier.py              # ProductClassifier (v2 logic)
      search.py                  # Search API connection test
    router/
      classification.py          # Classification endpoints
    schemas/
      classification.py          # ProductInput, BatchProductsInput, etc.
    utils/
  nginx-classification-v2.conf   # Nginx config
```

## API Endpoints

Same structure as v1 under `/classification/...` prefix.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/classification/...` | Single/batch product classification |
| `GET` | `/` | Root info |
| `GET` | `/health` | Health check |

## Conventions

- Replica ID in `X-Replica-ID` response header.
- `compare-v1-v2.py` utility for A/B testing v1 vs v2 classification results.

## Dependencies on Other Services

Same as `api-classification`: api-recherche (embedded), LLM (gRPC), Redis, Milvus.
