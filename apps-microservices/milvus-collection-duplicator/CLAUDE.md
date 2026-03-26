# milvus-collection-duplicator

FastAPI service to duplicate Milvus collections with BM25 sparse embedding support.

## Tech Stack

- Python 3.10
- FastAPI + uvicorn on port **8521**
- pymilvus >= 2.5.0
- Background threading for long-running jobs

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/milvus-collection-duplicator/Dockerfile .
  ```

## Folder Structure

```
milvus-collection-duplicator/
  main.py                              # FastAPI app with lifespan (Milvus connect)
  app/
    router/duplication_router.py       # All API endpoints
    core/milvus_connection.py          # Milvus connection + duplication logic
    schemas/duplication_schemas.py     # Request/response models
  requirements.txt
  Dockerfile
```

## API Endpoints (port 8521)

| Method | Path | Description |
|---|---|---|
| GET | `/` | Welcome message |
| GET | `/health` | Health check |
| POST | `/duplicate` | Start a duplication job (background) |
| GET | `/duplicate/{job_id}/status` | Check job progress |
| GET | `/duplicate/jobs` | List all jobs |
| POST | `/duplicate/retry` | Retry failed rows from error log |
| POST | `/duplicate/rename` | Rename a collection (metadata-only) |

## Conventions

- Schema cloned via `copy.deepcopy`, adds `sparse_embedding` field with Milvus 2.6 built-in BM25.
- Uses `query_iterator` for streaming pagination (supports 1M+ rows).
- Jobs run in background threads with in-memory state store.
- Parallel workers configurable for insert throughput.
- Error rows logged to file for later retry.

## Dependencies on Other Services

- **Milvus** (direct connection via pymilvus, `MILVUS_URI`/`MILVUS_PORT` env vars)
