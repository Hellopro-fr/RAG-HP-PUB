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
- **Commit messages**: Conventional Commits, bilingual EN/FR (see `.claude/rules/commit-messages.md`).

## PHP front Ecritel — workflow

**Règle stricte : on ne crée PAS de Pull Request pour les fichiers PHP front Ecritel.**
Le développeur (rravelonarisoa@hellopro.fr) uploade ces fichiers manuellement via FTP sur le serveur Ecritel. Les PRs sur ces fichiers polluent l'historique git sans valeur ajoutée (pas de CI, pas de déploiement automatique, fichier non tracké en prod).

### Fichiers concernés (PHP front Ecritel)

| Chemin local repo | Statut git | Workflow |
|---|---|---|
| `site/hellopro_fr/*.php` | non tracké | Upload FTP manuel |
| `site/annuaire_hp/fonctions/*.php` | non tracké | Upload FTP manuel |
| `site/moteur_recherche/*.php` (search_ajax.php, etc.) | non tracké | Upload FTP manuel |
| `site/design_system/js/*.js` | non tracké | Upload FTP manuel |
| `site/fichiers_communs_bo_front/**/*.json` | non tracké | Upload FTP manuel |
| `site/script/**/*.php` (crons) | tracké git | PR OK (déployé via script.hellopro.fr) |
| `site/moteur_recherche/*.md` (docs/specs) | tracké git | PR OK (mémoire technique) |

### Procédure correcte pour modifier un fichier Ecritel

1. **Modifier le fichier local** dans le repo (édition directe)
2. **NE PAS créer de PR** sur le fichier `.php` lui-même
3. **Créer un doc `.md`** dans `site/moteur_recherche/` (ex: `FIX_XXX_YYYY-MM-DD.md`) qui contient :
   - Le diff appliqué (en bloc markdown)
   - Le contexte / motivation
   - Les tests post-deploy
4. **PR avec uniquement le `.md`** (spec / review-only)
5. **Upload manuel FTP** du `.php` modifié vers Ecritel par le développeur
6. **Test sur prod** + validation

### Exemple

- ❌ Ne pas faire : PR contenant `site/hellopro_fr/moteur_recherche.php` ajouté/modifié
- ✅ Faire : PR contenant `site/moteur_recherche/BASCULE_DEFAULT_HYBRID_2026-05-22.md` (doc avec diff), upload manuel du `.php`

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
| `formatting.md` | Code style conventions per stack — references `stack-detection.md`, with unknown stack fallback |
| `refactoring.md` | When/how to refactor safely: scope rules, shared component protocol, known duplication targets |
| `stack-detection.md` | Single source of truth for detecting a service's stack from file indicators. All stack-dependent rules reference this. Unknown stack protocol included. |
| `critical-thinking.md` | Anti-sycophancy, blind spot detection, evidence-based pushback, uncertainty transparency, anti-rationalization |
| `lessons-learned.md` | Self-improving error-avoidance: when/how Claude saves a lesson, dedup rule, per-file-type category routing. Consumed by the inject-lessons hook. |

### Agents (`.claude/agents/`)

| Agent | Purpose | Tools |
|-------|---------|-------|
| `code-reviewer` | SOLID/DRY/KISS, security, performance, error handling, impact awareness. Exhaustive single-pass (multi-pass internally). | Read, Glob, Grep |
| `security-reviewer` | Deep SOURCE-CODE security audit — OWASP Top 10, auth/authz, injection, LLM/RAG-specific risks (prompt injection, data exfil, model supply chain), crypto, Docker/IaC, CI workflows. Read-only. | Read, Glob, Grep |
| `cybersecurity-auditor` | EXTERNAL web audit against a URL (DAST-style, non-intrusive). Runs inside a **Kali Docker container** (`tools/cyber-audit/`) with `--cap-drop=ALL`. HTTP headers, TLS, cookies, CORS, DNS (SPF/DMARC/DKIM/CAA/DNSSEC), well-known paths, TCP connect scan. Invoked via `/cyber-audit <url>` after authorization. | Bash, Read, Grep, WebFetch |
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
| `/secrets-scanner` | Full codebase scan for hardcoded secrets, API keys, passwords, connection strings |
| `/test-coverage` | Test coverage report across all services (well-tested / minimal / none) |
| `/dependency-mapper` | Map cross-service dependencies: imports, gRPC, RabbitMQ, HTTP calls |
| `/architecture-review` | Architecture-level review: coupling, cohesion, scalability, observability |
| `/cyber-audit <url>` | External web security audit of a URL. Runs the Kali container in `tools/cyber-audit/` (DAST, non-intrusive): TLS, headers, cookies, CORS, DNS, well-known paths, top-20 TCP ports. Requires authorization confirmation. |

### Skills (`.claude/skills/`)

