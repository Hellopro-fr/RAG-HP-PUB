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

## Recent Security & Reliability Fixes

- **embedding_client**: shared gRPC channel sets `grpc.max_receive_message_length` to 64 MB — a ~1000+ chunk page's `GetEmbeddings` response (1024 float32/chunk) exceeded the 4 MiB gRPC default → client-side `RESOURCE_EXHAUSTED`, 3 deterministic retries, DLQ. Server side raised symmetrically in `embedding-model-service/infrastructure/grpc_server.py` (`_SERVER_OPTIONS`).

- **MilvusWebsiteCrud**: `insert_website()` projects each record onto the fixed `siteweb_2` schema (`_INSERT_FIELDS` whitelist) — extra upstream keys (e.g. `commentaire_si_autre` from template-llm-service) previously failed the whole insert with an empty-repr `DataNotMatchException`. `MilvusException` is now wrapped in `RuntimeError` with context before re-raising (readable DLQ `x-error-reason`).
- **TrafilaturaCleaning**: all `markdownify` call sites go through `_md_safe()`, which converts `RecursionError` on pathologically nested DOMs (e.g. Liferay pages) into an empty extraction so the 3-tier cascade can fall through instead of crashing the message.
- **Utils**: `to_valid_utf8()` drops lone surrogates + C0/C1 control chars (keeps `\t\n\r`); `sanitize_record()` now applies it to every string value, so no Milvus CRUD can hand the server invalid UTF-8 (rejected as code 65535). `MilvusPjCrud.get_pj` / `MilvusDocumentCrud.get_document` also run it on the query-expr filename (the `sanitize_record` path only covers insert/update, not the query).
- **MilvusPjCrud**: `insert_pj()` projects each record onto the fixed `pjechanges` schema (`_INSERT_FIELDS` whitelist), replacing the fragile hand-maintained `del document`/`del annnee` denylist — extra upstream keys previously failed the insert with `DataNotMatchException`. Mirrors the `MilvusWebsiteCrud._INSERT_FIELDS` fix.
- **DeepseekOCRDocExtractor**: `_validate_pdf_page_count()` fails open — a PDF pypdf can't parse (e.g. a malformed `startref` trailer) is deferred to the OCR renderer instead of permanent-DLQ; the post-OCR page-count/min-text gates still apply. The too-many-pages rejection stays permanent.
- **CleanHTML**: the internal `md()` catches `RecursionError` (deeply nested table DOM) → empty result instead of crashing the caller, matching the `TrafilaturaCleaning._md_safe` pattern.

- **DLQProperties**: `create_dlq_headers()` now uses `repr(error)` for richer error messages in DLQ headers.
- **MilvusDocumentCrud / MilvusPjCrud**: `_ensure_connected()` uses `utility.list_collections()` RPC health check instead of unreliable `has_connection()`. Expression injection prevented via input sanitization in `get_document()`/`get_pj()` and type validation in `delete_document()`/`delete_pj()`.
- **MilvusPjCrud**: `update_pj()` returns serializable `"updated"` string instead of raw `MutationResult`.
- **MilvusDocumentCrud / MilvusPjCrud**: `_validate_varchar_lengths()` pre-validates all VARCHAR fields before insert/upsert using **UTF-8 byte length** (Milvus counts bytes, not Python chars), raising `ValueError` with field name, byte length, and preview. `MilvusException` is now wrapped in `RuntimeError` with operation context before re-raising, ensuring readable DLQ headers.
- **DeepseekOCRDocExtractor**: HTTP timeout now uses `self.timeout` (default 300s) instead of `None` (unbounded). `get_clean_result()` guards against `None` page results (blank pages). `_validate_pdf_page_count()` no longer includes filename in the `ValueError` message (caller has it). `_download_file()` sends `User-Agent: HelloPro-RAG-Pipeline/1.0` header to prevent 403 from bot detection.
