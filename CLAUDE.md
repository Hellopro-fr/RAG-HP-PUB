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
- **Type checking**: `cargo check` for Rust. No Python type checker enforced yet (ruff or mypy recommended — team decision pending).
- **CI/CD**: GitHub Actions — `ci_services_*.yml` (lint/test), `cd_build_push_*.yml` (Docker build+push).
- **Commit messages**: Conventional Commits, bilingual EN/FR (see `.claude/rules/commit-messages.md`).

## Claude Code Configuration

### Rules (`.claude/rules/`)

| Rule | Purpose |
|------|---------|
| `code-modification.md` | Surgical edit protocol: read first, minimal diff, preserve formatting, verify after |
| `commit-messages.md` | Bilingual Conventional Commits, scope to current response, < 72 chars |
| `language.md` | Respond in user's language, bilingual commits, English code identifiers |
| `security.md` | No hardcoded secrets/URLs, Pydantic BaseSettings, CORS (internal vs public), JWT, input validation, all infra connection strings |
| `impact-awareness.md` | Trade-off analysis, bigger-picture context, blast radius check on shared components before any modification |
| `docker-security.md` | Pinned base images, no root, healthchecks, no secrets in ENV, `.dockerignore`, `--no-cache-dir` |
| `config-freshness.md` | Re-read `.claude/` files mid-conversation before using agents/commands |
| `formatting.md` | Code style conventions per stack (Python, Rust, JS/TS): indentation, imports, naming, line length |
| `refactoring.md` | When/how to refactor safely: scope rules, shared component protocol, known duplication targets |

### Agents (`.claude/agents/`)

| Agent | Purpose | Tools |
|-------|---------|-------|
| `code-reviewer` | SOLID/DRY/KISS, security, performance, error handling, impact awareness. Exhaustive single-pass (multi-pass internally). | Read, Glob, Grep |
| `debugger` | Root cause analysis → structured fix plan with trade-offs and blast radius → apply after confirmation. | Read, Bash, Glob, Grep |
| `doc-writer` | Add file-level, function-level, and inline documentation. English docstrings only. Code-immutable. | Read, Write, Edit, Glob, Grep |
| `test-writer` | Stack-agnostic test generation: auto-detects Python (pytest), Rust (cargo test), Node.js (Jest/Vitest), or asks for unknown stacks. | Read, Write, Edit, Glob, Grep |

### Commands (`.claude/commands/`)

| Command | Purpose |
|---------|---------|
| `/commit-msg` | Generate bilingual commit message (EN/FR) |
| `/explain` | Explain a single file or code block (no modifications) |
| `/understand` | Absorb and summarize multiple files or broad topics |
| `/plan` | Interactive planning with step list and optional file table |
| `/pre-push` | Pre-push verification: syntax, tests, review, summary table |
| `/new-service-claude-md` | Generate CLAUDE.md for a new service + update root |
| `/new-feature-claude-md` | Update service CLAUDE.md after a feature addition |
| `/update-claude-md` | Propose surgical CLAUDE.md updates (mistake prevention, project change, rescan) |
| `/investigate` | Evidence-based statement verification: CONFIRMED / PARTIALLY TRUE / FALSE / INCONCLUSIVE |
| `/audit-feature` | End-to-end feature audit tracing the pipeline across services |
| `/review-task` | Tech Lead review: combined state + diff analysis, verdict APPROVED / CHANGES REQUESTED / BLOCKED |

### Skills (`.claude/skills/`)

| Skill | Purpose |
|-------|---------|
| `/fastapi-service-scaffold <name> <desc>` | Scaffold a new FastAPI service with all conventions |
| `/rabbitmq-consumer-scaffold <name> <collection>` | Scaffold a new RabbitMQ processor with consumer, DLQ, metrics |
| `/proto-sync [proto-file]` | Regenerate Python gRPC stubs from protos/ and check for breaking changes |

### Hooks (`settings.json`)

| Event | Purpose |
|-------|---------|
| `Stop` | After each response: (1) check if CLAUDE.md files need updating, (2) self-review modified code for quality/security/impact |

## Constraints

### Remote-Only Services
Most Python/Rust microservices run on a remote server with GPU and network access to Neo4j, Milvus, Qdrant, RabbitMQ, Redis. **Locally you CAN**: lint, typecheck (`cargo check` for Rust), run unit tests with mocks. **You CANNOT**: run integration tests, start the full service, connect to production DBs.

### GPU-Dependent
`vllm-server`, `triton-server`, `embedding-model-service`, `reranking-model-service` — require NVIDIA GPU.

### Shared Infrastructure
- **RabbitMQ**: Message broker for all processor services
- **Redis**: Caching layer (used by api-gateway, image services, crawlers)
- **Neo4j**: Graph database (Graph-RAG services)
- **Milvus**: Vector database (embedding search)
- **Qdrant**: Vector database (category/product/document search)
- **Elasticsearch**: Full-text search (disabled by default in compose)

### MCP Servers
`settings.json` enables all project MCP servers (`enableAllProjectMcpServers: true`). When adding a new MCP server, ensure it is reviewed by the team before merging — this flag grants full tool access to every configured server.

## Sub-Agent Routing

- **Rust service** (`graph-rag-api-recherche-rust-service`): use for Actix-web, Neo4j, gRPC client work. Note: no dedicated Rust agent exists yet — use the general-purpose agent with Rust context.
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
