# nettoyage-bruit-ocr-service

RabbitMQ consumer that cleans OCR-extracted text using LLM to remove legal/marketing noise.

## Tech Stack

- Python 3.11, asyncio
- RabbitMQ (aio-pika) with retry/DLQ
- gRPC client (to llm-service) with thinking mode enabled
- httpx
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/nettoyage-bruit-ocr-service/Dockerfile .
  ```

## Folder Structure

```
nettoyage-bruit-ocr-service/
  app/
    main.py                  # Entrypoint, connects to RabbitMQ
    core/processor.py        # LLM-based text cleaning logic
    messaging/
      consumer.py            # Single-message consumer with keep-alive
      publisher.py           # Publishes cleaned text + metrics
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Queue**: `nettoyage_bruit_ocr_queue` (routing key: `data.ready_for_ocr_cleaning`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `nettoyage_bruit_ocr_queue_dlq`
- Prefetch: 1 (sequential processing)

## Conventions

- Removes 5 categories: legal mentions, contractual clauses, disclaimers, regulatory notes, marketing slogans.
- Non-French content returns empty string (filtered out).
- Uses `enable_thinking=True` for LLM calls (max 64K output tokens).
- ACK-after strategy: messages acknowledged AFTER successful processing or DLQ routing (at-least-once delivery).
- Channel keep-alive task runs every 30s to prevent timeout on long LLM calls.
- DLQ sends the correct individual message body (not hardcoded `batch_bodies[0]`).
- Reconnection loop restored in `main.py` (was commented out).
- Docker: non-root user, `--no-cache-dir`, `.dockerignore`.

## Dependencies on Other Services

- **llm-service** (gRPC, via `common_utils.grpc_clients.llm_client`)
- **RabbitMQ**
