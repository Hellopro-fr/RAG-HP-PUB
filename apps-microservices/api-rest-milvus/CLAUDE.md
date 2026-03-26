# api-rest-milvus

Full CRUD REST API for Milvus vector database. Provides read, create, update, delete, search, stats, distinct values, and URL verification operations.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Vector DB:** Milvus (pymilvus)
- **Shared lib:** `common_utils`

## Build / Run

- **Port:** 8517
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8517`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-rest-milvus/
  main.py                            # FastAPI app, Milvus connection on startup
  app/
    core/
      api_rest_milvus.py             # get_milvus_connection, core operations
      credentials.py                 # Settings
    router/
      api_router.py                  # Aggregates all sub-routers
      create.py                      # POST operations
      read.py                        # GET operations
      read_post.py                   # POST-based search queries
      update.py                      # PUT operations
      delete.py                      # DELETE operations
      check_urls.py                  # URL verification
      stats.py                       # Collection statistics
      distinct.py                    # Distinct field values
    schemas/
      check_doublon_shemas.py        # Shared schemas
    utils/
  nginx-rest-milvus.conf            # Nginx load balancing config
```

## API Endpoints (grouped by router tag)

| Tag | Description |
|-----|-------------|
| GET | Read operations on Milvus collections |
| POST Search | Query Milvus via POST body |
| POST | Create/insert records |
| PUT | Update existing records |
| DELETE | Delete records |
| URL Verification | Check URL existence in collections |
| Statistics | Collection stats and counts |
| GET Distinct Values | Unique field values |

## Conventions

- Milvus connection pre-loaded at startup via `lifespan`.
- Router aggregation pattern via `api_router.py` including all sub-routers.

## Dependencies on Other Services

- **Milvus** (vector database)
