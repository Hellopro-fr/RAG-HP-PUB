# graph-rag-fournisseur-processor
RabbitMQ consumer that ingests supplier (fournisseur) data into the Neo4j graph database via the database-connector gRPC service.

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
- **Docker port:** 8572 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                                # Entrypoint (robust RabbitMQ reconnection)
  config.py                              # pydantic-settings (queues, batching, concurrency)
  core/processor.py                      # Supplier processing logic
  messaging/consumer.py                  # RabbitMQ consumer
  infrastructure/graph_database_client.py  # gRPC client
```

## Conventions
- Robust RabbitMQ connection with 10-retry loop on startup
- Batching: `BATCH_SIZE=10`, `BATCH_TIMEOUT_SECONDS=2.0`
- Concurrency: `MAX_CONCURRENCY=3`

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_fournisseur_processing_queue` (exchange: `graph-data_graph_exchange_fournisseurs`, key: `graph-new_data.fournisseurs`)
- **gRPC:** database-connector (50055)
