# content-extractor-api-service — Design Spec

> Date: 2026-04-06
> Status: Approved
> Approach: Thin wrapper over `libs/common-utils` (Approach 1)

## Overview

A stateless FastAPI service that exposes `boilerpy3` HTML cleaning and `HeaderFooterExtractor` as a REST API. Sits behind `api-gateway` (which handles auth). No database, queue, or cache dependencies.

**Consumers:**
- **boilerpy3 cleaning (`/clean`):** External teams, internal services, ad-hoc/ops usage
- **HeaderFooterExtractor (`/extract/header-footer`):** External teams only

## Service Structure

```
apps-microservices/content-extractor-api-service/
├── main.py                      # FastAPI app, Uvicorn, CORS, /metrics, /health
├── app/
│   ├── core/
│   │   └── config.py            # Pydantic BaseSettings (PORT, LOG_LEVEL, MAX_PAYLOAD_SIZE_MB)
│   ├── routers/
│   │   ├── clean.py             # POST /clean
│   │   └── extract.py           # POST /extract/header-footer
│   └── schemas/
│       ├── clean.py             # Request/response models for /clean
│       └── extract.py           # Request/response models for /extract
├── tests/
│   ├── test_clean.py
│   └── test_extract.py
├── requirements.txt
├── Dockerfile
└── CLAUDE.md
```

## Dependencies

- `common-utils` — `HeaderFooterExtractor`
- `boilerpy3` — direct import for `/clean` endpoint
- `fastapi`, `uvicorn`, `pydantic`, `prometheus-client`

No RabbitMQ, Redis, or external DB.

## API Endpoints

### POST /clean

Boilerpy3 HTML cleaning. Accepts raw HTML, returns cleaned text or HTML.

**Request:**
```json
{
  "html": "<html>...</html>",
  "format": "text"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `html` | `str` | Yes | — | Raw HTML to clean |
| `format` | `str` | No | `"text"` | `"text"` (plain text) or `"html"` (marked HTML) |

**Response:**
```json
{
  "content": "Extracted main content...",
  "format": "text",
  "content_length": 42
}
```

- `format=text` — `DefaultExtractor().get_content()` (boilerplate removed, plain text)
- `format=html` — `KeepEverythingExtractor().get_marked_html()` (HTML with boilerplate marked)

### POST /extract/header-footer

Header/footer extraction using multi-strategy comparison against reference pages.

**Request:**
```json
{
  "main_html": "<html>...</html>",
  "reference_htmls": ["<html>...</html>", "<html>...</html>"],
  "debug": false
}
```

| Field | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `main_html` | `str` | Yes | — | Non-empty |
| `reference_htmls` | `list[str]` | Yes | — | `min_length=2` |
| `debug` | `bool` | No | `false` | — |

**Response (debug=false):**
```json
{
  "header": "Extracted header text...",
  "footer": "Extracted footer text...",
  "header_method": "structural_intersection",
  "footer_method": "class_intersection"
}
```

**Response (debug=true):** Adds the following fields alongside the base response:

| Field | Type | Description |
|-------|------|-------------|
| `strategies.original` | `{header, footer}` | Semantic/regex strategy results |
| `strategies.class_intersection` | `{header, footer}` | Class-based intersection results |
| `strategies.structural_intersection` | `{header, footer}` | Structural intersection results |
| `intersections_class` | `list[dict]` | Matched elements via class intersection |
| `intersections_structural` | `list[dict]` | Matched elements via structural intersection |
| `cleaned_htmls` | `{main, ref1, ref2, ...}` | boilerpy3-cleaned HTML per input page |
| `gap_analysis` | `list[dict]` | DOM gap scoring details (weighted largest gap) |

### GET /health

Returns `{"status": "ok"}`.

### GET /metrics

Prometheus metrics endpoint.

## Error Handling

Consistent error shape:
```json
{
  "detail": "Human-readable error message",
  "error_code": "EXTRACTION_FAILED"
}
```

| Scenario | Status | Error Code |
|----------|--------|------------|
| Missing/empty `html` field | `422` | Pydantic validation |
| `reference_htmls` has < 2 items | `422` | Pydantic validation |
| Payload exceeds `MAX_PAYLOAD_SIZE_MB` | `413` | `PAYLOAD_TOO_LARGE` |
| boilerpy3 extraction returns empty | `200` | Not an error — `{"content": ""}` |
| All HeaderFooterExtractor strategies fail | `200` | Empty strings, `method: "none"` |
| Unexpected exception | `500` | `INTERNAL_ERROR` (logged, not leaked) |

**Rationale for 200 on empty results:** Extraction producing empty text is a valid outcome. The caller decides if that's an error for their use case.

## Observability

**Prometheus metrics:**

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | `method`, `endpoint`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` |
| `extraction_method_used_total` | Counter | `method` (which strategy won) |

**Logging:** Structured JSON via `common_utils.logging.setup_logging()`. Log extraction duration and method selected per request. No HTML content in logs (privacy + size).

## Data Flow

```
                    ┌──────────────┐
                    │  api-gateway │ (auth, rate limiting)
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       POST /clean              POST /extract/
              │                  header-footer
              ▼                         ▼
┌─────────────────────────┐  ┌──────────────────────────┐
│  boilerpy3 extractors   │  │  HeaderFooterExtractor   │
│  (direct pip import)    │  │  (from common-utils)     │
│                         │  │                          │
│  format=text:           │  │  1. Structural intersect │
│   DefaultExtractor()    │  │  2. Class intersection   │
│   .get_content()        │  │  3. Original semantic    │
│                         │  │                          │
│  format=html:           │  │  Uses boilerpy3          │
│   KeepEverythingExt()   │  │  internally for          │
│   .get_marked_html()    │  │  pre-cleaning            │
└─────────────────────────┘  └──────────────────────────┘
```

Internal consumers call directly via Docker network. External consumers go through `api-gateway`.

## Deployment

**Dockerfile:**
- Base: `python:3.10-slim` (pinned)
- Non-root user
- Copy `requirements.txt` first, install with `--no-cache-dir`, then copy source
- Copy `libs/common-utils` as local dependency
- Healthcheck: `curl --fail http://localhost:${PORT}/health`
- Entrypoint: `uvicorn main:app`

**docker-compose.yml:**
```yaml
content-extractor-api-service:
  build:
    context: .
    dockerfile: apps-microservices/content-extractor-api-service/Dockerfile
  ports:
    - "${CONTENT_EXTRACTOR_API_PORT:-8600}:8600"
  environment:
    - PORT=8600
    - LOG_LEVEL=info
    - MAX_PAYLOAD_SIZE_MB=10
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8600/health"]
    interval: 30s
    timeout: 10s
    retries: 3
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

**CI/CD:** `ci_services_content_extractor_api.yml` and `cd_build_push_content_extractor_api.yml` following existing patterns.

## Configuration

All via Pydantic `BaseSettings` in `app/core/config.py`:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `PORT` | `int` | `8600` | Service port |
| `LOG_LEVEL` | `str` | `"info"` | Logging level |
| `MAX_PAYLOAD_SIZE_MB` | `int` | `10` | Max request body size |
