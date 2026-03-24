# graph-rag-etl-processor
RabbitMQ consumer that performs final ETL — writes fully processed data into the graph database after all pipeline stages complete.

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **gRPC client:** grpcio (calls database-connector)
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
  main.py                    # Entrypoint — connects to RabbitMQ, starts consuming
  config.py                  # pydantic-settings (queues, gRPC URLs, batching)
  core/processor.py          # ETL processing logic
  messaging/consumer.py      # RabbitMQ consumer
  infrastructure/database_client.py  # gRPC client to database-connector
```

## Conventions
- Async consumer with robust RabbitMQ reconnection (10 retries)
- Batching: configurable `BATCH_SIZE` (default 5) and `BATCH_TIMEOUT_SECONDS` (2s)
- Concurrency: `MAX_CONCURRENCY` parallel batch workers (default 3)

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input queue:** `graph_rag_etl_queue` (exchange: `graph_rag_final_etl`, key: `graph_rag.etl.ready`)
- **gRPC:** database-connector (50055)
- **Upstream:** semantique-vigil-processor publishes to this exchange
