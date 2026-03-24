# QC-enrichissement

QC pipeline step 5 -- enriches category data via LLM before equivalence matching.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-enrichissement/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-enrichissement/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      enrichissement_generator.py  # business logic (EnrichissementGenerator)
      api_client.py                # HelloPro API client
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step5.start
      publisher.py                 # publishes to qc.step6.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                       |
|-----------|-----------------------|------------------|-----------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step5.start   | qc_enrichissement_queue     |
| Publishes | qc_pipeline_exchange  | qc.step6.start   | --                          |

- Retry: `qc_retry_exchange` / `qc_enrichissement_queue_retry` (TTL 30s)
- DLQ: `qc_dead_letter_exchange` / `qc_enrichissement_queue_dlq`
- Max retries: 3

## Dependencies on Other Services

- **Upstream**: QC-generation-valeurs (step 4) publishes to `qc.step5.start`
- **Downstream**: QC-equivalence (step 6) consumes from `qc.step6.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
