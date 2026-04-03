# database-service

Legacy service that inserts product embeddings into Milvus (predecessor of product-database-qdrant-service).

## Tech Stack

- Python 3.10, pika, pymilvus, pydantic, pytest
- Shared lib: `libs/common-utils` (MilvusCrud)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t database-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point, RabbitMQ connection loop
  core/processor.py    # insertion_data() - simple per-chunk insertion via MilvusCrud
  messaging/
    consumer.py        # Simple consumer (no DLQ/retry)
    publisher.py       # Publishes to 'inserted_data_exchange'
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `embedded_data_exchange` | `data.ready_for_insertion` | `insertion_product_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |

## Conventions

- Milvus-only (no Qdrant support)
- Inserts products chunk by chunk (no batch, no dedup)
- Only handles `CollectionName.PRODUIT` (other collections commented out)
- Simpler than product-database-qdrant-service: no source tracking, no similarity check, no DLQ

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Milvus
