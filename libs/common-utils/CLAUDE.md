# common-utils

Shared Python library providing reusable modules for all Python microservices in the RAG pipeline.

## Tech Stack

- Python 3.10+
- setuptools (packaging)
- Milvus / Qdrant (vector DBs), RabbitMQ (messaging), Redis (caching)
- gRPC client wrappers, Prometheus metrics

## Install

```bash
pip install -e libs/common-utils
```

## Folder Structure

```
src/common_utils/
  autres/          # Helpers: collection names, webhooks, DLQ properties
  cleaner/         # HTML cleaning (Trafilatura), text anonymization
    go-trafilatura/ # Go-based Trafilatura wrapper
    schemas/       # Cleaner data schemas
  database/        # CRUD classes for Milvus and Qdrant collections
    config/        # DB connection settings
    schemas/       # Pydantic models (devis, echange, produit, website)
  embedding/       # Embedding utility module
  extractor/       # PDF processing, header/footer extraction
  grpc_clients/    # Typed gRPC client wrappers (embedding, llm, reranking, spacy, graph_*)
    schemas/       # Chat request/response schemas
  llm/             # LLM provider abstraction
  metrics/         # Prometheus instrumentation helpers
  ocr/             # OCR extractors (Deepseek, standard, document)
  rabbitmq/        # RabbitMQ connection helpers
  redis/           # Redis cache service
```

## Conventions

- One class per file, PascalCase filenames matching class names.
- Database modules follow the pattern `Milvus{Entity}Crud.py` / `Qdrant{Entity}Crud.py`.
- gRPC clients are thin wrappers; proto definitions live in `protos/`.
- Package is imported as `from common_utils.<module> import <Class>`.

## What This Provides to Other Services

- Centralized gRPC client stubs for embedding, LLM, reranking, spacy, and graph services.
- Shared database CRUD operations for Milvus and Qdrant vector stores.
- RabbitMQ connection management and DLQ property helpers.
- Text cleaning, OCR, PDF extraction, and anonymization utilities.
- Prometheus metrics instrumentation.
- Redis caching layer.
