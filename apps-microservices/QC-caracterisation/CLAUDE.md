# QC-caracterisation

QC pipeline step 7 (final) -- generates product characterizations via LLM for a given category.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- Pydantic Settings, tenacity (retry), requests

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/QC-caracterisation/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs installed at build: `libs/common-utils`, `libs/grpc-stubs`
- Protos compiled at build from `protos/`

## Folder Structure

```
QC-caracterisation/
  main.py                          # asyncio entrypoint
  Dockerfile
  requirements.txt
  app/
    core/
      caracterisation_produit.py   # business logic (CaracterisationProduitGenerator)
      api_client.py                # HelloPro API client
      credentials.py               # pydantic-settings config
      ConnexionManager.py
      utils.py
    messaging/
      consumer.py                  # listens on qc.step7.start
      publisher.py                 # publishes to qc.complete
    schemas/
      question_caracteristique.py  # RequestProcessus model
```

## Messaging

| Direction | Exchange              | Routing Key      | Queue                       |
|-----------|-----------------------|------------------|-----------------------------|
| Consumes  | qc_pipeline_exchange  | qc.step7.start   | qc_caracterisation_queue    |
| Publishes | qc_pipeline_exchange  | qc.complete      | --                          |

- Retry: `qc_retry_exchange` / `qc_caracterisation_queue_retry` (TTL 30s)
- DLQ: `qc_dead_letter_exchange` / `qc_caracterisation_queue_dlq`
- Max retries: 3, concurrency controlled via `settings.MAX_CONCURRENCY`

## Dependencies on Other Services

- **Upstream**: QC-equivalence (step 6) publishes to `qc.step7.start`
- **HelloPro API**: REST calls via `HelloProAPIClient`
- **RabbitMQ**: required infrastructure
- **common-utils**: DLQPropertiesAsync, shared utilities

## Conventions

- Category-level deduplication via in-memory lock (per-replica only)
- Tracking files generated per run for observability
