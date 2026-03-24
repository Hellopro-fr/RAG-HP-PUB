# optimize-service

FastAPI service for LLM-powered product title/description optimization.

## Tech Stack

- Python 3.10
- FastAPI + uvicorn on port **8563**
- gRPC client (to llm-service)
- OpenAI client, pydantic-settings
- Prometheus metrics at `/metrics`
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/optimize-service/Dockerfile .
  ```
- Tests: `pytest tests/` (conftest.py present)

## Folder Structure

```
optimize-service/
  main.py                              # FastAPI app, CORS, OpenAPI customization
  app/
    router/optimize/optimize.py        # POST /qwen/v2 endpoint
    core/
      optimize/traitement_donnees.py   # Prompt generation + response cleaning
      credentials.py                   # Settings (DOCUMENT_ROOT, etc.)
    schemas/
      optimize/optimize.py             # OptimRequest, BatchOptimRequest, etc.
      base.py, message.py
    utils/
      handling.py, params.py, response.py
      router/tags.py
  init.sh, runs.sh
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8563)

| Method | Path | Description |
|---|---|---|
| POST | `/qwen/v2` | Batch product optimization via LLM |
| GET | `/metrics` | Prometheus metrics |

## Conventions

- Batch processing: all products processed concurrently via `asyncio.gather`.
- LLM responses parsed as JSON; falls back to `ast.literal_eval` on decode failure.
- Prometheus manual instrumentation: duration observed once, count incremented per product.

## Dependencies on Other Services

- **llm-service** (gRPC, via `common_utils.grpc_clients.llm_client`)
