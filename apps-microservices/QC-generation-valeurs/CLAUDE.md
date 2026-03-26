# QC-generation-valeurs

QC pipeline step 4 -- generates characteristic values/info for a category via LLM.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-generation-valeurs/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-generation-valeurs/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      info_caracteristiques_generator.py  # InfoCaracteristiquesGenerator
      api_client.py
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                         # listens on qc.step4.start
      publisher.py                        # publishes to qc.step5.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                |
|-----------|-----------------------|------------------|----------------------|
| Consumes  | qc_pipeline_exchange  | qc.step4.start   | qc_valeurs_queue     |
| Publishes | qc_pipeline_exchange  | qc.step5.start   | --                   |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream**: QC-generation-caracteristiques (step 3) publishes to `qc.step4.start`
- **Downstream**: QC-enrichissement (step 5) consumes from `qc.step5.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
