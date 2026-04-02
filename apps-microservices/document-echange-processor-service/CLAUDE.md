# document-echange-processor-service

Processes document files (PDF/Office) via OCR, cleans and anonymizes text, then publishes for templating. Handles batch processing.

## Tech Stack

- Python 3.11, aio_pika (async), pypdf, presidio (anonymization), beautifulsoup4, markdownify
- System dep: LibreOffice (for Office file conversion)
- Shared lib: `libs/common-utils` (CleanHTML, AnonymizeText, DeepseekOCRDocExtractor, DLQProperties)
- Docker base: `python:3.11-slim`

## Build / Run

- **Build**: `docker build -f Dockerfile -t document-echange-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL` env var

## Folder Structure

```
app/
  main.py              # Async entry point with reconnection loop
  core/processor.py    # process_document_data_for_templating() - OCR + cleanup + anonymization
  messaging/
    consumer.py        # Batch consumer (size=10, timeout=0.5s), ACK-early strategy, DLQ/retry
    publisher.py       # Async publisher to 'processed_data_exchange'
  testmanuel.py        # Manual test script
entrypoint.sh
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_document` | `new_data.document` | `document_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_templating` | - |
| DLQ       | `dead_letter_exchange` | same | `document_processing_queue_dlq` |

## Conventions

- Batch processing: accumulates up to 10 messages, processes together via DeepseekOCR
- ACK-early strategy: JSON decode runs BEFORE ACK; malformed messages sent to DLQ, valid messages ACKed before long OCR processing
- Validates PDF page count (<20 pages) and minimum text length (>200 chars)
- Anonymizes PII using Presidio before publishing
- GC collect after each batch to manage memory
- OCR HTTP timeout: configurable via `DeepseekOCRDocExtractor(timeout=N)` (default 300s, was unbounded)
- Docker: non-root user, `--no-cache-dir`, `--no-install-recommends` for LibreOffice, `.dockerignore`
- `entrypoint.sh` removed (was a dead file with conflicting runtime topology)

## Dependencies on Other Services

- **Upstream**: api-ingestion (produces document URLs)
- **Downstream**: template-llm-service or document-database-qdrant-service
- **Infrastructure**: RabbitMQ, DeepSeek OCR API
