# database-recherche-service

gRPC server providing vector search (dense, hybrid, classic) over Milvus/Zilliz with priority queuing and dynamic batching.

## Tech Stack

- Python 3.10, grpcio/grpcio-tools, pymilvus, uvloop, protobuf
- Shared libs: `libs/common-utils`, `libs/grpc-stubs` (auto-generated from `protos/`)
- Docker base: `python:3.10-slim` + protobuf-compiler
- Architecture: Clean Architecture (domain / application / infrastructure)

## Build / Run

- **Build**: `docker build -f Dockerfile -t database-recherche-service .` (from repo root)
- **Run**: Docker; requires `ZILLIZ_URI`, `ZILLIZ_PORT`, `ZILLIZ_USER`, `ZILLIZ_PASSWORD` env vars
- **Port**: gRPC on 50054

## Folder Structure

```
app/main.py                    # Entry point, wires MilvusClient -> SearchUseCase -> gRPC server
domain/search_result.py        # SearchResultEntity dataclass
application/search_use_case.py # Use cases: search, hybrid_search, classic_search, get_schema (+ batch variants)
infrastructure/
  grpc_server.py               # DatabaseSearchServiceImpl - priority queue, worker pools, batching
  milvus_client.py             # MilvusClient - search, hybrid_search, classic_search with context modes
Dockerfile
requirements.txt
```

## gRPC API (port 50054)

| RPC Method | Description |
|------------|-------------|
| `Search` | Dense vector search (COSINE) with dynamic batching |
| `HybridSearch` | Dense + sparse BM25 search with configurable ranker (Weighted/RRF) |
| `ClassicSearch` | Filter-based query (no vector) |
| `GetSchema` | Returns collection field types |

## Conventions

- **Priority queuing**: 3 levels (High/Medium/Low) based on `source_service` header
  - High: api-recherche-service, api-chat-llm-service
  - Medium: api-classification-service
  - Low: everything else
- **Dynamic batching**: groups identical search requests (same collection, top_k, filters) into single Milvus call
- **Worker pools**: dedicated High thread pool (20%), shared/medium/low pools with Zilliz rate limiter
- **Context modes**: `adjacent` (prev/next chunks), `full` (all chunks of same document)
- Collections: `produits_3`, `devis`, `echanges`, `siteweb_2`, `pjechanges`
- Configurable via env: `TOTAL_MAX_CONCURRENT_REQUESTS`, `DB_BATCH_SIZE`, `DB_MAX_CONCURRENT_ZILLIZ_DEFAULT`

## Dependencies on Other Services

- **Clients**: api-recherche-service, api-chat-llm-service, api-classification-service
- **Infrastructure**: Milvus/Zilliz Cloud
