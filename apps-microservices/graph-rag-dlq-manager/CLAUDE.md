# graph-rag-dlq-manager
FastAPI service for managing Dead Letter Queue (DLQ) messages — view, requeue, delete, and purge failed messages across the RAG pipeline.

## Tech Stack
- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Messaging:** aio-pika, pika (RabbitMQ AMQP + Management API)
- **Observability:** Prometheus metrics (mounted at `/metrics`)

## Build & Run
```bash
pip install -r requirements.txt
uvicorn main:app --port 8520
```
- **Docker port:** 8520
- Build is Docker-only (uses `libs/common-utils`)

## Folder Structure
```
main.py                        # FastAPI app (root level, not in app/)
app/
  core/config.py               # pydantic-settings (DLQ queues, retry config)
  router/dlq.py                # DLQ management endpoints
  schemas/dlq.py               # Pydantic request/response models
  services/                    # RabbitMQ client (AMQP + Management API)
  utils/params.py              # Router registration params
  utils/router/tags.py         # OpenAPI tags
```

## Conventions
- `main.py` at service root (unlike other services that use `app/main.py`)
- CORS enabled for all origins
- OpenAPI customization with route names as operation IDs

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/dlq/queues` | List all DLQ queues with message counts |
| GET | `/dlq/messages` | List messages in a DLQ (peek mode) |
| POST | `/dlq/requeue` | Requeue messages to retry queue |
| DELETE | `/dlq/messages` | Delete messages from DLQ |
| POST | `/dlq/purge/{queue_name}` | Purge all messages from a queue |
| GET | `/` | Health check |

## Dependencies
- **Direct:** RabbitMQ (AMQP connection + Management API)
- **Monitors:** `graph_rag_normalization_manual_dlq`, `graph_rag_llm_extraction_queue_dlq`
