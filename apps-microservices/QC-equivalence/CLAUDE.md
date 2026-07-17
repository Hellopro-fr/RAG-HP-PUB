# QC-equivalence

QC pipeline step 6 -- generates equivalences between product characteristics via LLM.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity, requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-equivalence/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
QC-equivalence/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      equivalence_generator.py     # business logic (EquivalenceGenerator)
      api_client.py                # HelloPro API client
      credentials.py
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step6.start
      publisher.py                 # publishes to qc.step7.start
    schemas/
      question_caracteristique.py
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                     |
|-----------|-----------------------|------------------|---------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step6.start   | qc_equivalence_queue      |
| Publishes | qc_pipeline_exchange  | qc.step7.start   | --                        |

- Retry/DLQ: same pattern as other QC services (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream**: QC-enrichissement (step 5) publishes to `qc.step6.start`
- **Downstream**: QC-caracterisation (step 7) consumes from `qc.step7.start`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Category deduplication per-replica only; cross-replica dedup handled by backend `can_start`
- Tracking files for observability
