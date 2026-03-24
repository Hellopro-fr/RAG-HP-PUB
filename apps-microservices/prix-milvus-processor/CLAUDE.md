# prix-milvus-processor

Inserts embedded price data into Milvus vector database, then publishes to webhook pipeline.

## Tech Stack

- Python 3.10 (synchronous -- uses `pika`, not `aio_pika`)
- RabbitMQ (pika) -- blocking consumer/publisher
- Milvus (pymilvus 2.5.4) -- vector DB insertion
- Prometheus metrics (prometheus-client, port 8010)
- Pydantic 2, pytest

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/prix-milvus-processor/Dockerfile .
  ```
- Entrypoint: `python -m app.main`
- Prometheus metrics exposed on port **8010**
- Shared libs: `libs/common-utils`
- No gRPC stubs needed

## Folder Structure

```
prix-milvus-processor/
  Dockerfile
  requirements.txt
  app/
    main.py                        # sync entrypoint (pika blocking)
    core/
      processor.py                 # insertion_data() -- Milvus insert logic
    messaging/
      consumer.py                  # listens on data.prix.ready_for_insertion
      publisher.py                 # publishes to data.ready_for_webhook
  tests/
    conftest.py
```

## Messaging

| Direction | Exchange                        | Routing Key                    | Queue                    |
|-----------|---------------------------------|--------------------------------|--------------------------|
| Consumes  | prix_embedded_data_exchange     | data.prix.ready_for_insertion  | insertion_prix_queue     |
| Publishes | inserted_data_exchange          | data.ready_for_webhook         | --                       |

- Retry: `prix_retry_exchange` / `insertion_prix_retry_queue` (TTL 30s)
- DLQ: `prix_dlq_exchange` / `insertion_prix_dlq_queue`
- Max retries: 3

## Dependencies on Other Services

- **Embedding service**: produces messages with embedded price vectors
- **Milvus**: target vector DB (collection `prix` via `MilvusPrixProduitsCrud`)
- **Webhook pipeline**: consumes `data.ready_for_webhook` downstream
- **RabbitMQ**, **common-utils** (CollectionName, MilvusPrixProduitsCrud)

## Conventions

- Synchronous pika (unlike other prix services which use aio_pika)
- Insert-only, no deduplication logic currently
- Each product's `source` field is auto-filled from `origin` if missing
