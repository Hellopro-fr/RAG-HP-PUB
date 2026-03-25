# api-recherche-service

Dedicated deployment variant of `api-recherche` running on a different port. Shares the same codebase (Dockerfile copies from `api-recherche`).

## Tech Stack

- Same as `api-recherche` (FastAPI, Gunicorn, Milvus, gRPC, Redis)

## Build / Run

- **Port:** 8511
- **Run:** `gunicorn -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8511 --timeout 120 main:app`
- **Docker build:** uses `api-recherche` source code, 3 workers instead of 8

## Folder Structure

- Only contains a `Dockerfile`; code is copied from `api-recherche/`.

## API Endpoints

Same as `api-recherche`: `POST /search`, `WS /ws/search`, `GET /`

## Dependencies on Other Services

Same as `api-recherche`: Milvus, Redis, embedding/reranking gRPC services, LLM providers.
