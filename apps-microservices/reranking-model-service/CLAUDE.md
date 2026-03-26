# reranking-model-service

gRPC service for document reranking using BGE-Reranker-v2-m3 via Triton Inference Server.

## Tech Stack

- Python 3.10, asyncio, uvloop
- gRPC (grpcio, protobuf) on port **50053**
- Triton Inference Server client (`tritonclient[all]`)
- sentence-transformers (CrossEncoder tokenizer), numpy
- Prometheus metrics on port **8530**
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/reranking-model-service/Dockerfile .
  ```

## Folder Structure

```
reranking-model-service/
  app/main.py                        # Entrypoint, starts Prometheus + gRPC
  application/reranking_use_case.py  # Reranking logic, batched Triton inference
  infrastructure/grpc_server.py      # gRPC servicer (Rerank, RerankDocuments)
  requirements.txt
  Dockerfile
```

## gRPC Methods (port 50053)

| Method | Description |
|---|---|
| `Rerank` | Returns documents sorted by relevance (no scores) |
| `RerankDocuments` | Returns documents with relevance scores |

## Conventions

- Model: `BAAI/bge-reranker-v2-m3` tokenizer, Triton model name `bge-reranker`.
- Batch size: 256 documents per Triton call.
- On Triton failure, returns documents in original order (graceful degradation).

## Dependencies on Other Services

- **Triton Inference Server** (gRPC, `TRITON_URL` env var).
