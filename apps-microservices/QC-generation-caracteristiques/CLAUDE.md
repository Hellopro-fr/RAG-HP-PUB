# QC-generation-caracteristiques

QC pipeline step 3 -- generates the list of characteristics for a category via LLM.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-generation-caracteristiques/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-generation-caracteristiques/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      list_caracteristiques_generator.py  # ListCaracteristiquesGenerator
      api_client.py
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                         # listens on qc.step3.start
      publisher.py                        # publishes to qc.step4.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                         |
|-----------|-----------------------|------------------|-------------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step3.start   | qc_caracteristiques_queue     |
| Publishes | qc_pipeline_exchange  | qc.step4.start   | --                            |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream**: QC-generation-question2aN (step 2) publishes to `qc.step3.start`
- **Downstream**: QC-generation-valeurs (step 4) consumes from `qc.step4.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
