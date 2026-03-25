# deepseek-metrics-collector-service

RabbitMQ consumer that collects LLM usage metrics and forwards them in adaptive batches via HTTP.

## Tech Stack

- Python 3.11, asyncio
- RabbitMQ (aio-pika) with retry/DLQ
- aiohttp for HTTP forwarding
- Shared libs: `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/deepseek-metrics-collector-service/Dockerfile .
  ```

## Folder Structure

```
deepseek-metrics-collector-service/
  app/main.py        # Entrypoint + MetricsConsumer class (all-in-one)
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Exchange**: `processed_data_exchange` (topic)
- **Queue**: `deepseek_metrics_queue` (routing key: `metrics.deepseek.result`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `deepseek_metrics_queue_dlq`
- Prefetch: `MAX_BATCH_SIZE * 2` (100)

## Conventions

- **Adaptive batching**: batch size adjusts between 5-50 based on success/failure.
  - On 5 consecutive successes: increase by 10% of max.
  - On HTTP 403 (WAF block): halve batch size immediately.
- Fixed 15s collection interval before each send.
- Required env vars: `RABBITMQ_URL`, `DEEPSEEK_METRICS_COLLECTOR_URL`.
- Forwards metrics as JSON array via HTTP POST to external collector endpoint.

## Dependencies on Other Services

- **RabbitMQ**
- **External metrics collector** (HTTP, `DEEPSEEK_METRICS_COLLECTOR_URL` env var)
