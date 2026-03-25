# echange-database-qdrant-service

Inserts/updates conversation exchange embeddings into Qdrant/Milvus with update support for existing conversations.

## Tech Stack

- Python 3.10, pika, qdrant-client, pymilvus, pydantic, prometheus-client
- Shared lib: `libs/common-utils` (QdrantEchangeCrud, MilvusEchangeCrud, DLQProperties)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t echange-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics
  core/processor.py    # insertion_data() - insert or update by conversation_id
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
| Consumes  | `echanges_embedded_data_exchange` | `data.echanges.ready_for_insertion` | `insertion_echanges_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |
| DLQ       | `dead_letter_exchange` | same | `insertion_echanges_queue_dlq` |

## Conventions

- Key entity: `conversation_id`
- If conversation exists in Milvus: calls `update_echange()` (unlike categories/fournisseurs which skip)
- Qdrant: skips if exists; Milvus: updates if exists
- Writes correspondance table on new inserts

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
