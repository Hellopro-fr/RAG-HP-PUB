# api-ingestion

Ingestion API that receives data payloads and publishes them to RabbitMQ exchanges for async processing by downstream consumers.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Messaging:** RabbitMQ (pika, topic exchanges)
- **Metrics:** Prometheus (`/metrics` via WSGI mount)
- **Shared lib:** `common_utils` (RabbitMQ connection, Prometheus helpers)

## Build / Run

- **Port:** 8509
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8509`
- **Tests:** `pytest tests/`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-ingestion/
  main.py                           # FastAPI app, RabbitMQ startup/shutdown
  app/
    core/
      credentials.py                # Settings (RABBITMQ_URL, etc.)
      ingestion/ingestion.py        # routing_key_collection mapping
    messaging/publisher.py          # publish_message helper
    router/ingestion/
      ingestion.py                  # /publier, /publier-lot (standard)
      ingestion_QC.py               # /publier QC pipeline (7 steps)
      ingestion_graph.py            # /publier graph-RAG variant
    schemas/ingestion/
      ingestion.py                  # BaseIngestion, response models
      ingestion_qc.py               # QC-specific schemas
    utils/
  tests/
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ingestion/publier` | Publish single message to RabbitMQ |
| `POST` | `/ingestion/publier-lot` | Publish batch messages |
| `POST` | `/ingestion-qc/publier` | Publish to QC pipeline exchanges |
| `POST` | `/ingestion-graph/publier` | Publish to graph-RAG exchanges |
| `GET` | `/` | Health check |

## Conventions

- Exchange naming: `data_exchange_{collection}`.
- Routing keys derived from collection name via `routing_key_collection()`.
- RabbitMQ connection retries up to 10 times on startup.

## Dependencies on Other Services

- **RabbitMQ** (message broker, topic exchanges)
