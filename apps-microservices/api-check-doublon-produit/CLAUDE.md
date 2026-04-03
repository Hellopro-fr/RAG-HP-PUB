# api-check-doublon-produit

API to check for duplicate products in Milvus using vector similarity search. Supports single and batch lookups.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Vector DB:** Milvus (pymilvus)
- **Shared lib:** `common_utils`

## Build / Run

- **Port:** 8516
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8516`
- **Tests:** `pytest tests/`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-check-doublon-produit/
  main.py                          # FastAPI app, Milvus connection on startup
  app/
    core/
      check_doublon.py             # search_in_milvus, get_milvus_connection
      credentials.py               # Settings
    router/
      check_doublon.py             # /check-doublon, /check-doublon-lot
    schemas/
      check_doublon_shemas.py      # SearchRequest, SearchResponse, etc.
    utils/
  tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/check-doublon` | Check single product for duplicates |
| `POST` | `/check-doublon-lot` | Batch duplicate check (parallel via asyncio.gather) |
| `GET` | `/` | Health check |

## Conventions

- Milvus connection pre-loaded at startup via `lifespan` context.
- Batch endpoint uses `asyncio.gather` for parallel processing.
- Response includes `is_doublon`, `from_similarity`, and `score` fields.

## Dependencies on Other Services

- **Milvus** (vector similarity search)
