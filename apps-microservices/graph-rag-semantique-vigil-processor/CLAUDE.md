# graph-rag-semantique-vigil-processor
RabbitMQ consumer that performs semantic deduplication — checks embeddings similarity before allowing data through to the final ETL stage.

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **gRPC client:** grpcio (calls embedding-service, milvus-service)
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker port:** 8563 (Prometheus only)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                    # Entrypoint
  config.py                  # pydantic-settings (similarity threshold, queues, batching)
  core/processor.py          # Semantic deduplication logic
  messaging/consumer.py      # RabbitMQ consumer
  messaging/publisher.py     # Publishes approved data downstream
  infrastructure/clients.py  # gRPC service clients
```

## Conventions
- Similarity threshold: `SIMILARITY_THRESHOLD=0.90`
- Batching: `BATCH_SIZE=10`, `BATCH_TIMEOUT_SECONDS=2.0`
- Rejects near-duplicates, passes unique data through

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_semantic_vigil_queue` (exchange: `graph_rag_semantic_check`, key: `graph_rag.semantic.check`)
- **Output:** `graph_rag_final_etl` (key: `graph_rag.etl.ready`)
- **gRPC:** embedding-service (50051), milvus-service (50056)
- **Upstream:** normalize-unite-processor
- **Downstream:** etl-processor
