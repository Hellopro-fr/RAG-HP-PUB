# graph-rag-normalize-unite-retry-processor
RabbitMQ consumer that retries failed normalization tasks — re-processes messages from the normalization retry DLQ with semantic deduplication.

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **gRPC client:** grpcio (calls normalization, milvus, database-connector)
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker port:** 8564 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                              # Entrypoint
  config.py                            # pydantic-settings (queues, gRPC, similarity threshold)
  core/processor.py                    # Retry processing logic
  messaging/consumer.py                # RabbitMQ consumer
  infrastructure/
    clients.py                         # Service clients
    database_client.py                 # gRPC database client
    normalization_client.py            # gRPC normalization client
```

## Conventions
- Permanently failed messages (after `MAX_RETRIES=3`) go to manual DLQ
- Semantic similarity check: `SIMILARITY_THRESHOLD=0.90`
- Batching: `BATCH_SIZE=10`, `MAX_CONCURRENCY=10`

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_normalization_retry_queue` (exchange: `graph_rag_normalization_retry`)
- **Manual DLQ:** `graph_rag_normalization_manual_dlq`
- **gRPC:** normalization-service (50057), milvus-service (50056), database-connector (50055)
- **HTTP:** Embedding API (configurable)
