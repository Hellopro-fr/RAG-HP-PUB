# RAG-HP-PUB

RAG (Retrieval-Augmented Generation) platform for HelloPro — 90+ microservices for product search, classification, pricing extraction, and quality control.

## Service Map

| Category | Services | Language/Framework | Local? |
|---|---|---|---|
| Graph-RAG Core | `graph-rag-api-recherche-rust-service` | Rust / Actix-web / Neo4j | Remote (GPU) |
| Graph-RAG Python | `graph-rag-*` (17 services) | Python / FastAPI / gRPC | Remote |
| Qdrant Databases | `*-database-qdrant-service` (7) | Python / FastAPI / Qdrant | Remote |
| Qdrant Processors | `*-processor-service` (6) | Python / FastAPI / RabbitMQ | Remote |
| API Services | `api-*` (16 services) | Python / FastAPI | Remote |
| QC Services | `QC-*` (8 services) | Python / FastAPI | Remote |
| Prix Services | `prix-*` (6 services) | Python / FastAPI | Remote |
| ML/LLM Services | `llm-service`, `embedding-*`, `reranking-*` | Python / FastAPI / Triton | Remote (GPU) |
| Frontends | `api-chatbot-html-service`, `nextjs-formulaire-hp`, etc. | Next.js / React / Vite | Local OK |
| Crawlers | `crawler-service`, `crawler-monitor-*` | Node.js / Crawlee / Express | Local OK |
| Image Services | `image-*` (3 services) | Python / FastAPI | Remote |
| Infrastructure | `tools/`, `model-optimizer/`, `protos/` | Python / Protobuf | Local (tools) |
| Libraries | `libs/common-utils`, `libs/rust-common-utils` | Python / Rust | Local |

## Monorepo Navigation

```
apps-microservices/   # All 90+ microservices (each with Dockerfile)
libs/
  common-utils/       # Shared Python: Milvus CRUD, HTML cleaning, Redis, metrics
  rust-common-utils/  # Shared Rust: gRPC client definitions
  grpc-stubs/         # Generated Python gRPC stubs
protos/grpc_stubs/    # .proto definitions (embedding, llm, reranking, spacy, etc.)
tools/                # DLQ archiver/requeuer, S3 upload/download daemons
model-optimizer/      # ONNX model export scripts (embedding + reranker)
grafana/              # Grafana dashboard provisioning
prometheus/           # Prometheus config (prometheus.yml)
docs/                 # Project documentation
.github/workflows/    # CI (ci_services_*) and CD (cd_build_push_*) pipelines
```

## Shared Conventions

- **Python services**: FastAPI + Uvicorn, Pydantic schemas, Prometheus `/metrics`, structured logging.
- **Messaging**: RabbitMQ (pika) for async processing; most processors consume from queues.
- **Inter-service RPC**: gRPC via `protos/` definitions; Python stubs in `libs/grpc-stubs`, Rust in `libs/rust-common-utils`.
- **Containerization**: Every service has a Dockerfile; root `docker-compose.yml` orchestrates infra.
- **Type checking**: Pyrefly (`pyrefly.toml`) for Python; `cargo check` for Rust.
- **CI/CD**: GitHub Actions — `ci_services_*.yml` (lint/test), `cd_build_push_*.yml` (Docker build+push).
- **Commit messages**: Conventional Commits, bilingual EN/FR (see `.claude/rules/commit-messages.md`).

## Constraints

### Remote-Only Services
Most Python/Rust microservices run on a remote server with GPU and network access to Neo4j, Milvus, Qdrant, RabbitMQ, Redis. **Locally you CAN**: lint, typecheck (`pyrefly`, `cargo check`), run unit tests with mocks. **You CANNOT**: run integration tests, start the full service, connect to production DBs.

### GPU-Dependent
`vllm-server`, `triton-server`, `embedding-model-service`, `reranking-model-service` — require NVIDIA GPU.

### Shared Infrastructure
- **RabbitMQ**: Message broker for all processor services
- **Redis**: Caching layer (used by api-gateway, image services, crawlers)
- **Neo4j**: Graph database (Graph-RAG services)
- **Milvus**: Vector database (embedding search)
- **Qdrant**: Vector database (category/product/document search)
- **Elasticsearch**: Full-text search (disabled by default in compose)

## Sub-Agent Routing

- **Rust service** (`graph-rag-api-recherche-rust-service`): use for Actix-web, Neo4j, gRPC client work.
- **Python FastAPI services**: most follow identical patterns — check one as template.
- **Frontend services**: Next.js/React — separate Node.js toolchain.
- **Proto changes**: update `protos/`, regenerate stubs in `libs/grpc-stubs` and `libs/rust-common-utils`.
- **Shared Python utils**: changes in `libs/common-utils` affect many services.

## Per-Service Instructions

@apps-microservices/*/CLAUDE.md
@libs/*/CLAUDE.md
@tools/CLAUDE.md
@model-optimizer/CLAUDE.md
@protos/CLAUDE.md
