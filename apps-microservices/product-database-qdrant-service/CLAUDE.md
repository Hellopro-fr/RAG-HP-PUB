# product-database-qdrant-service

Inserts/updates product embeddings into Qdrant/Milvus with smart upsert logic (dedup, source tracking, similarity check).

## Tech Stack

- Python 3.10, pika, qdrant-client, pymilvus, pydantic, prometheus-client, difflib
- Shared lib: `libs/common-utils` (QdrantProduitsCrud, MilvusProduitsCrud, DLQProperties)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t product-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics server
  core/processor.py    # insertion_data() - upsert with source/similarity logic
  messaging/
    consumer.py        # DLQ + retry infrastructure (max 3 retries, 30s TTL)
    publisher.py       # Reconnection-resilient publisher
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `produits_embedded_data_exchange` | `data.produits.ready_for_insertion` | `insertion_produits_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |
| DLQ       | `dead_letter_exchange` | same | `insertion_produits_queue_dlq` |
| Retry     | `retry_exchange` | same | `insertion_produits_queue_retry` |

## Conventions

- Upsert logic: new product -> insert; same id + different source -> insert; same source + Milvus -> compare 5 critical fields then text similarity (threshold 0.85)
- Supports `mode=update` to force update without checks
- `origin` field tracks data source (BO, etc.)

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
