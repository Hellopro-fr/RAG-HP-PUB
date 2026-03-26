# graph-rag-produit-processor
RabbitMQ consumer that ingests product data into the graph database and publishes extracted products downstream for LLM extraction.

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
- **Docker port:** 8560 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                                # Entrypoint
  config.py                              # pydantic-settings (queues, batching, concurrency)
  core/processor.py                      # Product processing logic
  domain/models.py                       # Product domain models
  messaging/consumer.py                  # RabbitMQ consumer
  messaging/publisher.py                 # Publishes to output exchange
  infrastructure/graph_database_client.py  # gRPC client
```

## Conventions
- Batching: `BATCH_SIZE=10`, `BATCH_TIMEOUT_SECONDS=2.0`
- High concurrency: `MAX_CONCURRENCY=30`
- Publishes extracted product data downstream

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_product_processing_queue` (exchange: `graph-data_graph_exchange_produits`, key: `graph-new_data.product`)
- **Output:** `graph_rag_product_extracted` (key: `graph_rag.product.extracted`)
- **gRPC:** database-connector (50055)
- **Downstream:** llm-extractor-processor