| Skill | Purpose |
|-------|---------|
| `/fastapi-service-scaffold <name> <desc>` | Scaffold a new FastAPI service with all conventions |
| `/rabbitmq-consumer-scaffold <name> <collection>` | Scaffold a new RabbitMQ processor with consumer, DLQ, metrics |
| `/proto-sync [proto-file]` | Regenerate Python gRPC stubs from protos/ and check for breaking changes |
| `docker-expert` | Docker troubleshooting, optimization, and security for 90+ Dockerfiles |

### Hooks (`settings.json`)

| Event | Hook | Purpose |
|-------|------|---------|
| `PreToolUse` (Bash) | `secret-scanner.py` | Block commits containing hardcoded secrets (60+ patterns) |
| `PreToolUse` (Bash) | `dangerous-command-blocker.py` | Block catastrophic commands (rm -rf /, dd, mkfs) and protect critical paths |
| `PreToolUse` (Bash) | force-push-blocker (inline) | Block `git push --force` and `git push -f` |
| `PreToolUse` (Bash) | `conventional-commits.py` | Validate commit messages follow Conventional Commits format |
| `PreToolUse` (Edit/Write) | `tdd-gate.sh` | Block production code edits if no corresponding test file exists |
| `PreToolUse` (Edit/Write/MultiEdit/NotebookEdit) | `inject-lessons.py` | Inject category-matched prior lessons before each code edit. Silent no-op when no lessons file exists. |
| `PostToolUse` (Edit) | format-python (inline) | Auto-format Python files after edits (black/ruff, graceful fallback) |
| `Stop` | auto-review (prompt) | Check if CLAUDE.md needs updating + self-review modified code |
| `Stop` | `scope-guard.sh` | Warn if files modified outside declared spec scope |

### Plugins

| Plugin | Source | Purpose |
|--------|--------|---------|
| `superpowers` | `claude-plugins-official` | Structured development workflow: brainstorming, plan writing, TDD, subagent orchestration, verification-before-completion |

**Superpowers vs. project commands — when to use which:**

| Task | Use project command | Use superpowers skill |
|------|--------------------|-----------------------|
| Plan a task | `/plan` (lightweight, quick) | `writing-plans` (heavyweight, multi-step spec with review) |
| Debug an error | `@debugger` (structured fix plan) | `systematic-debugging` (exhaustive hypothesis testing) |
| Review code | `@code-reviewer` (7-dimension single-pass) | `requesting-code-review` (formal review with verification gates) |
| Write tests | `@test-writer` (stack-agnostic generation) | `test-driven-development` (strict red-green-refactor TDD) |
| Execute a plan | Direct implementation | `executing-plans` (subagent delegation with checkpoints) |

**Rule of thumb:** Use project commands for focused, day-to-day tasks. Use superpowers skills for complex, multi-step work that benefits from structured gates and verification.

**Note:** Project commands already integrate key superpowers principles (verification evidence, no-placeholder plans, root-cause-first debugging, TDD integration, anti-rationalization checks). You get the best of both by default when using project commands.

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

## graphify

This project has a **unified graphify knowledge graph** at `graphify-out/` covering libs + protos + tools + model-optimizer + docs + any merged-in services (crawler-service today; more added via `/graphify <service> --update`). 1700 nodes, ~3150 edges, 86 communities, with explicit cross-service edges (e.g. `crawler_capacity_counter --uses--> cache_service.py`).

Rules:
- Before answering architecture or codebase questions, read `graphify-out/GRAPH_REPORT.md` for god nodes, community structure, and suggested questions.
- For cross-module "how does X relate to Y" questions, prefer the `/graphify query "<question>"`, `/graphify path "<A>" "<B>"`, or `/graphify explain "<concept>"` slash commands over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files.
- After modifying code files in this session, run `/graphify --update` (the slash command inside this session, NOT the `graphify update .` CLI). The slash command uses the scoped manifest and re-extracts only changed files; the CLI rescans the whole directory and in this monorepo that pulls in `apps-microservices/` and explodes the graph.
- For autonomous per-commit rebuilds: run `bash scripts/install-graphify-hook.sh` once per clone. The scoped post-commit hook derives the in-scope file set from `graphify-out/graph.json` (tracked, so every teammate gets the right scope right after `git pull`), runs AST only on in-scope changes, and never calls the LLM. Commits outside scope are silently ignored.
- Remember edge honesty tags: EXTRACTED (AST-sourced, trust fully), INFERRED (LLM-reasoned, verify before refactoring shared components), AMBIGUOUS (flagged, verify). INFERRED edges may also have flipped direction — the graph is undirected, so interpret bidirectionally.
- Do NOT run `graphify hook install` from the upstream CLI — it installs an unscoped hook that explodes the graph. Use `scripts/install-graphify-hook.sh` instead. See `docs/graphify-guide-en.md` § "Scoped hook vs. upstream hook" for the reason.
- Full team guide: `docs/graphify-guide-en.md` (English) or `docs/graphify-guide-fr.md` (Français).
