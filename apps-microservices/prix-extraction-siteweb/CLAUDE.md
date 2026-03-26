# prix-extraction-siteweb

Extracts price data from website content via LLM + Milvus search for a given category, then publishes to embedding pipeline.

## Tech Stack

- Python 3.10, asyncio
- RabbitMQ (aio_pika) -- async consumer/publisher
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`) + OpenAI
- httpx, requests, tenacity, Pydantic Settings
- Embeds `api-recherche` module as `api_recherche_lib` for Milvus search

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/prix-extraction-siteweb/Dockerfile .
  ```
- Entrypoint: `python main.py` (RabbitMQ consumer, no HTTP server)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`
- Also installs `api-recherche` requirements and copies its code as `api_recherche_lib`

## Folder Structure

```
prix-extraction-siteweb/
  main.py
  Dockerfile
  requirements.txt
  app/
    core/
      prix_extractor.py            # PrixExtractor
      api_client.py
      credentials.py
      search.py                    # Milvus search integration
      utils.py
    messaging/
      consumer.py                  # listens on new_data.prix_siteweb
      publisher.py                 # publishes to data.ready_for_embedding
    schemas/
      prix_extraction.py
      produit_prix_payload.py
```

## Messaging

| Direction | Exchange                      | Routing Key               | Queue                            |
|-----------|-------------------------------|---------------------------|----------------------------------|
| Consumes  | data_exchange_prix_siteweb    | new_data.prix_siteweb     | prix_siteweb_processing_queue    |
| Publishes | processed_data_exchange       | data.ready_for_embedding  | --                               |

- Uses `CollectionName.PRIX_SITEWEB` from common-utils
- Retry/DLQ: per-collection pattern (TTL 30s, max 3 retries)

## Dependencies on Other Services

- **Upstream dispatcher**: publishes to `new_data.prix_siteweb`
- **Embedding pipeline**: consumes from `data.ready_for_embedding`
- **api-recherche**: code embedded at build for Milvus vector search
- **Milvus**: vector DB for website content search
- **HelloPro API**, **RabbitMQ**, **common-utils**

## Conventions

- Each successful extraction item published individually to embedding
- Category-level deduplication (in-memory, per-replica)
- Dockerfile rewrites `api-recherche` imports (`from app.` -> `from api_recherche_lib.`)
