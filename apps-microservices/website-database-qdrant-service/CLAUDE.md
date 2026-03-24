# website-database-qdrant-service

Upserts website page embeddings into Qdrant/Milvus with delete-before-insert strategy for content freshness.

## Tech Stack

- Python 3.10, pika, qdrant-client, pymilvus, pydantic, prometheus-client
- Shared lib: `libs/common-utils` (QdrantWebsiteCrud, MilvusWebsiteCrud, DLQProperties)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t website-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics
  core/processor.py    # insertion_data() - upsert: delete old chunks then insert new
  messaging/
    consumer.py        # DLQ + retry (max 3, 30s TTL), reconnection logic
    publisher.py       # Standard publisher
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `siteweb_embedded_data_exchange` | `data.siteweb.ready_for_insertion` | `insertion_siteweb_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |
| DLQ       | `dead_letter_exchange` | same | `insertion_siteweb_queue_dlq` |

## Conventions

- Upsert = delete old + insert new (not in-place update)
- Standard pages: delete by URL; headers/footers: delete by domaine + page_type
- Validates required fields: url, page_type, domaine

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
