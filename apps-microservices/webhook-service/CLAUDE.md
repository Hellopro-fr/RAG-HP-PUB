# webhook-service

Async RabbitMQ consumer that sends HMAC-signed webhook notifications to external back-office systems, with batching support for high-throughput update scenarios.

## Tech Stack

- Python 3.10
- RabbitMQ (aio_pika, async robust connection)
- HTTP client (aiohttp, persistent session with connection pooling)
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
    main.py                  # Async entrypoint, validates env, connects RabbitMQ
    core/processor.py        # WebhookSender class: HMAC signing, aiohttp session, batch + single delivery
    messaging/consumer.py    # Async consumer with message buffer, batch flush by size/timeout
  tests/
    conftest.py
    test_consumer.py         # Tests: filtering, batch payload, URL resolution, HMAC signature
    test_chunking.py
    test_embedding.py
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Exchange**: `inserted_data_exchange` (topic)
- **Queue**: `webhook_queue` (routing key: `data.ready_for_webhook`)
- Async (aio_pika RobustConnection), with prefetch_count = BATCH_SIZE * 2.
- Only `mode=update` messages are processed; all others are ACK'd silently.

## Batching

Messages are accumulated in a buffer and flushed as a single HTTP POST when:
- Buffer reaches `BATCH_SIZE` (default: 50), or
- `BATCH_TIMEOUT_S` seconds elapse since first buffered message (default: 5.0s)

Batch payload format sent to the PHP webhook:
```json
{
  "batch": true,
  "mode": "update",
  "collection": "produits",
  "count": 50,
  "products": [
    {"id_produit": "12345", "chunk_ids": "pk1,pk2", "origin": "siteweb", "update_reason": "..."},
    ...
  ]
}
```

The PHP endpoint uses a single SQL `UPDATE ... CASE/WHEN` for all products in the batch.

## Conventions

- Required env vars: `RABBITMQ_URL`, `KEY_WEBHOOK`.
- Optional env vars: `WEBHOOK_BATCH_SIZE` (default: 50), `WEBHOOK_BATCH_TIMEOUT_S` (default: 5.0).
- Payloads signed with HMAC-SHA256 using `KEY_WEBHOOK`, sent in `X-Webhook-Signature` header.
- Retry: 3 attempts with exponential backoff (1s, 2s, 4s).
- Webhook URL resolved per collection via `CollectionWebhook` mapping; `mode=update` uses `CollectionWebhookUpdate` (env var `WEBHOOK_UPDATE_PRODUIT_URL`).
- Connection pooling: aiohttp TCPConnector (limit=20, keepalive=30s).

## Dependencies on Other Services

- **RabbitMQ**
- External back-office webhook endpoints (PHP)
