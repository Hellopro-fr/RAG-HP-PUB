# di-database-qdrant-service

Inserts devis (quotes/DI) embeddings into Qdrant/Milvus vector databases, keyed by lead_id.

## Tech Stack

- Python 3.10, pika, qdrant-client, pymilvus, pydantic, prometheus-client
- Shared lib: `libs/common-utils` (QdrantDevisCrud, MilvusDevisCrud, MilvusDevisInserer, DLQProperties)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t di-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics
  core/processor.py    # insertion_data() - dedup by lead_id
  messaging/
    consumer.py        # DLQ + retry (max 3, 30s TTL), reconnection logic
    publisher.py       # Standard publisher with reconnection
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `devis_embedded_data_exchange` | `data.devis.ready_for_insertion` | `insertion_devis_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |
| DLQ       | `dead_letter_exchange` | same | `insertion_devis_queue_dlq` |

## Conventions

- Key entity: `lead_id` (dedup: skip if already exists)
- Collection: `CollectionName.DEVIS`
- Supports Qdrant and Milvus; correspondance table on Milvus inserts

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
