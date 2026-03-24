# product-processor-service

Cleans and prepares product data (HTML stripping) for the embedding pipeline with DLQ support.

## Tech Stack

- Python 3.10, pika, beautifulsoup4, markdownify, html5lib, prometheus-client
- Shared lib: `libs/common-utils` (CleanHTML, CollectionName, DLQProperties, RabbitMQConnection)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t product-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics
  core/processor.py    # process_product_data_for_embedding() - HTML cleanup
  messaging/
    consumer.py        # DLQ + retry (max 3, 30s TTL), reconnection logic
    publisher.py       # Reconnection-resilient publisher
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_produits` | `new_data.product` | `product_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_embedding` | - |
| DLQ       | `dead_letter_exchange` | same | `product_processing_queue_dlq` |

## Conventions

- Cleans HTML from `text` field using `CleanHTML`
- Tracks `origin` field (bo, etc.) through the pipeline
- Full DLQ/retry infrastructure with Prometheus metrics

## Dependencies on Other Services

- **Upstream**: api-ingestion (produces raw product data)
- **Downstream**: embedding-service
- **Infrastructure**: RabbitMQ
