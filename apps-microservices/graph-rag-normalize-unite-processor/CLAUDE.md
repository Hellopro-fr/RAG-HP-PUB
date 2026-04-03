# graph-rag-normalize-unite-processor
RabbitMQ consumer that normalizes product characteristic units — calls the normalization gRPC service and forwards results downstream.

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **gRPC client:** grpcio (calls normalize-unite-service)
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker port:** 8562 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                              # Entrypoint — starts consumer
  config.py                            # pydantic-settings (queues, gRPC, batching)
  core/processor.py                    # Normalization processing logic
  messaging/consumer.py                # RabbitMQ consumer
  messaging/publisher.py               # Publishes to output + retry DLQ exchanges
  infrastructure/normalization_client.py  # gRPC client
```

## Conventions
- Batching: `BATCH_SIZE=10`, `BATCH_TIMEOUT_SECONDS=2.0`
- Concurrency: `MAX_CONCURRENCY=10`
- Failed messages routed to retry DLQ (`graph_rag_normalization_retry`)

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_normalization_queue` (exchange: `graph_rag_normalization`, key: `graph_rag.normalization.pending`)
- **Output:** `graph_rag_semantic_check` (key: `graph_rag.semantic.check`)
- **Retry DLQ:** `graph_rag_normalization_retry`
- **gRPC:** normalize-unite-service (50057)
- **Upstream:** llm-extractor-processor
