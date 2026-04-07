---
name: rabbitmq-consumer-scaffold
description: Scaffold a new RabbitMQ processor service with consumer, publisher, DLQ setup, and Prometheus metrics
argument-hint: <service-name> <collection-name>
---

# Scaffold a New RabbitMQ Processor Service

Create a new processor service named `$0` consuming from collection `$1`.

## Steps

### 1. Create the service directory structure

```
apps-microservices/$0/
  main.py
  Dockerfile
  requirements.txt
  CLAUDE.md
  app/
    __init__.py
    core/
      __init__.py
      config.py            # Pydantic BaseSettings (RABBITMQ_URL, etc.)
      processor.py         # Business logic
    messaging/
      __init__.py
      consumer.py          # RabbitMQ consumer with DLQ
      publisher.py         # RabbitMQ publisher for downstream events
  tests/
    __init__.py
    conftest.py
    test_processor.py
    test_consumer.py
```

### 2. Follow project conventions

- **main.py**: RabbitMQ connection with retry logic (10 attempts, exponential backoff), consumer startup, graceful shutdown.
- **consumer.py**: Use `aio_pika` (async) as preferred pattern.
  - Exchange: `data_exchange_$1`
  - Queue: `$1_processing_queue`
  - Routing key: `new_data.$1`
  - ACK messages AFTER processing (not before).
  - Transient errors (network, timeout): NACK + requeue.
  - Permanent errors (validation, malformed): NACK + route to DLQ via `common_utils.autres.DLQPropertiesAsync`.
- **publisher.py**: Publish downstream events with delivery confirmation.
- **config.py**: Pydantic `BaseSettings` — `RABBITMQ_URL`, `SERVICE_NAME`, `LOG_LEVEL`.
- **Metrics**: `common_utils.metrics.prometheus` on port 8530, use `@measure_processing_time` decorator.
- **Logging**: `setup_logging("$0")` from `common_utils.logging`.

### 3. Read existing processor for reference

Before generating, read one existing processor service (e.g., `website-processor-service` or `product-processor-service`) to match exact patterns.

### 4. Generate CLAUDE.md

Use `/new-service-claude-md` conventions. Include:
- Exchange/queue/routing key names.
- What triggers this processor (upstream service).
- What it publishes downstream.

### 5. Generate basic tests

- `conftest.py`: Mock RabbitMQ connection, mock env vars.
- `test_processor.py`: Test business logic with sample payloads.
- `test_consumer.py`: Test message handling (success, transient error, permanent error → DLQ).

### 6. Update root files

- Add to root `CLAUDE.md` Service Map.
- Add `@apps-microservices/$0/CLAUDE.md` to Per-Service Instructions.

## Rules

- Apply `.claude/rules/security.md` (connection strings from env vars).
- Apply `.claude/rules/docker-security.md`.
- Apply `.claude/rules/impact-awareness.md` — check if `$1` collection already exists in other services.
- Prefetch count MUST be set (not unlimited).
- Consumer MUST handle graceful shutdown (close channel before connection).
