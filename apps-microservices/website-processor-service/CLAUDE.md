# website-processor-service

Extracts and cleans web page content using Trafilatura/Go-Trafilatura/Boilerpy3 with header/footer batch extraction via Redis.

## Tech Stack

- Python 3.13, aio_pika (async), trafilatura, beautifulsoup4, boilerpy3, langdetect, redis, tldextract, pymilvus, psutil, prometheus-client
- Go binary: `go-trafilatura-hp` (built from `libs/common-utils/cleaner/go-trafilatura`)
- Multi-stage Docker: Go 1.24 builder + Python 3.13 slim + JRE (for boilerpy3)
- Shared lib: `libs/common-utils` (TrafilaturaHp, HeaderFooterExtractor, DLQProperties, MilvusWebsiteCrud)

## Build / Run

- **Build**: `docker build -f Dockerfile -t website-processor-service .` (from repo root)
- **Run**: Docker; requires `RABBITMQ_URL`, Redis connection. Prometheus metrics on port 8530

## Folder Structure

```
app/
  main.py                # Async entry point + Prometheus
  core/
    processor.py         # process_website_data_for_embedding() - 3-tier extraction fallback
    redis_manager.py     # Header/footer batch buffering in Redis
    exceptions.py        # BatchProcessingError
  messaging/
    consumer.py          # Async consumer with DLQ, retry, batch error resurrection
    publisher.py         # Async publisher, routes to templating or embedding
Dockerfile
requirements.txt
```

## RabbitMQ Topology

| Direction | Exchange | Routing Key | Queue |
|-----------|----------|-------------|-------|
| Consumes  | `data_exchange_siteweb` | `new_data.website` | `website_processing_queue` |
| Publishes | `processed_data_exchange` | `data.ready_for_templating` or `data.ready_for_embedding` | - |
| DLQ       | `dead_letter_exchange` | same | `website_processing_queue_dlq` |

## Conventions

- Extraction cascade: Trafilatura Python -> Go-Trafilatura -> Boilerpy3 (3 retries each)
- Headers/footers buffered in Redis, processed as batch via HeaderFooterExtractor
- Bypass: if page already classified in Milvus, skip template-llm-service
- Routes dynamically: unclassified pages -> templating; classified -> embedding

## Dependencies on Other Services

- **Upstream**: crawler-service / api-ingestion
- **Downstream**: template-llm-service OR embedding-service
- **Infrastructure**: RabbitMQ, Redis, Milvus/Zilliz (optional bypass)
