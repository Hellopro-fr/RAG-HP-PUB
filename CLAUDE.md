# RAG-HP-PUB

RAG (Retrieval-Augmented Generation) platform for HelloPro — 90+ microservices for product search, classification, pricing extraction, and quality control.

## Service Map

Motifs, pas comptes : `ls apps-microservices/ | wc -l` donne le nombre du jour (99 au 2026-08-03).
Les compteurs qui figuraient ici — 17 graph-rag, 7 qdrant, 6 processors, 8 QC, 6 prix — etaient faux sur 5 lignes sur 7 : ils ne sont pas re-derives quand un service est ajoute, et ce fichier est injecte a chaque requete.

| Category | Services | Language/Framework | Local? |
|---|---|---|---|
| Graph-RAG Core | `graph-rag-api-recherche-rust-service` | Rust / Actix-web / Neo4j | Remote (GPU) |
| Graph-RAG Python | `graph-rag-*` | Python / FastAPI / gRPC | Remote |
| Qdrant Databases | `*-database-qdrant-service` | Python / FastAPI / Qdrant | Remote |
| Qdrant Processors | `*-processor-service` | Python / FastAPI / RabbitMQ | Remote |
| API Services | `api-*`, `content-extractor-api-service` | Python / FastAPI | Remote |
| QC Services | `QC-*` | Python / FastAPI | Remote |
| Prix Services | `prix-*` | Python / FastAPI | Remote |
| ML/LLM Services | `llm-service`, `embedding-*`, `reranking-*` | Python / FastAPI / Triton | Remote (GPU) |
| Frontends | `api-chatbot-html-service`, `nextjs-formulaire-hp`, etc. | Next.js / React / Vite | Local OK |
| MCP Template Runner | `mcp-google-templates-runner` | Python / FastAPI / asyncio | Local OK |
| MCP Zoho Proxy | `mcp-zoho-service` | Go / net/http | Remote |
| Crawlers | `crawler-service`, `crawler-monitor-*` | Node.js / Crawlee / Express | Local OK |
| Image Services | `image-*` | Python / FastAPI | Remote |
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
**Et s'il contredit ce que tu lis dans le code, corrige-le dans le meme commit.** Mesure du 2026-08-03 : sur 98 CLAUDE.md de service, 39 ont plus de 30 jours de retard sur le dernier commit de leur propre service, 10 plus de 120 jours (tous du lot initial du 2026-03-25, jamais retouches). Un rafraichissement de masse en reproduirait 39 qui repourriraient ensemble : la correction se fait a la touche, par celui qui constate l'ecart.
Ils ne sont PAS importes ici : un `@import` avec glob ne s'expanse pas — verifie le 2026-08-03 par sonde, un marqueur present uniquement dans `apps-microservices/*/CLAUDE.md` n'etait pas visible du modele, alors que les imports litteraux ci-dessous l'etaient. Et les importer tous couterait 8 599 lignes a chaque requete pour 101 fichiers dont un seul sert a la fois.

@tools/CLAUDE.md
@model-optimizer/CLAUDE.md
@protos/CLAUDE.md

## graphify

This project has a **unified graphify knowledge graph** at `graphify-out/` covering libs + tools + model-optimizer + docs + the services merged in so far — **4 of the 99** at 2026-08-04: `crawler-service`, `api-detection-langue-fr`, `graph-rag-api-recherche-rust-service`, `api-gateway-go` (the LIVE Go ingress; the Python `api-gateway` is deprecated and deliberately NOT graphed). More are added one at a time via `/graphify apps-microservices/<service> --update`. Per-service node counts drift on every re-clustering — read them from `graphify-out/services-policy.yml` and the graph itself, not from here.
Before widening much: the observed ratio is ~12.3 nodes per source file at ~1.5 KB per node, and 777 of the 2659 source files are inside the graph — full coverage would land around 32 000 nodes and ~48 MB **per revision**, against 14 MB today. Cost in git is currently a non-issue (successive revisions delta extremely well); the thing to re-check after each widening is that delta efficiency, not the raw size. Note also that `graph.html` was already retired at graphify's 5000-node render ceiling — at 9551 nodes you are well past it, and a full sweep goes 3x further. 9551 nodes, ~20 900 edges, 254 communities (re-derived 2026-08-04 from `graphify-out/graph.json` — re-measure before quoting, it grows on every merge), with explicit cross-service edges (e.g. `crawler_capacity_counter --uses--> cache_service.py`).

Rules:
- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes, community structure, and suggested questions.
- For cross-module "how does X relate to Y" questions, prefer the `/graphify query "<question>"`, `/graphify path "<A>" "<B>"`, or `/graphify explain "<concept>"` slash commands over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files.
- After modifying code files in this session, re-extract **with an explicit path**: `/graphify apps-microservices/<service> --update`. The path argument is the ONLY thing that bounds scope. Verified 2026-08-04 in `graphify/detect.py:468`: `detect_incremental(root)` calls `detect(root)` first, so the file set comes entirely from the path you pass; the manifest is just a `file -> mtime` table used to skip unchanged files. A bare `/graphify --update` is therefore exactly as wide as `graphify update .` — both rescan the whole monorepo and pull in all 99 services. Never run either without a path.
- Do NOT delete `graphify-out/manifest.json` to "reset scope" — it does the opposite. `detect_incremental` treats a missing manifest as "everything is new" (`full["new_files"] = full["files"]`), so removing it turns the next update into a full re-extraction. It currently holds 3363 entries across 97 services (from a 2026-07-01 wide run) while the graph holds 3 — that mismatch is harmless, and each stale entry is one more file the updater skips.
- For autonomous per-commit rebuilds: run `bash scripts/install-graphify-hook.sh` once per clone. The scoped post-commit hook derives the in-scope file set from `graphify-out/graph.json` (tracked, so every teammate gets the right scope right after `git pull`), runs AST only on in-scope changes, and never calls the LLM. Commits outside scope are silently ignored.
- Remember edge honesty tags: EXTRACTED (AST-sourced, trust fully), INFERRED (LLM-reasoned, verify before refactoring shared components), AMBIGUOUS (flagged, verify). INFERRED edges may also have flipped direction — the graph is undirected, so interpret bidirectionally.
- Do NOT run `graphify hook install` from the upstream CLI — it installs an unscoped hook that explodes the graph. Use `scripts/install-graphify-hook.sh` instead. See `docs/graphify-guide-en.md` § "Scoped hook vs. upstream hook" for the reason.
- Full team guide: `docs/graphify-guide-en.md` (English) or `docs/graphify-guide-fr.md` (Français).
