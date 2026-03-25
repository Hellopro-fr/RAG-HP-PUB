# api-rest-milvus-bkp

Legacy/backup variant of the Milvus REST API. Provides a generic query execution interface and RabbitMQ-based ingestion. Largely superseded by `api-rest-milvus`.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Vector DB:** Milvus (pymilvus)
- **Messaging:** RabbitMQ (via `common_utils`)
- **Shared lib:** `common_utils`

## Build / Run

- **Port:** 8515
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8515`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-rest-milvus-bkp/
  main.py                     # FastAPI app (generic /execute endpoint)
  milvus_client.py            # execute_query helper
  app/
    core/
      credentials.py          # Settings
      ingestion/ingestion.py  # routing_key_collection
    router/ingestion/
      ingestion.py            # /publier, /publier-lot (RabbitMQ publish)
    schemas/
      base.py
      message.py
      ingestion/ingestion.py  # Request/response models
    utils/
  tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/execute` | Execute generic Milvus query (collection + query dict) |
| `POST` | `/publier` | Publish message to RabbitMQ |
| `POST` | `/publier-lot` | Batch publish to RabbitMQ |

## Conventions

- Generic query interface via `QueryRequest(collection_name, query)`.
- Kept as backup; prefer `api-rest-milvus` for new development.

## Dependencies on Other Services

- **Milvus** (vector database)
- **RabbitMQ** (message broker, for ingestion routes)
