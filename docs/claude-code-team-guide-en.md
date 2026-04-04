# Claude Code Team Guide — RAG-HP-PUB

> **Version:** 2.0 — April 2026
> **Audience:** All developers working on the RAG-HP-PUB platform
> **Prerequisite:** Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Quick Start](#2-quick-start)
3. [Available Commands (/commands)](#3-available-commands-commands)
4. [Available Agents (@agents)](#4-available-agents-agents)
5. [Rules (.claude/rules/)](#5-rules-clauderules)
6. [Standardized Daily Workflow](#6-standardized-daily-workflow)
7. [Multi-Service Work](#7-multi-service-work)
8. [Remote-Only Services: Absolute Rules](#8-remote-only-services-absolute-rules)
9. [Team Harmonization](#9-team-harmonization)
10. [CLAUDE.md System Maintenance](#10-claudemd-system-maintenance)
11. [Common Mistakes to Avoid](#11-common-mistakes-to-avoid)
12. [Advanced Tips](#12-advanced-tips)
13. [New Team Member Checklist](#13-new-team-member-checklist)
14. [Quick Reference (Cheat Sheet)](#14-quick-reference-cheat-sheet)

---

## 1. Introduction

### What Is Claude Code?

Claude Code is Anthropic's official CLI for Claude. It operates directly in your terminal, reads your codebase, runs commands, edits files, and maintains a persistent memory of project conventions. Unlike a generic chatbot, Claude Code understands the project it is working in because it reads configuration files that tell it what the project is, how to behave, and what to avoid.

On RAG-HP-PUB — a platform of 90+ microservices spanning Python, Rust, TypeScript, and Go — Claude Code is the team's primary AI-assisted development tool. It enforces consistent code style, generates bilingual commit messages, reviews code, debugs issues, and writes documentation, all while respecting the constraints of our remote-only infrastructure.

### How the Memory System Works

Claude Code's behavior is governed by a layered configuration system:

| Layer | File | Scope | Checked into Git? |
|-------|------|-------|--------------------|
| **Project root** | `CLAUDE.md` at repo root | All team members, all services | Yes |
| **Project rules** | `.claude/rules/*.md` | Automatic rules loaded every session | Yes |
| **Project agents** | `.claude/agents/*.md` | Specialized sub-agents (review, debug, doc) | Yes |
| **Project commands** | `.claude/commands/*.md` | Slash commands (`/plan`, `/commit-msg`, etc.) | Yes |
| **Service-level** | `apps-microservices/<service>/CLAUDE.md` | One specific microservice | Yes |
| **Personal global** | `~/.claude/CLAUDE.md` | Your personal preferences (all projects) | No |
| **Session primer** | `~/.claude/primer.md` | Session continuity between restarts | No |

Claude Code reads these files at session start and follows them as instructions. The project-level files ensure team consistency; the personal files let each developer customize their experience.

### Our Configuration at a Glance

**4 agents:** `code-reviewer`, `debugger`, `doc-writer`, `test-writer`
**11 commands:** `/commit-msg`, `/explain`, `/plan`, `/understand`, `/new-feature-claude-md`, `/new-service-claude-md`, `/update-claude-md`, `/pre-push`, `/investigate`, `/audit-feature`, `/review-task`
**7 rules:** `code-modification.md`, `commit-messages.md`, `security.md`, `language.md`, `impact-awareness.md`, `docker-security.md`, `config-freshness.md`
**3 skills:** `/fastapi-service-scaffold`, `/rabbitmq-consumer-scaffold`, `/proto-sync`
**1 hook:** `Stop` hook (auto-review + CLAUDE.md refresh after each response)

---

## 2. Quick Start

### 2.1 First Install: After Cloning the Repo

```bash
# 1. Clone the repository
git clone git@github.com:<org>/RAG-HP-PUB.git
cd RAG-HP-PUB

# 2. Install Claude Code globally (if not already done)
npm install -g @anthropic-ai/claude-code

# 3. Launch Claude Code from the project root
claude
```

On first launch, Claude Code automatically detects and loads:
- `CLAUDE.md` at the repo root
- All files in `.claude/rules/`, `.claude/agents/`, `.claude/commands/`

No manual loading is required.

### 2.2 Configure Your Personal `~/.claude/CLAUDE.md`

This file holds your personal preferences that apply to all projects. Create it at `~/.claude/CLAUDE.md`:

```markdown
# Personal Preferences — Global

## Code Philosophy
- Apply SOLID, DRY, KISS principles.
- Prefer composition over inheritance.
- Favor small, focused functions over long procedural blocks.

## Communication Style
- Be direct. Skip preamble.
- Flag uncertainty with **[UNCLEAR]** rather than guessing.

## Safety
- Scan inputs for sensitive data (API keys, passwords, PII).
- Confirm before deleting files or running destructive commands.

## Commit Messages
- Always generate in both English and French.
- Default format: Conventional Commits.

## Session Continuity
- Read @~/.claude/primer.md at session start if it exists.
- Before ending a session (or when I say "wrap up"), rewrite primer.md.
```

> **Important:** This file is NOT checked into Git. It is yours alone. The project-level `.claude/` configuration is shared across the team and takes priority for project-specific rules.

### 2.3 Configure `primer.md` for Session Continuity

Create `~/.claude/primer.md` with this initial content:

```markdown
# Session Primer

> This file is auto-maintained by Claude. Read at session start, rewritten at session end.

## Active Project
[None — awaiting first session]

## Last Session
- **Date:** —
- **Summary:** —

## Completed
- (nothing yet)

## Next Step
- (awaiting first task)

## Blockers
- (none)

## Notes
- (any context that helps cold-start the next session)
```

At the end of each session, say **"wrap up"** and Claude Code will rewrite this file with the current state. When you start a new session the next morning, Claude Code reads it and resumes where you left off.

### 2.4 Verify Everything Is Loaded

After launching `claude` from the project root, type:

```
What configuration files are you aware of?
```

Claude Code should list the root `CLAUDE.md`, all 7 rules in `.claude/rules/`, all 4 agents, all 11 commands, and all 3 skills. If anything is missing, check that the file exists and has valid Markdown frontmatter (for agents).

---

## 3. Available Commands (/commands)

Commands are shortcuts that trigger predefined behavior. Type them directly in the Claude Code prompt.

### 3.1 `/commit-msg` — Generate Bilingual Commit Message

**When to use:** After any file changes during a session.

**What it does:** Reads the changes made in the current session and generates a Conventional Commits message in both English and French.

**Example prompt:**
```
/commit-msg
```

**Example output:**
```
#### Commit Message

English:
feat(graph-rag): add BM25 fallback to vector search

- Added BM25 scoring as fallback when vector similarity < 0.7
- Updated search pipeline in graph-rag-api-recherche-rust-service

French:
feat(graph-rag): ajout du fallback BM25 pour la recherche vectorielle

- Ajout du scoring BM25 en fallback quand la similarité vectorielle < 0.7
- Mise à jour du pipeline de recherche dans graph-rag-api-recherche-rust-service
```

> If no file changes were made, Claude Code responds: *"No file changes detected in this session."*

### 3.2 `/explain` — Code Explanation

**When to use:** When you encounter unfamiliar code and need to understand it without modifying or critiquing it.

**Example prompt:**
```
/explain apps-microservices/graph-rag-api-recherche-rust-service/src/reranking.rs
```

**What it does:** Provides a plain-language explanation of the file's purpose, key components, and non-obvious logic. Ends with: *"Is there a specific part you would like me to go deeper on?"*

**Rules:** Does NOT critique, suggest improvements, or output code.

### 3.3 `/plan` — Interactive Planning

**When to use:** Before starting any task that involves multiple files or services. Always plan before coding complex features.

**Example prompt:**
```
/plan Add a circuit breaker to the gRPC calls between api-gateway and embedding-model-service
```

**Example prompt with file details:**
```
/plan with file details Add WebSocket support to api-chatbot-html-service for real-time streaming
```

**What it does:**
1. Restates the goal in one sentence.
2. Lists the steps to take.
3. If "with file details" is included, provides a table of files to CREATE, UPDATE, or DELETE.
4. Ends with: *"Does this align with what you are looking for? Please confirm to proceed."*

**Rules:** Does NOT generate any code until you explicitly confirm.

### 3.4 `/understand` — Content Comprehension

**When to use:** When you upload or paste content (architecture docs, API specs, error logs) and want Claude Code to absorb it before you ask questions.

**Example prompt:**
```
/understand [paste RabbitMQ exchange topology diagram or upload a PDF]
```

**What it does:** Reads and analyzes the content thoroughly, then provides a detailed summary of purpose, key components, and constraints. Ends with: *"What would you like to discuss or work on next?"*

### 3.5 `/new-feature-claude-md` — Update CLAUDE.md After a Feature Addition

**When to use:** After adding a significant feature to an existing service (new module, new external dependency, structural change, new commands).

**When NOT to use:** For minor changes like bug fixes, small refactors, or adding a single endpoint.

**Example prompt:**
```
/new-feature-claude-md
```

Claude Code will ask:
- Which service?
- What was added?

Then it scans the service directory, proposes surgical edits to the service's `CLAUDE.md`, and shows a diff preview before applying.

### 3.6 `/new-service-claude-md` — Generate CLAUDE.md for a New Service

**When to use:** When a brand-new microservice has been added to `apps-microservices/`.

**Example prompt:**
```
/new-service-claude-md
```

Claude Code will ask for the service name, path, and whether it runs locally or is remote-only. It then scans the directory and generates a `CLAUDE.md` following the standard template (under 60 lines). It also updates the root `CLAUDE.md` service map.

### 3.7 `/update-claude-md` — Propose Surgical CLAUDE.md Updates

**When to use:** In three situations:
- **(a)** Claude made a mistake you want to prevent in the future.
- **(b)** Something changed in the project (new dependency, restructure, convention change).
- **(c)** You want to rescan a service and refresh its CLAUDE.md.

**Example prompt:**
```
/update-claude-md
```

Claude Code asks you to pick (a), (b), or (c), then proposes minimal edits — never a full rewrite — and shows a diff before applying. Files are kept under 80 lines; if they exceed that limit, Claude Code suggests extracting rules to `.claude/rules/`.

### 3.8 `/pre-push` — Pre-Push Verification Checklist

**When to use:** Before pushing code to the remote repository. This command runs a complete checklist on all modified services.

**What it does:**
1. Identifies modified files and groups them by service
2. Runs per-language checks:
   - **Python:** Syntax compilation, import verification, pytest (if tests exist)
   - **Rust:** `cargo check`, `cargo test` (if tests exist)
   - **TypeScript/Node.js:** Lint and test scripts (if defined in package.json)
   - **Shared libraries (`libs/`):** Syntax check + downstream impact warning
3. Runs `@code-reviewer` on all changed files
4. Displays a summary table with each service's status

**Example prompt:**
```
/pre-push
```

**Example output:**
```
| Service              | Syntax | Tests | Review | Status |
|----------------------|--------|-------|--------|--------|
| api-gateway          | ✅     | ✅    | ✅     | OK     |
| graph-rag-etl        | ✅     | ⚠️    | ✅     | Warn   |

All checks passed. Safe to push.
```

> **Rule:** If tests are missing for a service, the command suggests using `@test-writer` to generate them.

### 3.9 `/investigate` — Evidence-Based Statement Verification

**When to use:** When you need to verify a claim about the codebase (e.g., "Do all services have health checks?" or "Is Redis only used by crawlers?").

**Example prompt:**
```
/investigate All processor services use DLQ headers
```

**What it does:**
1. Parses the claim into a testable assertion.
2. Searches the entire codebase exhaustively (not just a sample).
3. Produces a verdict: **CONFIRMED**, **PARTIALLY TRUE**, **FALSE**, or **INCONCLUSIVE** — with file:line evidence.

**Rules:** Read-only. Does NOT modify any files.

### 3.10 `/audit-feature` — End-to-End Feature Audit

**When to use:** When you want to trace a feature across the entire microservice pipeline and audit every service involved.

**Example prompt:**
```
/audit-feature product search
```

**What it does:**
1. Maps the feature flow (API entry → message queue → processor → database → response).
2. Audits each service for code quality, security, Docker compliance, test coverage, and CLAUDE.md accuracy.
3. Reports cross-service findings (inconsistent schemas, missing error propagation).
4. Ends with: *"Would you like me to fix any of these findings?"*

### 3.11 `/review-task` — Tech Lead Task Review

**When to use:** When reviewing a developer's completed work or auditing the current state of a service.

**Example prompt:**
```
/review-task apps-microservices/QC-tracking-service
```

**What it does:**
1. Reads the full service state (code, config, Dockerfile, tests, CLAUDE.md).
2. If branch changes exist, also analyzes the diff to highlight what was introduced.
3. Reviews against all 7 dimensions: code quality, security, Docker, impact, test coverage, CLAUDE.md accuracy, acceptance criteria.
4. Produces a verdict: **APPROVED**, **CHANGES REQUESTED**, or **BLOCKED**.

### 3.12 Skills (Scaffolding)

Skills generate entire service structures following project conventions. They live in `.claude/skills/`.

| Skill | Usage | Purpose |
|-------|-------|---------|
| `/fastapi-service-scaffold` | `/fastapi-service-scaffold my-service "Description"` | Scaffold a new FastAPI service (main.py, Dockerfile, tests, CLAUDE.md) |
| `/rabbitmq-consumer-scaffold` | `/rabbitmq-consumer-scaffold my-processor products` | Scaffold a RabbitMQ processor with consumer, DLQ, metrics |
| `/proto-sync` | `/proto-sync` or `/proto-sync embedding.proto` | Regenerate Python gRPC stubs and check for breaking changes |

---

## 4. Available Agents (@agents)

Agents are specialized sub-agents that Claude Code can delegate tasks to. They run in a focused mode with limited tools and a specific role. You trigger them by referencing their name or by describing a task that matches their scope.

### 4.1 `code-reviewer` — Code Quality & Security Review

**Model:** Sonnet
**Tools:** Read, Glob, Grep (read-only — cannot modify files)

**When to use:**
- Before opening a PR
- After completing a feature
- When auditing unfamiliar code

**Example prompt:**
```
Review the code in apps-microservices/QC-tracking-service/src/
```

**What it does:**
1. Analyzes code against 7 dimensions: SOLID, DRY, KISS, security, performance, error handling, and **impact awareness** (trade-offs, shared component blast radius).
2. Performs **multiple internal passes** (structure → security → performance → impact) before producing output — all findings in one response.
3. Groups findings by severity: Red (Critical) > Yellow (Warning) > Blue (Suggestion).
4. References specific lines and functions.
5. Ends with an **Impact Summary** paragraph and: *"Would you like me to implement any of these suggested improvements?"*

**Rules:** Does NOT generate fixed code or modify files. You must confirm which improvements to apply. The reviewer is designed to be **exhaustive in a single pass** — running it again on unchanged code should not produce new findings.

### 4.2 `debugger` — Error Diagnosis & Root Cause Analysis

**Model:** Sonnet
**Tools:** Read, Bash, Glob, Grep

**When to use:**
- When you have a stack trace or error log
- When a service behaves unexpectedly
- When a test fails and the reason is not obvious

**Example prompt:**
```
Debug this error from graph-rag-api-recherche-rust-service:
thread 'main' panicked at 'index out of bounds: the len is 0 but the index is 0'
```

**What it does:**
1. Reads the actual source file (never assumes from memory).
2. Explains WHY the error occurs, not just what it is.
3. If multiple causes are possible, ranks them by likelihood.
4. Produces a **structured fix plan** with a table of changes, trade-off analysis, and blast radius check.
5. Asks: *"Does this fix plan look correct? Confirm to apply."*
6. On confirmation, applies all changes and verifies the fix (py_compile, tests if available).

**Rules:** Does NOT apply fixes until you confirm. Follows `impact-awareness.md` for trade-off and downstream impact analysis.

### 4.3 `doc-writer` — Documentation Specialist

**Model:** Sonnet
**Tools:** Read, Write, Edit, Glob, Grep

**When to use:**
- When a file has no docstrings or JSDoc comments
- When onboarding a new team member to a service
- After a major refactor that invalidated existing comments

**Example prompt:**
```
Document all functions in apps-microservices/crawler-service/src/crawler.ts
```

**What it does:**
1. Adds file-level descriptions, function/method docs (purpose, params, returns, errors), and inline comments for non-obvious logic.
2. Uses the language's standard format: Python docstrings, JSDoc for TypeScript, Rust `///` doc comments.
3. Outputs the fully documented file.

**Rules:** NEVER modifies executable code. Only adds or updates comments/documentation.

### 4.4 `test-writer` — Test Suite Generator

**Model:** Sonnet
**Tools:** Read, Write, Edit, Glob, Grep

**When to use:**
- When a service has no tests (69/91 services currently lack tests)
- When you want to increase test coverage for an existing service
- When `/pre-push` flags missing tests for a modified service

**Example prompt:**
```
Write tests for apps-microservices/QC-tracking-service/
```

**What it does:**
1. **Auto-detects the stack** by reading the service directory:
   - `requirements.txt` / `pyproject.toml` → Python (pytest)
   - `Cargo.toml` → Rust (cargo test)
   - `package.json` → Node.js (Jest or Vitest)
   - Unknown → asks the user which framework to use
2. Reads the service source code (endpoints, schemas, business logic).
3. Looks for existing test files to reuse fixtures and patterns.
4. Generates test files appropriate for the detected stack.

**Python test patterns:**
- `httpx.AsyncClient` for FastAPI endpoint tests
- Mock all external dependencies (RabbitMQ, gRPC, Milvus, Redis)
- `pytest.mark.asyncio` for async tests
- Descriptive naming: `test_<action>_<condition>_<expected_result>`

**Rules:**
- NEVER modifies existing source code — only creates/edits test files.
- NEVER generates tests that require live connections to databases or queues.
- After writing tests, suggests the appropriate run command for the detected stack.

### When NOT to Use an Agent

- Do not trigger `code-reviewer` for a quick one-line fix — just ask Claude directly.
- Do not trigger `debugger` if you already know the fix — just describe the change.
- Do not trigger `doc-writer` for a single function — ask Claude Code directly to add a docstring.
- Do not trigger `test-writer` for a single trivial unit test — write it directly with Claude.

Agents have their own context window. Use them for substantial tasks where their specialization adds value.

---

## 5. Rules (.claude/rules/)

### 5.1 `code-modification.md` — The Surgical Edit Protocol

**Location:** `.claude/rules/code-modification.md`

This rule ensures that Claude Code behaves like a **patch tool**, not a rewriter:

1. **Read first.** Always read the current file from disk before editing.
2. **Minimal diff.** Change only what the task requires.
3. **Preserve formatting.** Keep original indentation, line structure, and style.
4. **Preserve comments.** Never remove comments unless a code change makes one factually incorrect.
5. **Verify after.** Run typecheck/lint after the edit.

Every code block in Claude Code's output is preceded by the full file path as a header. For partial edits, surrounding context is marked with `// ... existing code ...`.

### 5.2 `commit-messages.md` — Bilingual Conventional Commits

**Location:** `.claude/rules/commit-messages.md`

This rule defines how commit messages are generated:

- Format: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`)
- Always bilingual: English + French
- Scope limited to changes made in the current response only
- Subject line under 72 characters

### 5.3 `security.md` — Security Rules

**Location:** `.claude/rules/security.md`

This rule enforces security best practices across the entire project:

1. **Secrets & URLs** — NEVER hardcode service URLs, API keys, or connection strings. All must come from environment variables via Pydantic `BaseSettings`.
2. **CORS** — `allow_origins=["*"]` is acceptable for internal services behind the API gateway. Public-facing services (`api-gateway`, `api-html-recherche`) must restrict origins.
3. **JWT & Authentication** — JWT secrets must be set via environment variables, never default values like "changeme-jwt-secret".
4. **Input Validation** — Use Pydantic models for ALL request validation. Sanitize data before passing to LLM prompts (prompt injection prevention).
5. **Logging** — Sensitive headers (`authorization`, `cookie`, `x-api-key`) must be redacted in logs.

### 5.4 `language.md` — Language Rules

**Location:** `.claude/rules/language.md`

This rule defines Claude Code's linguistic behavior:

1. **Response language** — Claude responds in the same language the user writes in (French if user writes French, English if English).
2. **Code identifiers** — Always in English, regardless of conversation language.
3. **Code comments** — Follow the conversation language (French comments for French users, English for English users).
4. **Commit messages** — Always generated in BOTH English and French.
5. **CLAUDE.md files** — Written in English for maximum instruction adherence.

### 5.5 `impact-awareness.md` — Trade-Off & Blast Radius Analysis

**Location:** `.claude/rules/impact-awareness.md`

This rule requires analyzing trade-offs BEFORE every code modification:

1. **Trade-off analysis** — State what the change gains vs. what it costs (complexity, dependencies, breaking changes).
2. **Bigger picture** — Understand the service's role in the pipeline, check if the same pattern exists in other services.
3. **Blast radius** — For shared components (`libs/`, `protos/`, `docker-compose.yml`), list all downstream consumers and assess if the change is backward-compatible or breaking.

### 5.6 `docker-security.md` — Docker Security Rules

**Location:** `.claude/rules/docker-security.md`

This rule enforces Docker best practices for all Dockerfiles and docker-compose.yml:

1. **Base images** — Always pin versions (no `latest` tag), no EOL images, prefer `-slim` variants.
2. **Build** — Use `--no-cache-dir` on pip install, multi-stage builds, COPY only what is needed.
3. **Runtime** — No root user, no secrets in `ENV`, healthchecks required in compose.
4. **Vulnerability patterns** — Flag `chmod 777`, `ADD` instead of `COPY`, missing `.dockerignore`.

### 5.7 `config-freshness.md` — Configuration Freshness

**Location:** `.claude/rules/config-freshness.md`

This rule ensures Claude Code always works with the latest `.claude/` configuration, even mid-conversation:

1. Re-read agent/command files before invoking them.
2. After creating or updating any `.claude/` file, treat it as immediately active.
3. If a conflict exists between a stale in-context version and the file on disk, the file on disk wins.

### 5.8 `formatting.md` — Code Formatting Conventions

**Location:** `.claude/rules/formatting.md`

No project-wide formatter is enforced yet. This rule defines the conventions Claude must follow:

1. **Python**: 4-space indent, 88-char line length, double quotes, import ordering (stdlib → third-party → libs → local).
2. **Rust**: rustfmt defaults, 100-char line length, no `unwrap()` in production.
3. **JS/TS**: 2-space indent, semicolons required, single quotes.
4. **Universal**: Match the file's existing style. Never reformat outside the scope of your change.

### 5.9 `refactoring.md` — Refactoring Guidelines

**Location:** `.claude/rules/refactoring.md`

Governs when and how to refactor safely:

1. **When**: After reviewer flags duplication/SOLID violation, when logic exists in 3+ services, or user explicitly requests.
2. **When NOT**: During bug fixes, during feature additions, without tests, or unprompted.
3. **Shared components**: Always `/plan` first, list all downstream consumers, commit library changes separately.
4. **Known targets**: logging centralization (75 services), config duplication (45 services), structure standardization (15 services).

### How Rules Are Loaded

Rules in `.claude/rules/` are loaded **automatically** at every session start. You do not need to reference them explicitly. Claude Code reads them as part of its initialization.

### How to Add a New Rule

When Claude Code makes an error that should be prevented in the future:

1. **Diagnose:** Identify what went wrong and why.
2. **Draft the rule:** Write a clear, concise `.md` file.
3. **Place it:** Save to `.claude/rules/<rule-name>.md`.
4. **Commit it:** The rule is shared with the team via Git.

**Example: Claude kept importing a deprecated module.**

```bash
# Create the rule
cat > .claude/rules/deprecated-imports.md << 'EOF'
# Deprecated Imports

NEVER import from `libs/old_embeddings/`. This module is deprecated.
Use `libs/embedding_utils/` instead. The API is the same.
EOF

# Commit it
git add .claude/rules/deprecated-imports.md
git commit -m "chore(rules): add deprecated-imports rule to prevent old_embeddings usage"
```

From the next session onward, Claude Code will follow this rule automatically.

---

## 6. Standardized Daily Workflow

### 6.1 Session Start

```
1. Launch `claude` from the project root.
2. Claude Code reads CLAUDE.md, rules, and primer.md automatically.
3. Verify context: "What do you know about the current project state?"
4. If primer.md had a next step, pick up where you left off.
```

### 6.2 Before Coding

For any non-trivial task, start with `/plan`:

```
/plan with file details Add retry logic to RabbitMQ consumers in QC-tracking-service
```

Review the plan, confirm, then proceed. This prevents Claude Code from going in the wrong direction on a multi-file task.

**When to use Plan mode:**
- Multi-file changes
- Cross-service modifications
- New features or architectural changes
- Anything involving shared libraries in `libs/`

**When Normal mode is fine:**
- Single-file edits
- Bug fixes with a known root cause
- Adding a test for an existing function
- Documentation tasks

### 6.3 During Work

- After each significant change, run `/commit-msg` to capture progress.
- If a modified service has no tests, use `@test-writer` to generate a test suite.
- Before pushing, run `/pre-push` for the full verification checklist.
- If Claude Code's context is filling up (you notice slower responses or repeated mistakes), use `/compact` at **50-65% context usage** to summarize and free space.
- For code reviews before committing, trigger the `code-reviewer` agent.

### 6.4 Handling Remote-Only Services

For services that only run on the remote server (most Python/Rust microservices):

```
# You CAN do locally:
cargo check                                      # Rust type checking
pytest tests/ -m "not integration"               # Unit tests with mocks

# You CANNOT do locally:
python -m uvicorn main:app                       # No DB/queue access
docker-compose up <service>                      # No GPU, no infra
pytest tests/ -m integration                     # No live connections
```

See [Section 8](#8-remote-only-services-absolute-rules) for the full list.

### 6.5 Session End

When you are done for the day, say:

```
wrap up
```

Claude Code will rewrite `~/.claude/primer.md` with:
- What was completed
- The exact next step
- Any blockers encountered

### 6.6 Code Review Cycle

```
1. Complete your changes.
2. Trigger code-reviewer: "Review the changes in apps-microservices/my-service/src/"
3. Read the findings (Critical > Warning > Suggestion).
4. Tell Claude Code which findings to fix: "Fix findings 1 and 3."
5. Run /commit-msg to generate the final commit message.
```

---

## 7. Multi-Service Work

### 7.1 Working Across Multiple Microservices

RAG-HP-PUB has 90+ services. Many tasks touch multiple services simultaneously: a new proto definition affects every service that imports it, a shared lib change ripples across dozens of consumers.

**Approach:**
1. Start with `/plan with file details` to map all affected files.
2. Work on one service at a time. Commit after each service.
3. Use the service-level `CLAUDE.md` to understand each service's conventions before editing.

### 7.2 When to Use Parallel Sub-Agents

Use sub-agents when you need to explore multiple directories without polluting your main context:

```
Use a sub-agent to analyze the folder structure and dependencies of:
1. apps-microservices/api-gateway/
2. apps-microservices/embedding-model-service/
3. libs/grpc_utils/
```

This keeps your main conversation focused on the task while the sub-agents gather information in parallel.

**Use sub-agents for:**
- Scanning multiple services for a pattern
- Comparing implementations across services
- Understanding dependency chains

### 7.3 Shared Libraries (`libs/`)

Changes to shared libraries are high-impact. Always follow this protocol:

1. **Identify consumers:** Search for imports of the library across all services.
2. **Plan the change:** Use `/plan` with the full list of affected services.
3. **Make the library change first.** Verify with type checking.
4. **Update consumers one by one.** Test each.
5. **Commit atomically:** One commit for the library change, one per affected service.

**Example:**
```
Search for all services that import from libs/embedding_utils/
```

### 7.4 Concrete Example: Auth + Gateway + ML Pipeline

Scenario: Adding an API key validation layer that spans three services.

```
/plan with file details
Add API key validation:
1. New middleware in api-gateway (port 8500) that checks X-API-Key header
2. New validation endpoint in auth-service
3. Update embedding-model-service gRPC client to forward API key metadata
```

After confirmation:
```
Step 1: Work on api-gateway
Step 2: Work on auth-service
Step 3: Update protos/grpc_stubs/ if needed
Step 4: Update embedding-model-service gRPC client
Step 5: /commit-msg for each step
```

---

## 8. Remote-Only Services: Absolute Rules

### 8.1 Why Most Services Are Remote-Only

The RAG-HP-PUB platform depends on GPU hardware, production databases (Neo4j, Milvus, Qdrant), message queues (RabbitMQ), and cache layers (Redis). These are only available on the remote deployment server. Most microservices cannot function locally.

### 8.2 Remote-Only Services

All Python/FastAPI services in `apps-microservices/` that depend on:
- **GPU:** `vllm-server`, `triton-server`, `embedding-model-service`, `reranking-model-service`
- **Databases:** Any service connecting to Neo4j, Milvus, Qdrant, Redis, Elasticsearch
- **Message queues:** Any service consuming/publishing to RabbitMQ
- **gRPC backends:** Any service calling GPU-dependent gRPC endpoints (port 50052, etc.)

### 8.3 What CAN Be Done Locally

| Action | Command | Notes |
|--------|---------|-------|
| Python type checking | [TODO: to be filled — Python type checker to be decided by the team] | |
| Rust type checking | `cd apps-microservices/graph-rag-api-recherche-rust-service && cargo check` | |
| Unit tests (mocked) | `pytest tests/ -m "not integration"` | Only with mocked dependencies |
| Lint TypeScript | `cd apps-microservices/<ts-service> && npm run lint` | |
| Read and analyze code | Use Claude Code's Read, Glob, Grep tools | No execution needed |
| Generate documentation | Use `doc-writer` agent | Read-only analysis |
| Code review | Use `code-reviewer` agent | Read-only analysis |

### 8.4 What CANNOT Be Done Locally

| Action | Why |
|--------|-----|
| Start a Python microservice (`uvicorn`, `python main.py`) | No DB/queue/GPU access |
| Run `docker-compose up` for backend services | No GPU, no infra network |
| Run integration tests | No live connections to Neo4j, Milvus, RabbitMQ |
| Connect to production databases | Credentials and network not available locally |
| Run model inference | No GPU hardware |

### 8.5 Commands to NEVER Run Locally

```bash
# NEVER run these for remote-only services:
python -m uvicorn main:app --reload          # Will fail — no DB connections
docker-compose up <backend-service>          # Will fail — no GPU/infra
pytest tests/integration/                    # Will fail — no live services
python -c "from neo4j import GraphDatabase"  # Will hang — no Neo4j server
```

> **Rule of thumb:** If a command needs a network connection to a database, queue, or GPU, it will not work locally. Stick to static analysis: type checking, linting, unit tests with mocks.

### 8.6 Services That CAN Run Locally

| Service | Type | Port |
|---------|------|------|
| `api-chatbot-html-service` | Next.js frontend | 3000 |
| `nextjs-formulaire-hp` | Next.js frontend | 3000 (basePath: `/formulaire`) |
| `crawler-monitor-frontend` | Frontend | [TODO: to be filled by the team] |
| `crawler-service` | Node.js/Crawlee | 8503 |
| Shared libraries (`libs/`) | Python/TS packages | N/A (importable) |

---

## 9. Team Harmonization

### 9.1 Naming Conventions by Language

| Language | Files | Functions | Classes | Constants |
|----------|-------|-----------|---------|-----------|
| Python | `snake_case.py` | `snake_case()` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Rust | `snake_case.rs` | `snake_case()` | `PascalCase` | `UPPER_SNAKE_CASE` |
| TypeScript | `kebab-case.ts` or `camelCase.ts` | `camelCase()` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Go | `snake_case.go` | `PascalCase()` (exported) / `camelCase()` (unexported) | `PascalCase` | `PascalCase` or `camelCase` |
| Proto | `snake_case.proto` | `PascalCase` (service/message) | — | — |

### 9.2 Code Style by Service Type

**Python/FastAPI services:**
- Type hints on all function signatures
- Pydantic models for request/response validation
- Async handlers where I/O is involved (`async def`)
- Type checking: [TODO: Python type checker to be decided by the team]

**Rust/Actix-web services:**
- Strong typing, no `unwrap()` in production code
- `Result<T, E>` for error propagation
- Type checking: `cargo check`

**TypeScript/Next.js services:**
- Strict TypeScript (`strict: true` in `tsconfig.json`)
- React functional components with hooks
- ESLint + Prettier for formatting

**Go extractors:**
- Standard `go fmt` formatting
- Error returns (no panic in production)
- `go vet` for static analysis

### 9.3 Git Conventions

**Branch naming:**
```
features/<feature-name>       # New features
fix/<bug-description>         # Bug fixes
refactor/<scope>              # Refactoring
chore/<task>                  # Maintenance tasks
docs/<topic>                  # Documentation
```

**Commit format:** Conventional Commits, always bilingual (EN + FR). Generated via `/commit-msg`.

**Pull requests:**
- Title: Conventional Commit format, under 72 characters
- Body: Summary of changes, test plan, link to related issues
- Review: Run `code-reviewer` agent before opening the PR

### 9.4 Project CLAUDE.md vs Personal `~/.claude/CLAUDE.md`

| Aspect | Project `.claude/` | Personal `~/.claude/CLAUDE.md` |
|--------|--------------------|--------------------------------|
| Scope | This project only | All your projects |
| Checked into Git | Yes | No |
| Who maintains it | The team | You alone |
| Content | Project rules, agents, commands | Communication preferences, shortcuts |
| Priority | Project rules override personal preferences for project-specific behavior | Personal preferences apply when project rules are silent |

**Rule:** Never put project-specific rules in your personal config. If a rule applies to RAG-HP-PUB, it goes in `.claude/rules/` or the root `CLAUDE.md`.

---

## 10. CLAUDE.md System Maintenance

### 10.1 When to Update

- After adding a new microservice → `/new-service-claude-md`
- After adding a significant feature to an existing service → `/new-feature-claude-md`
- After Claude Code makes a preventable mistake → `/update-claude-md` (option a)
- After a project change (new dependency, restructure) → `/update-claude-md` (option b)
- Weekly, as part of routine maintenance → `/update-claude-md` (option c: rescan)

### 10.2 How to Update: Surgical Edits Only

CLAUDE.md files are NEVER rewritten from scratch unless explicitly requested. All updates follow the surgical edit protocol:

1. Read the current file.
2. Identify the exact lines to add, remove, or modify.
3. Show a diff preview.
4. Apply only after confirmation.

### 10.3 Dedicated Commands

| Situation | Command |
|-----------|---------|
| New service added | `/new-service-claude-md` |
| Significant feature added to existing service | `/new-feature-claude-md` |
| Mistake prevention, project change, or rescan | `/update-claude-md` |

### 10.4 Weekly Review

Once a week, pick 2-3 services and run:

```
/update-claude-md
> (c) I just want you to rescan this service and refresh its CLAUDE.md.
```

This catches drift between the code and its documentation.

### 10.5 The 80-Line Rule

Every `CLAUDE.md` file must stay under **80 lines**. If an update would push it over 80 lines:

1. Identify detailed sections that can be extracted.
2. Move them to `.claude/rules/<topic>.md`.
3. Add a reference in the `CLAUDE.md`: `See .claude/rules/<topic>.md for details.`

This keeps CLAUDE.md files scannable and fast to load.

---

## 11. Common Mistakes to Avoid

> These are real mistakes that have occurred or are likely to occur on this project. Each one wastes time or causes confusion.

- **Mistake 1:** Trying to run a Python microservice locally (`uvicorn main:app`) when it requires Neo4j, Milvus, or RabbitMQ. Stick to type checking and mocked unit tests.

- **Mistake 2:** Editing a shared library in `libs/` without checking which services import it. Always search for consumers first: `grep -r "from libs/<name>" apps-microservices/`.

- **Mistake 3:** Letting Claude Code rewrite an entire file when only 3 lines needed to change. The `code-modification.md` rule exists for this reason — enforce minimal diffs.

- **Mistake 4:** Forgetting to say "wrap up" at end of session. Your `primer.md` will be stale the next morning and Claude Code will lose context of where you left off.

- **Mistake 5:** Putting project-specific rules in `~/.claude/CLAUDE.md` instead of `.claude/rules/`. Personal config is not shared with the team — the rule will only work for you.

- **Mistake 6:** Skipping `/plan` on multi-service tasks. Without a plan, Claude Code may edit files in the wrong order, miss dependencies, or go in the wrong direction entirely.

- **Mistake 7:** Waiting until 90% context usage to `/compact`. By then, Claude Code has already lost accuracy. Compact at **50-65%** for best results.

- **Mistake 8:** Committing a CLAUDE.md that exceeds 80 lines. It becomes slow to scan and hard to maintain. Extract detailed rules into `.claude/rules/`.

- **Mistake 9:** Using the `code-reviewer` agent for a one-line typo fix. Agents have overhead — use them for substantial reviews, not trivial edits.

- **Mistake 10:** Running `docker-compose up` locally for GPU-dependent services like `vllm-server` or `triton-server`. These require hardware that does not exist on developer machines.

---

## 12. Advanced Tips

### 12.1 Pipe Mode

Send a single prompt to Claude Code without starting an interactive session:

```bash
echo "Explain the purpose of apps-microservices/api-gateway/main.py" | claude
```

Useful for:
- Quick one-off questions
- CI/CD integration (generating commit messages, running reviews)
- Scripting Claude Code into automation pipelines

### 12.2 Agent Mode for Exploration

When exploring an unfamiliar part of the codebase, ask Claude Code to use sub-agents to keep your main context clean:

```
Use a sub-agent to map all gRPC service definitions in protos/grpc_stubs/
and list which services implement each one.
```

The sub-agent explores, summarizes, and returns results without consuming your main context window.

### 12.3 Hooks

Claude Code hooks are configured in `.claude/settings.json`. They execute automatically in response to events.

**Currently configured:**

| Event | Hook Type | Purpose |
|-------|-----------|---------|
| `Stop` | `prompt` | After each response: (1) checks if any CLAUDE.md needs updating based on file changes, (2) self-reviews modified code for quality/security/impact awareness violations |

This means after every response where code was modified, Claude Code automatically checks its own work. If issues are found, it reports them and offers to fix.

**How to add a new hook:** Edit `.claude/settings.json` and add entries under the `hooks` key. See [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code) for the full hook API (PreToolUse, PostToolUse, Stop, etc.).

### 12.4 Superpowers Plugin

The project has the `superpowers` plugin installed project-wide. It provides 14 skills that enforce a structured development workflow: brainstorming before coding, plan writing, TDD, subagent orchestration, and verification-before-completion.

**When to use superpowers vs. project commands:**

| Task | Project command (lightweight) | Superpowers skill (heavyweight) |
|------|-------------------------------|----------------------------------|
| Plan a task | `/plan` | `writing-plans` (multi-step spec with formal review) |
| Debug an error | `@debugger` | `systematic-debugging` (exhaustive hypothesis testing) |
| Review code | `@code-reviewer` | `requesting-code-review` (formal review with verification gates) |
| Write tests | `@test-writer` | `test-driven-development` (strict red-green-refactor TDD) |
| Execute a plan | Direct implementation | `executing-plans` (subagent delegation with checkpoints) |

**Rule of thumb:** Use project commands for focused, day-to-day tasks. Use superpowers skills for complex, multi-step work that benefits from structured gates and verification.

### 12.4 The `primer.md` Pattern in Depth

The `primer.md` file acts as a "save state" for your Claude Code sessions. Here is how it works in practice:

**End of Monday session:**
```
wrap up
```

Claude Code writes:
```markdown
## Active Project
RAG-HP-PUB — QC-tracking-service

## Last Session
- **Date:** 2026-03-24
- **Summary:** Added retry logic to RabbitMQ consumer. Fixed deserialization bug.

## Completed
- Retry logic with exponential backoff (max 3 retries)
- Fixed Pydantic model for QC event payload

## Next Step
- Add unit tests for retry logic (mock aio_pika)

## Blockers
- No .env template for QC-tracking-service — need to ask DevOps for required vars
```

**Tuesday morning:** Launch `claude`. It reads this file and immediately knows the context.

### 12.5 Effective Context Management

Claude Code has a finite context window. Manage it deliberately:

| Context Usage | Action |
|---------------|--------|
| 0-50% | Work normally |
| 50-65% | Run `/compact` to summarize and free space |
| 65-80% | Must `/compact` — accuracy starts degrading |
| 80%+ | Start a new session. Context is too polluted for reliable work |

### 12.6 Using Claude Code for Proto Changes

When modifying `.proto` files in `protos/grpc_stubs/`:

1. Edit the `.proto` file.
2. Regenerate stubs (check the service's build instructions).
3. Update all services that import the modified stubs.
4. Type check each affected service.

Always use `/plan with file details` before touching proto files — the ripple effect can be significant.

---

## 13. New Team Member Checklist

Follow these steps in order on your first day:

1. **Clone the repository:**
   ```bash
   git clone git@github.com:<org>/RAG-HP-PUB.git
   cd RAG-HP-PUB
   ```

2. **Install Claude Code:**
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

3. **Create your personal config** at `~/.claude/CLAUDE.md` (see [Section 2.2](#22-configure-your-personal-claudeclaudemd)).

4. **Create your primer file** at `~/.claude/primer.md` (see [Section 2.3](#23-configure-primermd-for-session-continuity)).

5. **Launch Claude Code from the project root** and verify configuration:
   ```
   claude
   > What configuration files are you aware of?
   ```

6. **Read this guide** in its entirety — you are doing this step now.

7. **Explore a service** using `/explain`:
   ```
   /explain apps-microservices/api-gateway/main.py
   ```

8. **Try a planning workflow** with a low-risk task:
   ```
   /plan Add a docstring to all functions in apps-microservices/QC-tracking-service/src/main.py
   ```

9. **Run the code-reviewer agent** on a file you will be working on:
   ```
   Review apps-microservices/<your-assigned-service>/src/
   ```

10. **Try `@test-writer`** on a service without tests:
    ```
    Write tests for apps-microservices/<your-assigned-service>/
    ```

11. **Try `/pre-push`** before your first push to see the verification checklist.

12. **Make your first commit** using the bilingual workflow:
    ```
    # After making changes:
    /commit-msg
    ```

13. **End your first session** with "wrap up" to initialize your `primer.md`.

---

## 14. Quick Reference (Cheat Sheet)

### Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/commit-msg` | Generate bilingual commit message (EN/FR) | After any file changes |
| `/explain` | Explain a single file or code block | Understanding unfamiliar code |
| `/plan` | Interactive planning with step list | Before multi-file or multi-service tasks |
| `/understand` | Absorb and summarize multiple files/topics | When analyzing docs, specs, logs |
| `/new-feature-claude-md` | Update service CLAUDE.md after feature addition | After adding a significant feature |
| `/new-service-claude-md` | Generate CLAUDE.md for a new service | When a new microservice is created |
| `/update-claude-md` | Propose surgical CLAUDE.md updates | Mistake prevention, project changes, rescans |
| `/pre-push` | Pre-push verification checklist | Before every push |
| `/investigate` | Verify a statement about the codebase | Checking claims, auditing compliance |
| `/audit-feature` | End-to-end feature audit across pipeline | Feature quality assessment |
| `/review-task` | Tech Lead review (state + diff, verdict) | Reviewing dev work, service audits |

### Agents

| Agent | Model | Role | Tools |
|-------|-------|------|-------|
| `code-reviewer` | Sonnet | Code quality, security, SOLID/DRY/KISS, impact awareness (exhaustive single-pass) | Read, Glob, Grep |
| `debugger` | Sonnet | Root cause analysis → structured fix plan with trade-offs → apply | Read, Bash, Glob, Grep |
| `doc-writer` | Sonnet | Add documentation (English only) without modifying code | Read, Write, Edit, Glob, Grep |
| `test-writer` | Sonnet | Stack-agnostic test generation (Python/Rust/Node.js/unknown) | Read, Write, Edit, Glob, Grep |

### Rules

| Rule File | Purpose |
|-----------|---------|
| `.claude/rules/code-modification.md` | Surgical edit protocol: read first, minimal diff, preserve formatting, verify after |
| `.claude/rules/commit-messages.md` | Bilingual Conventional Commits, scope to current response, < 72 chars |
| `.claude/rules/security.md` | No hardcoded secrets/URLs, Pydantic BaseSettings, CORS (internal vs public), JWT, input validation, all infra connections |
| `.claude/rules/language.md` | Respond in user's language, bilingual commits, English code identifiers |
| `.claude/rules/impact-awareness.md` | Trade-off analysis, bigger picture, blast radius on shared components |
| `.claude/rules/docker-security.md` | Pinned images, no root, healthchecks, no secrets in ENV, `.dockerignore` |
| `.claude/rules/config-freshness.md` | Re-read `.claude/` config mid-session before using agents/commands |
| `.claude/rules/formatting.md` | Code style per stack — references stack-detection.md, with unknown stack fallback |
| `.claude/rules/refactoring.md` | When/how to refactor safely, scope rules, known duplication targets |
| `.claude/rules/stack-detection.md` | Single source of truth for stack detection. All stack-dependent rules reference this file. |

### Key Thresholds

| Metric | Threshold | Action |
|--------|-----------|--------|
| Context usage | 50-65% | Run `/compact` |
| Context usage | 80%+ | Start a new session |
| CLAUDE.md length | 80 lines max | Extract rules to `.claude/rules/` |
| Service CLAUDE.md | 80 lines max (new) | Keep concise, mark unknowns with [TODO] |
| Commit subject | 72 chars max | Enforced by commit-messages rule |

### Sample Service Ports

| Service | Port | Protocol |
|---------|------|----------|
| `api-gateway` | 8500 (FastAPI) + 8050 (Nginx) | HTTP |
| `graph-rag-api-recherche-rust-service` | 8528 + 8566 (Prometheus) | HTTP |
| `embedding-model-service` | 50052 + 8530 (Prometheus) | gRPC |
| `QC-tracking-service` | 8590 | HTTP |
| `crawler-service` | 8503 | HTTP |
| `api-chatbot-html-service` | 3000 | HTTP |
| `nextjs-formulaire-hp` | 3000 (basePath: `/formulaire`) | HTTP |

### Key File Locations

| File | Path |
|------|------|
| Project root config | `CLAUDE.md` |
| Rules | `.claude/rules/*.md` |
| Agents | `.claude/agents/*.md` |
| Commands | `.claude/commands/*.md` |
| Skills | `.claude/skills/*/SKILL.md` |
| Proto definitions | `protos/grpc_stubs/` |
| Shared libraries | `libs/` |
| Microservices | `apps-microservices/` |
| Model optimization | `model-optimizer/` |
| CI/CD workflows | `.github/workflows/ci_services_*.yml`, `.github/workflows/cd_build_push_*.yml` |
| Docker orchestration | `docker-compose.yml` (root) |
| Python type checking config | [TODO: to be configured by the team] |
| Personal config | `~/.claude/CLAUDE.md` |
| Session primer | `~/.claude/primer.md` |

### Known Gaps

> These items are documented as [TODO] across the project. Addressing them will improve the Claude Code experience for the entire team.

| Gap | Impact |
|-----|--------|
| No test commands in most service CLAUDE.md files | Claude Code cannot run tests automatically |
| No lint commands for Python/Rust services | No automated code quality checks |
| No `.env` templates | New developers cannot configure services |
| No port registry | Risk of port conflicts |
| No pre-commit hooks | Quality checks depend on manual discipline (mitigated by `Stop` hook auto-review) |
| No database migration strategy | Schema changes are ad-hoc |
| No error handling/logging standards | Inconsistent error reporting across services |

---

> **Maintained by the RAG-HP-PUB team.** Update this guide when new commands, agents, or rules are added. Last updated: March 2026.
