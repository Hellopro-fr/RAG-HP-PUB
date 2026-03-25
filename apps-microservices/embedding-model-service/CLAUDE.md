# embedding-model-service

gRPC service for text embedding generation, tokenization, chunking via Triton Inference Server (CamemBERT-large).

## Tech Stack

- Python 3.10, asyncio, uvloop
- gRPC (grpcio, protobuf) on port **50052**
- Triton Inference Server client (`tritonclient[all]`)
- sentence-transformers, transformers, numpy, torch
- Prometheus metrics on port **8530**
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/embedding-model-service/Dockerfile .
  ```

## Folder Structure

```
embedding-model-service/
  app/main.py                       # Entrypoint, starts Prometheus + workers + gRPC
  application/embedding_use_case.py # Priority queue, dynamic batching, Triton inference
  infrastructure/grpc_server.py     # gRPC servicer (GetEmbeddings, Tokenize, Detokenize, ChunkText)
  requirements.txt
  Dockerfile
```

## gRPC Methods (port 50052)

| Method | Description |
|---|---|
| `GetEmbeddings` | Generate embeddings with multi-level priority (HIGH/MEDIUM/LOW) |
| `Tokenize` | Tokenize texts to token IDs |
| `Detokenize` | Decode token IDs back to text |
| `ChunkText` | Split text into chunks using model tokenizer |

## Conventions

- **Multi-level priority queue** with dedicated worker pools (high, shared, medium, low).
- Dynamic batching aggregates concurrent requests into GPU-optimal batches.
- Model: `dangvantuan/sentence-camembert-large` via Triton (`camembert-embedding`).
- Env vars: `TRITON_URL`, `EMBEDDING_BATCH_SIZE`, `HIGH_PRIORITY_SERVICES`, `MEDIUM_PRIORITY_SERVICES`.

## Dependencies on Other Services

- **Triton Inference Server** (gRPC, `TRITON_URL` env var).
