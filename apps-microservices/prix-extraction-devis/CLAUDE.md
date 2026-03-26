# prix-extraction-devis

Extracts price data from PDF quotes (devis) via LLM for a given category, then publishes to embedding pipeline.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- httpx, requests, tenacity, Pydantic Settings

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/prix-extraction-devis/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
prix-extraction-devis/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      prix_extractor.py            # PrixExtractor -- main business logic
      api_client.py                # HelloPro API client
      credentials.py
      utils.py                     # process_product_data_for_embedding
    messaging/
      consumer.py                  # listens on new_data.prix_devis
      publisher.py                 # publishes to data.ready_for_embedding
    schemas/
      prix_extraction.py           # RequestProcessus
      produit_prix_payload.py
```

## Messaging

| Direction | Exchange                   | Routing Key               | Queue                          |
|-----------|---------------------------|---------------------------|--------------------------------|
| Consumes  | data_exchange_prix_devis   | new_data.prix_devis       | prix_devis_processing_queue    |
| Publishes | processed_data_exchange    | data.ready_for_embedding  | --                             |

- Uses `CollectionName.PRIX_DEVIS` from common-utils for naming
- Retry/DLQ: per-collection pattern (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **prix-traitement** or upstream dispatcher: publishes to `new_data.prix_devis`
- **Embedding pipeline**: consumes from `data.ready_for_embedding`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Each successful extraction item published individually to embedding
- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
