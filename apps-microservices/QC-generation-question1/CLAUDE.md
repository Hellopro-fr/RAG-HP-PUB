# QC-generation-question1

QC pipeline step 1 (entry point) -- generates the first question (Q1) for a category via LLM.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-generation-question1/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-generation-question1/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      question1_generator.py       # Question1Generator
      api_client.py
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step1.start
      publisher.py                 # publishes to qc.step2.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                  |
|-----------|-----------------------|------------------|------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step1.start   | qc_question1_queue     |
| Publishes | qc_pipeline_exchange  | qc.step2.start   | --                     |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream**: External trigger publishes to `qc.step1.start`
- **Downstream**: QC-generation-question2aN (step 2) consumes from `qc.step2.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
