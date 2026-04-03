# prix-extraction-message

Extracts price data from messages/exchanges via LLM for a given category, then publishes to embedding pipeline.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- httpx, requests, tenacity, Pydantic Settings

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/prix-extraction-message/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`

## Folder Structure

```
prix-extraction-message/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      prix_extractor.py            # PrixExtractor
      api_client.py
      credentials.py
      utils.py                     # process_product_data_for_embedding
    messaging/
      consumer.py                  # listens on new_data.prix_message
      publisher.py                 # publishes to data.ready_for_embedding
    schemas/
      prix_extraction.py
      produit_prix_payload.py
```

## Messaging

| Direction | Exchange                     | Routing Key               | Queue                            |
|-----------|------------------------------|---------------------------|----------------------------------|
| Consumes  | data_exchange_prix_message   | new_data.prix_message     | prix_message_processing_queue    |
| Publishes | processed_data_exchange      | data.ready_for_embedding  | --                               |

- Uses `CollectionName.PRIX_MESSAGE` from common-utils
- Retry/DLQ: per-collection pattern (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream dispatcher**: publishes to `new_data.prix_message`
- **Embedding pipeline**: consumes from `data.ready_for_embedding`
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Each successful extraction item published individually to embedding
- Category-level deduplication (in-memory, per-replica)
- Tracking files for observability
