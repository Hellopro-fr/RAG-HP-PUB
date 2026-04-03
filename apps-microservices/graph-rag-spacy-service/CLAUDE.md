# graph-rag-spacy-service
gRPC service providing NLP capabilities via spaCy — tokenization, NER, and text analysis for the RAG pipeline.

## Tech Stack
- **Language:** Python 3.10
- **Protocol:** gRPC server (grpcio + protobuf)
- **NLP:** spaCy (`fr_core_news_sm` French model)
- **Async:** uvloop
- **Observability:** Prometheus metrics

## Build & Run
```bash
pip install -r requirements.txt
python -m spacy download fr_core_news_sm
python -m app.main
```
- **Docker gRPC port:** 50058
- **Docker Prometheus port:** 8569
- Build is Docker-only (includes `spacy download` step)

## Folder Structure
```
app/
  main.py                  # Entrypoint — starts gRPC server
  config.py                # pydantic-settings
application/
  spacy_use_case.py        # NLP processing logic (tokenization, NER)
infrastructure/
  grpc_server.py           # gRPC server definition
```

## Conventions
- Hexagonal Architecture
- French language model downloaded at Docker build time
- Shared libs: `libs/grpc-stubs`, `libs/common-utils`

## API Endpoints
- gRPC service on port **50058** (no REST endpoints)

## Dependencies
- **Consumed by:** API recherche services (Rust and Python)
