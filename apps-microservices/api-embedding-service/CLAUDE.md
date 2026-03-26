# api-embedding-service

API proxy for text embedding and reranking operations. Delegates to internal gRPC-based model services.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Gunicorn (8 uvicorn workers)
- **gRPC:** Protobuf stubs for embedding and reranking model services
- **Shared libs:** `common_utils` (gRPC clients, Embedding class), `grpc-stubs`

## Build / Run

- **Port:** 8555
- **Run:** `gunicorn -w 8 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8555 --timeout 120 main:app`
- **Docker build:** multi-stage, compiles protobuf stubs at build time

## Folder Structure

```
api-embedding-service/
  main.py                    # FastAPI app
  app/
    core/
      credentials.py         # Settings
    router/
      embedding.py           # /embedding, /reranking endpoints
    schemas/
      embedding.py           # EmbeddingRequest
      reranking.py           # RerankingRequest
    utils/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/embedding` | Generate text embeddings (cleaned) |
| `POST` | `/reranking` | Rerank documents against a query |
| `GET` | `/` | Health check |

## Conventions

- Embedding uses `common_utils.embedding.Embedding` which cleans input text before embedding.
- Reranking delegates to `reranking_client.rerank_documents_with_scores` via gRPC.
- Worker PID in log format for multi-worker debugging.

## Dependencies on Other Services

- **embedding-model-service** (gRPC)
- **reranking-model-service** (gRPC)
