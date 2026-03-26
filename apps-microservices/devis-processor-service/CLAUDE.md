# devis-processor-service

RabbitMQ consumer that transforms incoming devis (quote) data for embedding.

## Tech Stack

- Python 3.10
- RabbitMQ (pika, blocking connection) with retry/DLQ
- Prometheus metrics on port **8530**
- Shared libs: `common-utils`

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/devis-processor-service/Dockerfile .
  ```

## Folder Structure

```
devis-processor-service/
  app/
    main.py                  # Entrypoint, connects RabbitMQ + Prometheus
    core/processor.py        # Data transformation (date->timestamp, int conversion, etc.)
    messaging/
      consumer.py            # Listens on devis_processing_queue, retry/DLQ logic
      publisher.py           # Publishes to embedding pipeline
  requirements.txt
  Dockerfile
```

## RabbitMQ Topology

- **Exchange**: `data_exchange_devis` (topic)
- **Queue**: `devis_processing_queue` (routing key: `new_data.devis`)
- **Retry**: 30s TTL, max 3 retries
- **DLQ**: `devis_processing_queue_dlq`

## Conventions

- Transforms devis fields: hyphen-to-underscore keys, `lead_id`/`id_produit`/`id_categorie` to int.
- Parses `liste_frns` CSV string into array.
- Converts `date_du_lead` ISO string to Unix timestamp.
- Output collection: `devis` (target database configurable, default: `qdrant`).

## Dependencies on Other Services

- **RabbitMQ**
- Downstream: **embedding-service** (via published messages)
