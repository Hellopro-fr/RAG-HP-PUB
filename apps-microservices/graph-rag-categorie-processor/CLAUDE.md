# graph-rag-categorie-processor
RabbitMQ consumer that ingests category data into the Neo4j graph database via the database-connector gRPC service.

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
- **Docker:** no explicit EXPOSE (Prometheus on port 8570)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                          # Entrypoint
  config.py                        # pydantic-settings
  core/processor.py                # Category processing logic
  messaging/consumer.py            # RabbitMQ consumer
  infrastructure/database_client.py  # gRPC client
```

## Conventions
- Concurrency: `MAX_CONCURRENCY=5`
- No batching configuration (simpler processor)

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_categorie_queue` (exchange: `graph-data_graph_exchange_categories`, key: `graph-new_data.categories`)
- **gRPC:** database-connector (50055)
