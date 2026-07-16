# template-llm-service

RabbitMQ consumer that classifies web pages and OCR documents by type using LLM (DeepSeek-R1).

## Tech Stack

- Python 3.11, asyncio
- RabbitMQ (aio-pika) with batch processing, retry/DLQ
- gRPC client (to llm-service)
- transformers AutoTokenizer (for token counting/truncation)
- Prometheus metrics on port **8530**
- Shared libs: `grpc-stubs`, `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/template-llm-service/Dockerfile .
  ```
- Tests: `pytest tests/` (test_messaging.py, test_qualifier.py)

## Folder Structure

```
template-llm-service/
  app/
    main.py                  # Entrypoint, connects to RabbitMQ
    core/processor.py        # Page classification logic, prompt templates
    messaging/
      consumer.py            # Batch consumer (BATCH_SIZE=16, TIMEOUT=2s)
      publisher.py           # Publishes classified results + metrics
  tests/
  start.sh
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Queue**: `llm_templating_queue` (routing key: `data.ready_for_templating`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `llm_templating_queue_dlq`
- Messages grouped by collection type before batch processing.

## Conventions

- Classifies into predefined page types: `home`, `fiche_produit`, `catalogue`, `devis`, etc.
- Prompts truncated at 127,488 tokens (DeepSeek-R1 128K context - 512 safety margin).
- Batch processor collects up to 16 messages or waits 2s, then sends concurrent LLM calls.

## Dependencies on Other Services

- **llm-service** (gRPC, via `common_utils.grpc_clients.llm_client`)
- **RabbitMQ**
