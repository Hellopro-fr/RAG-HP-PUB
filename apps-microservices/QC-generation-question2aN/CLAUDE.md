# QC-generation-question2aN

QC pipeline step 2 -- generates follow-up questions (Q2 to QN) for a category via LLM.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-generation-question2aN/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-generation-question2aN/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      question2aN_generator.py     # Question2aNGenerator
      api_client.py
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step2.start
      publisher.py                 # publishes to qc.step3.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                    |
|-----------|-----------------------|------------------|--------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step2.start   | qc_question2aN_queue     |
| Publishes | qc_pipeline_exchange  | qc.step3.start   | --                       |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream**: QC-generation-question1 (step 1) publishes to `qc.step2.start`
- **Downstream**: QC-generation-caracteristiques (step 3) consumes from `qc.step3.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
