# document-database-qdrant-service

Inserts document/PJ embeddings into Milvus asynchronously with high-concurrency message processing.

## Tech Stack

- Python 3.11, aio_pika (async RabbitMQ), pymilvus, pydantic
- Shared lib: `libs/common-utils` (MilvusDocumentCrud, MilvusPjCrud, DLQProperties)
- Docker base: `python:3.11-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t document-database-qdrant-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var
- **Tests**: `pytest tests/`

## Folder Structure

```
app/
  main.py              # Async entry point with reconnection loop
  core/processor.py    # insertion_data() - handles documents and PJs (page_type logic)
  messaging/
    consumer.py        # Async consumer, prefetch=100, semaphore=100, DLQ/retry
    publisher.py       # Async publisher
tests/
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `document_embedded_data_exchange` | `data.document.ready_for_insertion` | `insertion_document_queue` |
| Publishes | `inserted_data_exchange` | `data.ready_for_webhook` | - |
| DLQ       | `dead_letter_exchange` | same | `insertion_document_queue_dlq` |
| Retry     | `retry_exchange` | same | `insertion_document_queue_retry` |

## Conventions

- Fully async (aio_pika), unlike most other database services
- Handles two entity types: documents (`page_type=autre` -> update/insert) and PJs (dedup by `fichier_source`)
- Milvus-only (no Qdrant support in practice)
- Dedicated persistent AMQP channel for publishing (avoids channel-per-message exhaustion)
- DLQ error messages use `repr(e)` for full exception context (via shared DLQProperties)
- `_send_to_dlq()` wrapped in try/except to prevent silent message loss
- `_ensure_connected()` uses real RPC health check (`utility.list_collections`) instead of `has_connection()`
- Milvus expression injection prevented: `fichier_source` sanitized, `id` type-validated
- Docker: non-root user, `--no-cache-dir`, `.dockerignore`

## Dependencies on Other Services

- **Upstream**: embedding-service / document-echange-processor-service
- **Downstream**: webhook-service
- **Infrastructure**: RabbitMQ, Milvus/Zilliz
