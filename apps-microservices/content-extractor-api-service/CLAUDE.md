# content-extractor-api-service

REST API exposing boilerpy3 HTML cleaning and HeaderFooterExtractor for external teams, internal services, and ad-hoc usage.

## Tech Stack

- Python 3.10 / FastAPI / Uvicorn
- boilerpy3 (HTML cleaning)
- common-utils (HeaderFooterExtractor)
- Prometheus metrics

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/clean` | POST | boilerpy3 HTML cleaning (text or HTML output) |
| `/extract/header-footer` | POST | Header/footer extraction with optional debug mode |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8600
```

## Test

```bash
python -m pytest tests/ -v
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8600` | Service port |
| `LOG_LEVEL` | `"info"` | Logging level |
| `MAX_PAYLOAD_SIZE_MB` | `10` | Max request body size |

## Dependencies

- No RabbitMQ, Redis, or database
- Sits behind `api-gateway` for auth
- Imports `HeaderFooterExtractor` from `libs/common-utils`

## What This Provides to Other Services

- On-demand HTML content extraction without going through the RabbitMQ pipeline
- Header/footer detection API for external consumers
