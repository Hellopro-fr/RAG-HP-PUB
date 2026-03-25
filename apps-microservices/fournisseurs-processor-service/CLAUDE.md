# fournisseurs-processor-service

Cleans and prepares supplier (fournisseur) data (HTML stripping) for the embedding pipeline.

## Tech Stack

- Python 3.10, pika, beautifulsoup4, markdownify, html5lib
- Shared lib: `libs/common-utils` (CleanHTML, CollectionName)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t fournisseurs-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var

## Folder Structure

```
app/
  main.py              # Entry point, RabbitMQ connection loop
  core/processor.py    # process_fournisseurs_data_for_embedding() - HTML cleanup
  messaging/
    consumer.py        # Simple consumer (no DLQ/retry)
    publisher.py       # Publishes to 'processed_data_exchange'
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_fournisseurs` | `new_data.fournisseurs` | `fournisseurs_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_embedding` | - |

## Conventions

- Cleans HTML from `text` field using `CleanHTML`
- Preserves all metadata fields; cleaned text replaces original
- No DLQ/retry (simple consumer, same pattern as categories-processor)

## Dependencies on Other Services

- **Upstream**: api-ingestion
- **Downstream**: embedding-service
- **Infrastructure**: RabbitMQ
