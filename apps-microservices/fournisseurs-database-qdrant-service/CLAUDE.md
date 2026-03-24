# fournisseurs-database-qdrant-service

Inserts supplier (fournisseur) embeddings into Qdrant/Milvus vector databases from RabbitMQ messages.

## Tech Stack

- Python 3.10, pika, qdrant-client, pymilvus, pydantic, pytest
- Shared lib: `libs/common-utils` (QdrantFournisseursCrud, MilvusFournisseursCrud)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t fournisseurs-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Entry point, RabbitMQ connection loop
  core/processor.py    # insertion_data() - dedup by id_fournisseur
  messaging/
    consumer.py        # Simple consumer (no DLQ/retry infrastructure)
    publisher.py       # Publishes to inserted_data_exchange
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `fournisseurs_embedded_data_exchange` | `data.fournisseurs.ready_for_insertion` | `insertion_fournisseurs_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |

## Conventions

- Dedup by `id_fournisseur`: skips insert if already exists
- Supports Qdrant and Milvus via `database` field
- Milvus inserts also write to correspondance table (`MilvusFournisseursInserer`)
- No DLQ/retry (simpler error handling than product/website services)

## Dependencies on Other Services

- **Upstream**: embedding-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
