# echange-processor-service

Prepares exchange/conversation data for the embedding pipeline with DLQ support.

## Tech Stack

- Python 3.10, pika, prometheus-client
- Shared lib: `libs/common-utils` (CollectionName, DLQProperties, RabbitMQConnection)
- Docker base: `python:3.10-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t echange-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var. Prometheus metrics on port 8530

## Folder Structure

```
app/
  main.py              # Entry point + Prometheus metrics
  core/processor.py    # process_echange_data_for_embedding() - builds conversation_id
  messaging/
    consumer.py        # DLQ + retry (max 3, 30s TTL)
    publisher.py       # Reconnection-resilient publisher
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_echanges` | `new_data.echange` | `echange_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_embedding` | - |
| DLQ       | `dead_letter_exchange` | same | `echange_processing_queue_dlq` |

## Conventions

- Generates `conversation_id` from `{id_demande}_{id_fournisseur}`
- No HTML cleaning (raw text pass-through)
- Replaces hyphens with underscores in field names

## Dependencies on Other Services

- **Upstream**: api-ingestion
- **Downstream**: embedding-service
- **Infrastructure**: RabbitMQ
