# embedding-service

RabbitMQ consumer that vectorizes incoming data via the embedding-model-service and publishes results.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio-pika) with retry/DLQ pattern
- gRPC client (to embedding-model-service)
- Prometheus metrics on port **8530**
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/embedding-service/Dockerfile .
  ```
- Tests: `pytest tests/` (test_chunking.py, test_embedding.py)

## Folder Structure

```
embedding-service/
  app/
    main.py                  # Entrypoint, connects to RabbitMQ (2 separate connections)
    core/processor.py        # embed_input_data() - calls Embedding utility
    messaging/
      consumer.py            # Listens on 'embedding_queue', retry/DLQ logic
      publisher.py           # Publishes embedded results
  tests/
    conftest.py
    test_chunking.py
    test_embedding.py
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Exchange**: `processed_data_exchange` (topic)
- **Queue**: `embedding_queue` (routing key: `data.ready_for_embedding`)
- **Retry**: `embedding_queue_retry` (30s TTL, max 3 retries)
- **DLQ**: `embedding_queue_dlq`
- Prefetch: 10, poison message shield (x-death > 10)

## Conventions

- Two separate AMQP connections (consume vs publish) to avoid frame interleaving.
- Permanent errors (ValueError, JSONDecodeError) go directly to DLQ.
- Transient errors are retried up to 3 times with 30s TTL.

## Dependencies on Other Services

- **embedding-model-service** (gRPC, via `common_utils.embedding.Embedding`)
- **RabbitMQ**
