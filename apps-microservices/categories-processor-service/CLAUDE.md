# categories-processor-service

Cleans and prepares category data (HTML stripping) for the embedding pipeline.

## Tech Stack

- Python 3.10, pika, beautifulsoup4, markdownify, html5lib
- Shared lib: `libs/common-utils` (CleanHTML, CollectionName)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t categories-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var

## Folder Structure

```
app/
  main.py              # Entry point, RabbitMQ connection loop
  core/processor.py    # process_categories_data_for_embedding() - HTML cleanup
  messaging/
    consumer.py        # Listens on 'categories_processing_queue'
    publisher.py       # Publishes to 'processed_data_exchange'
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_categories` | `new_data.category` | `categories_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_embedding` | - |

## Conventions

- Cleans HTML from `text` field using `CleanHTML`
- Preserves all metadata fields except `text` (which is replaced with cleaned version)
- No DLQ/retry infrastructure (simple consumer)
- Passes `database` field through to downstream

## Dependencies on Other Services

- **Upstream**: api-ingestion (produces raw category data)
- **Downstream**: embedding-service (consumes cleaned data for vectorization)
- **Infrastructure**: RabbitMQ
