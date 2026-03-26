# prix-traitement

REST API for price processing -- identifies price-influencing characteristics via LLM and answers price questionnaires via RAG + LLM.

## Tech Stack

- Python 3.10
- FastAPI + uvicorn
- gRPC (grpcio, protobuf) via shared `grpc-stubs`
- LLM: Google Gemini (`google-genai`)
- httpx, tenacity, Pydantic Settings
- Embeds `api-recherche` module as `api_recherche_lib` for Milvus search

## Build / Run

- **Docker-only build** (context = repo root):
  ```
  docker build -f apps-microservices/prix-traitement/Dockerfile .
  ```
- Entrypoint: `uvicorn main:app --host 0.0.0.0 --port 8591`
- Port: **8591** (Dockerfile EXPOSE says 8595 but CMD uses 8591)
- Shared libs: `libs/common-utils`, `libs/grpc-stubs`
- Also installs `api-recherche` requirements and copies its code as `api_recherche_lib`

## Folder Structure

```
prix-traitement/
  main.py                          # FastAPI app
  Dockerfile
  requirements.txt
  app/
    core/
      prix_service.py              # run_identification, run_questionnaire, run_identification_lot
      api_client.py
      credentials.py               # Settings (Gemini, HelloPro, prompt IDs)
      search.py                    # Milvus search integration
      utils.py
    router/
      prix.py                      # API route definitions
    schemas/
      prix.py                      # Request/Response models
```

## API Endpoints

| Method | Path                       | Description                                               |
|--------|----------------------------|-----------------------------------------------------------|
| GET    | /                          | Health check / welcome message                            |
| POST   | /prix/caracteristique      | Extract price-influencing characteristics for a category  |
| POST   | /prix/questionnaire        | RAG + LLM price questionnaire (search + structured answer)|
| POST   | /prix/caracteristique-lot  | Batch extraction for multiple categories (max 5 parallel) |

## Dependencies on Other Services

- **HelloPro API**: REST calls for category/product data
- **Milvus**: vector search via `api_recherche_lib` (prix collection)
- **Gemini LLM**: prompts 113 (characteristics) and 114 (questionnaire)
- **common-utils**, **grpc-stubs**
- No RabbitMQ dependency (HTTP-only service)

## Conventions

- Dockerfile rewrites `api-recherche` imports at build time
- Batch endpoint uses `asyncio.Semaphore(5)` for concurrency control
