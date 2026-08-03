# RAG-HP-PUB

RAG (Retrieval-Augmented Generation) platform for HelloPro — 90+ microservices for product search, classification, pricing extraction, and quality control.

## Service Map

| Category | Services | Language/Framework | Local? |
|---|---|---|---|
| Graph-RAG Core | `graph-rag-api-recherche-rust-service` | Rust / Actix-web / Neo4j | Remote (GPU) |
| Graph-RAG Python | `graph-rag-*` (17 services) | Python / FastAPI / gRPC | Remote |
| Qdrant Databases | `*-database-qdrant-service` (7) | Python / FastAPI / Qdrant | Remote |
| Qdrant Processors | `*-processor-service` (6) | Python / FastAPI / RabbitMQ | Remote |
| API Services | `api-*`, `content-extractor-api-service` (17) | Python / FastAPI | Remote |
| QC Services | `QC-*` (8 services) | Python / FastAPI | Remote |
| Prix Services | `prix-*` (6 services) | Python / FastAPI | Remote |
| ML/LLM Services | `llm-service`, `embedding-*`, `reranking-*` | Python / FastAPI / Triton | Remote (GPU) |
| Frontends | `api-chatbot-html-service`, `nextjs-formulaire-hp`, etc. | Next.js / React / Vite | Local OK |
| MCP Template Runner | `mcp-google-templates-runner` | Python / FastAPI / asyncio | Local OK |
| MCP Zoho Proxy | `mcp-zoho-service` | Go / net/http | Remote |
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
- **Commit messages**: Conventional Commits, bilingual EN/FR. The `conventional-commits.py` PreToolUse hook checks the Conventional *prefix* on the first line only — the bilingual body, the subject length and the scoping are conventions, not machine-enforced. `/commit-msg` writes a message that respects all of them.
- **Language**: reply in the language of the current message. Identifiers, file names, log messages and error codes always in English. Code comments and docstrings are **mixed FR/EN across this repo** (measured: Python is an even split, TS/Vue leans EN) — follow the file you are editing, never retranslate existing comments.

## PHP front Ecritel

Ces fichiers ne passent PAS par une Pull Request : upload FTP manuel sur Ecritel.
Procedure complete, liste des chemins concernes et exceptions : `site/CLAUDE.md`
(charge automatiquement des que tu ouvres un fichier sous `site/`).

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

**Avant de modifier un fichier sous `apps-microservices/<service>/` ou `libs/<lib>/`, lis d'abord le `CLAUDE.md` de ce service ou de cette lib.**
Ils ne sont PAS importes ici : un `@import` avec glob ne s'expanse pas — verifie le 2026-08-03 par sonde, un marqueur present uniquement dans `apps-microservices/*/CLAUDE.md` n'etait pas visible du modele, alors que les imports litteraux ci-dessous l'etaient. Et les importer tous couterait 8 599 lignes a chaque requete pour 101 fichiers dont un seul sert a la fois.

@tools/CLAUDE.md
@model-optimizer/CLAUDE.md
@protos/CLAUDE.md

## graphify

This project has a **unified graphify knowledge graph** at `graphify-out/` covering libs + protos + tools + model-optimizer + docs + any merged-in services (crawler-service today; more added via `/graphify <service> --update`). ~8 850 nodes, ~19 600 edges (re-derived 2026-08-03 from `graphify-out/graph.json` — re-measure before quoting, it grows on every rebuild), with explicit cross-service edges (e.g. `crawler_capacity_counter --uses--> cache_service.py`).

Rules:
- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes, community structure, and suggested questions.
- For cross-module "how does X relate to Y" questions, prefer the `/graphify query "<question>"`, `/graphify path "<A>" "<B>"`, or `/graphify explain "<concept>"` slash commands over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files.
- After modifying code files in this session, run `/graphify --update` (the slash command inside this session, NOT the `graphify update .` CLI). The slash command uses the scoped manifest and re-extracts only changed files; the CLI rescans the whole directory and in this monorepo that pulls in `apps-microservices/` and explodes the graph.
- For autonomous per-commit rebuilds: run `bash scripts/install-graphify-hook.sh` once per clone. The scoped post-commit hook derives the in-scope file set from `graphify-out/graph.json` (tracked, so every teammate gets the right scope right after `git pull`), runs AST only on in-scope changes, and never calls the LLM. Commits outside scope are silently ignored.
- Remember edge honesty tags: EXTRACTED (AST-sourced, trust fully), INFERRED (LLM-reasoned, verify before refactoring shared components), AMBIGUOUS (flagged, verify). INFERRED edges may also have flipped direction — the graph is undirected, so interpret bidirectionally.
- Do NOT run `graphify hook install` from the upstream CLI — it installs an unscoped hook that explodes the graph. Use `scripts/install-graphify-hook.sh` instead. See `docs/graphify-guide-en.md` § "Scoped hook vs. upstream hook" for the reason.
- Full team guide: `docs/graphify-guide-en.md` (English) or `docs/graphify-guide-fr.md` (Français).
