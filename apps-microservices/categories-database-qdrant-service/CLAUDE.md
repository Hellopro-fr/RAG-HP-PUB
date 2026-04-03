# categories-database-qdrant-service

Inserts category embeddings into Qdrant/Milvus vector databases from RabbitMQ messages.

## Tech Stack

- Python 3.10, pika (RabbitMQ), qdrant-client, pymilvus, pydantic, pytest
- Shared lib: `libs/common-utils` (QdrantCategoriesCrud, MilvusCategoriesCrud)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t categories-database-qdrant-service .` (from repo root)
- **Run**: Deployed via Docker; requires `RABBITMQ_URL` env var
- **Tests**: `pytest tests/` (test_chunking.py, test_embedding.py)

## Folder Structure

```
app/
  main.py              # Entry point, RabbitMQ connection loop
  core/processor.py    # insertion_data() - upsert logic with dedup by id_categorie
  messaging/
    consumer.py        # Listens on 'insertion_categories_queue'
    publisher.py       # Publishes to 'inserted_data_exchange'
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `categories_embedded_data_exchange` | `data.categories.ready_for_insertion` | `insertion_categories_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |

## Conventions

- Processor checks if `id_categorie` exists before insert (dedup)
- Supports both Qdrant and Milvus via `database` field in message payload
- Milvus inserts also write to correspondance table (`MilvusCategoriesInserer`)

## Dependencies on Other Services

- **Upstream**: embedding-service (produces embedded data)
- **Downstream**: webhook-service (consumes insertion results)
- **Infrastructure**: RabbitMQ, Qdrant, Milvus/Zilliz
