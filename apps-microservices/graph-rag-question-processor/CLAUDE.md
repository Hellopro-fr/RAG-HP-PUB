# graph-rag-question-processor
RabbitMQ consumer that ingests question data into the Neo4j graph database via the database-connector gRPC service.

## Tech Stack
- **Language:** Python 3.10
- **Messaging:** aio_pika (async RabbitMQ)
- **gRPC client:** grpcio (calls database-connector)
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m app.main
```
- **Docker:** no explicit EXPOSE (Prometheus on port 8571)
- Build is Docker-only

## Folder Structure
```
app/
  main.py                          # Entrypoint
  config.py                        # pydantic-settings
  core/processor.py                # Question processing logic
  messaging/consumer.py            # RabbitMQ consumer
  infrastructure/database_client.py  # gRPC client
```

## Conventions
- Simple processor with no batching or concurrency configuration
- Uses `RabbitMQConsumer` class pattern (vs `Consumer` in other processors)

## API Endpoints
- None (RabbitMQ consumer only)

## Dependencies
- **Input:** `graph_rag_question_queue` (exchange: `data_graph_exchange_questions`, key: `question.create`)
- **gRPC:** database-connector (50055)
