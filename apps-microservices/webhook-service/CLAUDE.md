# webhook-service

RabbitMQ consumer that sends HMAC-signed webhook notifications to external back-office systems.

## Tech Stack

- Python 3.10
- RabbitMQ (pika, blocking connection)
- HTTP client (requests) for webhook delivery
- Shared libs: `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/webhook-service/Dockerfile .
  ```

## Folder Structure

```
webhook-service/
  app/
    main.py                  # Entrypoint, validates env, connects RabbitMQ
    core/processor.py        # Webhook signing (HMAC-SHA256) + delivery with retry
    messaging/consumer.py    # Listens on webhook_queue, ACK/NACK logic
  tests/
    conftest.py
    test_chunking.py
    test_embedding.py
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Exchange**: `inserted_data_exchange` (topic)
- **Queue**: `webhook_queue` (routing key: `data.ready_for_webhook`)
- Synchronous (pika BlockingConnection), no DLQ yet (TODO in code).

## Conventions

- Required env vars: `RABBITMQ_URL`, `KEY_WEBHOOK`.
- Payloads signed with HMAC-SHA256 using `KEY_WEBHOOK`, sent in `X-Webhook-Signature` header.
- Retry: 3 attempts with exponential backoff (1s, 2s, 4s).
- Webhook URL resolved per collection via `CollectionWebhook` mapping.

## Dependencies on Other Services

- **RabbitMQ**
- External back-office webhook endpoints
