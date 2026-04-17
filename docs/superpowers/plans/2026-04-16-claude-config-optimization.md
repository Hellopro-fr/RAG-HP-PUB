# RAG-HP-PUB Claude Config Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Claude Code token consumption by ~20-25% per conversation by applying Marketplace-validated optimizations to RAG-HP-PUB.

**Architecture:** Edit-only changes to `.claude/` configuration files. No code changes. All changes preserve content — only verbosity is removed.

**Tech Stack:** Markdown, JSON, Python, Bash (hooks)

**Spec:** `docs/superpowers/specs/2026-04-16-claude-config-optimization-design.md`

---

### Task 0: Plugin Cleanup + Agent/Command Deletion

**Goal:** Empty project plugins, delete 4 redundant agents/commands.

**Files:**
- Modify: `.claude/settings.json`
- Delete: `.claude/agents/code-reviewer.md`
- Delete: `.claude/agents/debugger.md`
- Delete: `.claude/commands/review-task.md`
- Delete: `.claude/commands/plan.md`

**Acceptance Criteria:**
- [ ] `enabledPlugins` is `{}`
- [ ] 4 files deleted
- [ ] JSON valid

**Verify:** `python3 -c "import json; json.load(open('.claude/settings.json')); print('OK')"`

**Steps:**

- [ ] **Step 1: Edit settings.json — empty enabledPlugins**

Replace the `enabledPlugins` block with:

```json
  "enabledPlugins": {}
```

- [ ] **Step 2: Delete redundant files**

```bash
cd "d:\DevHellopro\Workspaces\RAG-HP-PUB"
rm .claude/agents/code-reviewer.md .claude/agents/debugger.md .claude/commands/review-task.md .claude/commands/plan.md
```

- [ ] **Step 3: Validate and commit**

```bash
python3 -c "import json; json.load(open('.claude/settings.json')); print('OK')"
git add -A .claude/settings.json .claude/agents/ .claude/commands/
git commit -m "chore(config): empty project plugins, remove 4 redundant agents/commands

Plugins managed per-user in personal settings.
Agents/commands superseded by superpowers-extended-cc skills."
```

---

### Task 1: Create New Automation Rules

**Goal:** Create 3 automation rules (auto-simplify, auto-documentation, frontend-design-guidelines).

**Files:**
- Create: `.claude/rules/auto-simplify.md`
- Create: `.claude/rules/auto-documentation.md`
- Create: `.claude/rules/frontend-design-guidelines.md`

**Acceptance Criteria:**
- [ ] All 3 files created, each under 30 lines

**Verify:** `wc -l .claude/rules/auto-simplify.md .claude/rules/auto-documentation.md .claude/rules/frontend-design-guidelines.md`

**Steps:**

- [ ] **Step 1: Create auto-simplify.md**

```markdown
# Auto-Simplify

> After completing any implementation or modification, perform a simplification pass
> on the code you just wrote or modified. This is automatic — do not wait for the user to ask.

## Simplification Pass

Review your recent changes for:
1. **Unnecessary complexity** — reduce nesting, flatten conditionals
2. **Redundant code** — eliminate dead code, duplicate logic, unused variables
3. **Naming clarity** — rename vague variables/functions to express intent
4. **Over-abstraction** — remove abstractions used only once
5. **Obvious comments** — remove comments that restate the code

## Constraints

- **Never change behavior** — only change how the code is written, not what it does
- **Prefer clarity over brevity** — explicit code beats clever one-liners
- **No nested ternaries** — use if/else or switch for multiple conditions
- **Focus scope** — only simplify code you just modified, not surrounding code
- **Don't over-simplify** — keep helpful abstractions that aid organization
```

- [ ] **Step 2: Create auto-documentation.md**

```markdown
# Auto-Documentation

> Automatically fetch up-to-date documentation when working with external libraries.

## When to Fetch

1. **During implementation** — when writing code that uses external libraries/APIs
   (FastAPI, Pydantic, Crawlee, Playwright, httpx, Milvus, RabbitMQ, etc.),
   use context7 to fetch current documentation before writing the code.

2. **During brainstorming** — when discussing technical choices involving libraries,
   verify current capabilities/limitations before recommending an approach.

## How

- Use the context7 plugin to resolve library documentation.
- If context7 is unavailable, fall back to WebSearch/WebFetch.
- Focus on: API signatures, breaking changes, deprecated features, best practices.

## When to Skip

- Internal project code (libs/, apps-microservices/) — use codebase search instead.
- Well-known language builtins (Python stdlib, Rust std) — no need to verify.
- Repeat usage of a library already verified in the current session.
```

- [ ] **Step 3: Create frontend-design-guidelines.md**

```markdown
# Frontend Design Guidelines

> Apply when building UI components, pages, or web applications.

## Before Coding

1. **Purpose** — What problem does this interface solve? Who uses it?
2. **Tone** — Pick a deliberate aesthetic direction (minimal, editorial, brutalist, luxury, playful, etc.)
3. **Differentiation** — What makes this memorable? One thing someone will remember.

## Implementation Principles

- **Typography**: Distinctive, characterful fonts. Avoid generic (Inter, Roboto, Arial, system fonts).
- **Color**: Cohesive palette via CSS variables. Dominant color + sharp accents.
- **Motion**: CSS-only for HTML, Motion library for React. Focus on page load reveals, scroll-trigger, hover states.
- **Layout**: Unexpected compositions — asymmetry, overlap, grid-breaking. Avoid cookie-cutter patterns.
- **Detail**: Atmosphere via gradients, textures, layered transparencies, shadows.

## Anti-Patterns (Never)

- Generic AI aesthetics (Inter + purple gradient on white)
- Predictable layouts and component patterns
- Design without a clear point-of-view

## Philosophy

Bold maximalism and refined minimalism both work — the key is intentionality, not intensity.
Complexity of implementation must match the aesthetic vision.
```

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/auto-simplify.md .claude/rules/auto-documentation.md .claude/rules/frontend-design-guidelines.md
git commit -m "feat(rules): add auto-simplify, auto-documentation, frontend-design-guidelines

Automation rules for post-implementation simplification, library doc fetching, and UI design."
```

---

### Task 2: Condense Rules — Batch 1 (Shared Rules)

**Goal:** Condense 6 rules that are identical/near-identical to the Marketplace versions.

**Files:**
- Modify: `.claude/rules/code-modification.md`
- Modify: `.claude/rules/commit-messages.md`
- Modify: `.claude/rules/config-freshness.md`
- Modify: `.claude/rules/critical-thinking.md`
- Modify: `.claude/rules/language.md`
- Modify: `.claude/rules/refactoring.md`

**Acceptance Criteria:**
- [ ] All 6 rules condensed to target line counts
- [ ] No content lost

**Verify:** `wc -l .claude/rules/code-modification.md .claude/rules/commit-messages.md .claude/rules/config-freshness.md .claude/rules/critical-thinking.md .claude/rules/language.md .claude/rules/refactoring.md`

**Steps:**

- [ ] **Step 1: Rewrite code-modification.md (22→15)**

Same content as Marketplace condensed version:

```markdown
# Code Modification Rules

## Output Format

- Every code block preceded by its full file path as a Markdown header.
- New files/full rewrites: output the complete file.
- Surgical edits: ONLY the changed function/block with 3 lines of context, marked with `// ... existing code ...`.

## Surgical Edit Protocol

1. **Read first** — always read the file from disk. Never rely on memory.
2. **Minimal diff** — change only what the task requires. Preserve every unrelated line character-for-character.
3. **Preserve formatting** — keep original indentation, line structure, style.
4. **Preserve comments** — never remove unless factually incorrect after the change.
5. **Verify after** — run typecheck/lint. Fix before moving on.
```

- [ ] **Step 2: Rewrite commit-messages.md (40→13)**

```markdown
# Commit Message Protocol

## Format

Default: **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).
User-specified format overrides this.

## Rules

- Generate automatically after any response that creates or modifies files.
- Describe ONLY changes in the current response — never reference unrelated prior work.
- Subject line under 72 characters.
- Always bilingual (EN + FR). See global CLAUDE.md for output template.
```

- [ ] **Step 3: Rewrite config-freshness.md (24→12)**

```markdown
# Configuration Freshness

> Always work with the latest `.claude/` configuration, even mid-conversation.

## Rule

Before invoking any agent, applying any rule, or when the user references a config by name:
re-read the file from disk if it was created or modified in this conversation.

- Files created mid-conversation are immediately active.
- If disk content conflicts with your cached version, **disk wins**.
- When in doubt, re-read. The cost is negligible; the cost of stale rules is bad output.
```

- [ ] **Step 4: Rewrite critical-thinking.md (55→23)**

```markdown
# Critical Thinking Rules

> Be an honest thinking partner, not an agreeable assistant. Apply to EVERY interaction.

## Principles

1. **Anti-Sycophancy** — Never agree just to be pleasant. No flattery ("Great question!"). No padding disagreements. If the request will produce bad code or security risks, say so before implementing.

2. **Blind Spot Detection** — Proactively flag risks, edge cases, and unexamined assumptions. If a change breaks something downstream, mention it. If the user is solving the symptom not the root cause, redirect.

3. **Evidence Over Opinion** — Disagree with evidence (file paths, code, concrete examples), not opinions. If you can't provide evidence, state your uncertainty level explicitly.

4. **Defend or Concede** — When challenged, defend with stronger evidence or concede with a clear reason. Never cave from insistence alone. Never double down if proven wrong.

5. **Uncertainty Transparency** — Distinguish: "This is wrong" (evidence) vs "I'm not sure" (concerns, no proof) vs "I don't know" (insufficient info). Mark uncertain claims with **[UNCLEAR]**. Never bluff.

6. **Anti-Rationalization** — Before implementing something you believe is wrong, flag concerns first. Watch for: "It's probably fine" → verify. "The user wants this" → the user wants the best solution. "Close enough" → define "enough" with evidence.

## When to Skip

- Subjective preferences (naming style, wording, UI preferences)
- Conventions documented in project rules — follow them
- User's domain knowledge about their own business logic — ask questions instead
```

- [ ] **Step 5: Rewrite language.md (33→20)**

```markdown
# Language Rules

## Response Language

Determined ONLY by the user's CURRENT message. Nothing else.

- English message → respond entirely in English
- French message → respond entirely in French
- Mixed → use the dominant language

## Always English

Code identifiers, file names, directory names, log messages, error codes.

## Follows User's Language

Explanations, descriptions, code comments you ADD (existing stay as-is), summaries.

## Exception

Commit messages: always bilingual (EN + FR). See `commit-messages.md`.
```

- [ ] **Step 6: Rewrite refactoring.md (52→30)**

```markdown
# Refactoring Rules

## When to Refactor

- Code-reviewer flagged duplication or SOLID violation
- File exceeds ~300 lines with multiple responsibilities
- Same logic in 3+ services → move to `libs/`
- User explicitly requests it

## When NOT to Refactor

- **During a bug fix or feature addition** — complete the work first, refactor separately
- **Unprompted** — working code has value; don't touch it unless asked or flagged
- **Without understanding consumers** — grep all import statements first

## Scope Rules

**Single-service:** Acceptable. Still apply `impact-awareness.md` for downstream effects.

**Shared libraries** (`libs/common-utils/`, `libs/grpc-stubs/`):
- Use `/plan` first. List ALL downstream consumers via grep.
- Additive changes (new function) = safe. Breaking changes (rename/remove) = need migration.
- Commit shared lib separately from consumer updates.

**Cross-service:**
- Use `/plan with file details` first. One service at a time. Commit per service.

## Commit Convention

- `refactor(scope):` prefix. Separate commit from fix/feature. Explain *why* in message.
```

- [ ] **Step 7: Verify and commit**

```bash
wc -l .claude/rules/code-modification.md .claude/rules/commit-messages.md .claude/rules/config-freshness.md .claude/rules/critical-thinking.md .claude/rules/language.md .claude/rules/refactoring.md
git add .claude/rules/code-modification.md .claude/rules/commit-messages.md .claude/rules/config-freshness.md .claude/rules/critical-thinking.md .claude/rules/language.md .claude/rules/refactoring.md
git commit -m "refactor(rules): condense 6 shared rules for token optimization

Reduce verbosity while preserving all constraints and conventions."
```

---

### Task 3: Condense Rules — Batch 2 (RAG-Specific Rules)

**Goal:** Condense 5 RAG-specific rules (formatting, security, stack-detection, docker-security, impact-awareness).

**Files:**
- Modify: `.claude/rules/formatting.md`
- Modify: `.claude/rules/security.md`
- Modify: `.claude/rules/stack-detection.md`
- Modify: `.claude/rules/docker-security.md`
- Modify: `.claude/rules/impact-awareness.md`

**Acceptance Criteria:**
- [ ] formatting ≤ 58 lines, security ≤ 25, stack-detection ≤ 42, docker-security ≤ 40, impact-awareness ≤ 35

**Verify:** `wc -l .claude/rules/formatting.md .claude/rules/security.md .claude/rules/stack-detection.md .claude/rules/docker-security.md .claude/rules/impact-awareness.md`

**Steps:**

- [ ] **Step 1: Rewrite formatting.md (92→55)**

```markdown
# Formatting Rules

> No project-wide formatter enforced. Detect stack per `.claude/rules/stack-detection.md` before applying conventions.

## Python (80+ services)

| Aspect | Convention |
|--------|-----------|
| Indentation | 4 spaces |
| Line length | 88 chars (black/ruff) |
| Quotes | Double preferred, match file |
| Trailing commas | Yes in multi-line structures |
| Files | `snake_case.py` |
| Functions/vars | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` |
| Pydantic models | `PascalCase` with descriptive names |

Import order: stdlib → third-party → shared libs (`libs/`) → local. Blank line between groups. No duplicates, no unused.

## Rust (1 service + shared lib)

Follow `rustfmt` defaults. 4 spaces, 100 chars max. No `unwrap()` in production — use `Result<T, E>`.

## JavaScript / TypeScript (6 frontends)

| Aspect | Convention |
|--------|-----------|
| Indentation | 2 spaces |
| Semicolons | Required |
| Quotes | Single |
| Trailing commas | Yes |
| React | Functional components + hooks. PascalCase components, camelCase hooks. |

Follow existing ESLint config if present.

## Go

Follow `go fmt` defaults. Tabs. Exported = `PascalCase`, unexported = `camelCase`. Always check errors.

## When Modifying Existing Code

- **Match the file's existing style.** Never reformat outside your change scope.
- Flag inconsistent formatting as a suggestion — do not auto-fix during unrelated changes.
```

- [ ] **Step 2: Rewrite security.md (36→25)**

```markdown
# Security Rules

## Secrets & URLs

- NEVER hardcode service URLs, API keys, passwords, or connection strings.
- ALL service URLs MUST come from environment variables via Pydantic `BaseSettings`.
- Hardcoded URL found → replace with env var in `app/core/config.py`.
- Applies to: HTTP URLs, RabbitMQ, Redis, Neo4j, Milvus, Qdrant, Elasticsearch, gRPC addresses.

## CORS

- **Internal services** (behind api-gateway): `allow_origins=["*"]` acceptable with comment `# Internal only`.
- **Public-facing** (api-gateway, api-html-recherche): MUST restrict origins, methods, headers explicitly.

## JWT & Auth

- JWT secrets via environment variable only — never defaults like "changeme-jwt-secret".
- Redact sensitive headers (`authorization`, `cookie`, `x-api-key`) in logs.

## Input Validation

- Pydantic models for ALL request validation. Never trust user input.
- Sanitize data before LLM prompts (prevent prompt injection).
```

- [ ] **Step 3: Rewrite stack-detection.md (61→42)**

```markdown
# Stack Detection Rules

> Single source of truth for detecting a service's technology stack. All stack-dependent rules MUST reference this file.

## Detection Table

Match in order (first match wins):

| Indicator | Stack | Tests | Formatter | Linter |
|-----------|-------|-------|-----------|--------|
| `Cargo.toml` | Rust | `cargo test` | `cargo fmt` | `cargo clippy` |
| `package.json` + `next.config.*` | Next.js | Jest / `next test` | Prettier | ESLint |
| `package.json` + `vite.config.*` | Vite | Vitest | Prettier | ESLint |
| `package.json` | Node.js | Jest/Vitest | Prettier | ESLint |
| `go.mod` | Go | `go test ./...` | `go fmt` | `go vet` |
| `pom.xml` | Java (Maven) | JUnit | google-java-format | Checkstyle |
| `build.gradle*` | Java/Kotlin | JUnit | google-java-format / ktlint | detekt |
| `requirements.txt` / `pyproject.toml` | Python | pytest | ruff/black | ruff/flake8 |
| `Gemfile` | Ruby | RSpec/minitest | rubocop | rubocop |
| `composer.json` | PHP | PHPUnit | php-cs-fixer | phpstan |

## Detection Process

1. List files in service root → match table above.
2. Check for existing tool configs (`.eslintrc`, `ruff.toml`, `pytest.ini`) — these override defaults.
3. No match → Unknown Stack (see below).

## Unknown / New Stack

1. Show detected files and your stack guess to the user.
2. Ask: "What conventions should I follow?"
3. Apply defaults: match existing style, look for Makefile/tests/Dockerfile.
4. Flag: "New stack detected. Consider updating `stack-detection.md`."
```

- [ ] **Step 4: Rewrite docker-security.md (61→40)**

```markdown
# Docker Security Rules

> Apply when creating or modifying Dockerfiles and docker-compose files.

## Base Images

- NEVER use `latest` tag — pin to specific version (e.g., `python:3.10-slim`).
- NEVER use EOL/deprecated images. Prefer `-slim` or `-alpine` variants.

## Build Patterns (per stack)

- **Python**: `--no-cache-dir` on pip install. Copy requirements.txt first (layer caching).
- **Node.js**: Copy package.json + lock first. Use `npm ci` not `npm install`. Dockerignore node_modules.
- **Rust**: Multi-stage build. Build in `rust:*`, copy binary to `debian:*-slim` or `alpine`.
- **Go**: Multi-stage. `CGO_ENABLED=0` for static binaries. Copy to `scratch` or `alpine`.
- **All**: Multi-stage when build produces artifacts. COPY only needed files. Clean apt lists.

## Runtime Security

- NEVER run as root without justification. Add `USER nonroot`.
- NEVER pass secrets via `ENV` — use `.env` files or Docker secrets.
- NEVER hardcode credentials in Dockerfile.

## docker-compose.yml

- Every service SHOULD have `healthcheck`. Flag missing ones.
- Internal ports → `expose:` not `ports:`. Credentials → `.env` file or secrets.
- Logging: `json-file` driver with `max-size: 10m`, `max-file: 3`.

## Vulnerability Patterns

Flag: `apt-get` without `--no-install-recommends`, `chmod 777`, downloads without checksum, `ADD` instead of `COPY`, missing `.dockerignore`.
```

- [ ] **Step 5: Rewrite impact-awareness.md (41→33)**

```markdown
# Impact Awareness Rules

> Apply BEFORE every code modification.

## 1. Trade-Off Analysis

Before modifying code, briefly state the **Gain** and **Cost**. If the cost is non-trivial, mention it before proceeding.

## 2. Bigger Picture

- Understand the service's role (check its CLAUDE.md).
- Grep for the same pattern in other services. If found: "This same issue exists in [services]. Fix here only, or fix all?"

## 3. Blast Radius — Shared Components

| Path | Impact |
|------|--------|
| `libs/common-utils/` | 75+ Python services — grep all importers |
| `libs/grpc-stubs/` | All gRPC consumers — verify proto compatibility |
| `protos/grpc_stubs/` | All gRPC services — regeneration required |
| `libs/rust-common-utils/` | Rust service — `cargo check` |
| `docker-compose.yml` | All services — flag env/port changes |

When modifying shared components: list downstream consumers, assess backward compatibility, propose migration if breaking.

## 4. When to Skip

Typo fixes, comment-only changes, documentation updates, single-service changes with no shared imports.
```

- [ ] **Step 6: Verify and commit**

```bash
wc -l .claude/rules/formatting.md .claude/rules/security.md .claude/rules/stack-detection.md .claude/rules/docker-security.md .claude/rules/impact-awareness.md
git add .claude/rules/formatting.md .claude/rules/security.md .claude/rules/stack-detection.md .claude/rules/docker-security.md .claude/rules/impact-awareness.md
git commit -m "refactor(rules): condense 5 RAG-specific rules for token optimization

formatting (92→55), security (36→25), stack-detection (61→42),
docker-security (61→40), impact-awareness (41→33)"
```

---

### Task 4: Condense Commands

**Goal:** Condense pre-push.md and new-feature-claude-md-command.md.

**Files:**
- Modify: `.claude/commands/pre-push.md`
- Modify: `.claude/commands/new-feature-claude-md-command.md`

**Acceptance Criteria:**
- [ ] pre-push ≤ 32 lines
- [ ] new-feature-claude-md ≤ 24 lines

**Verify:** `wc -l .claude/commands/pre-push.md .claude/commands/new-feature-claude-md-command.md`

**Steps:**

- [ ] **Step 1: Rewrite pre-push.md (62→30)**

```markdown
# /pre-push — Pre-Push Verification Checklist

Run this checklist before pushing code to the remote repository.

## Process

### Step 1 — Identify changed files
Run `git diff --name-only origin/main...HEAD`. Group by service directory.

### Step 2 — Per-service checks

Detect each service's stack per `.claude/rules/stack-detection.md`, then run syntax checks and tests.

For shared libraries (`libs/`): flag downstream impact per `.claude/rules/impact-awareness.md`.

### Step 3 — Code review
Review all changed files for SOLID/DRY/KISS violations, security issues, and performance concerns.

### Step 4 — Verification discipline

- Every check must have a concrete PASS or FAIL from running the actual command.
- If claiming "tests pass", show the output. No "should be fine" without evidence.

### Step 5 — Summary

| Service | Syntax | Tests | Review | Status |
|---------|--------|-------|--------|--------|

End with: "All checks passed. Safe to push." or "Issues found. Fix before pushing."
```

- [ ] **Step 2: Rewrite new-feature-claude-md-command.md (43→22)**

```markdown
# /new-feature-claude-md — Update CLAUDE.md After a New Feature

A significant new feature or module has been added to an existing service. Update its CLAUDE.md.

## When to Use

- New module/domain added (e.g., WebSocket support, Stripe billing)
- New external dependency integrated
- Folder structure changed significantly
- New commands became available

Do NOT use for minor changes (bug fixes, small refactors, single endpoint).

## Process

1. Ask: **Which service?** and **What was added?**
2. Read the current service CLAUDE.md.
3. Scan the service directory for structural changes (new folders, dependencies, scripts, tests).
4. Propose surgical edits — add to Tech Stack, Commands, Structure, Conventions, or Dependencies as needed.
5. Show diff preview and ask for confirmation.

## Rules

Same as `/update-claude-md`: surgical edits only, keep under 80 lines, extract to `.claude/rules/` if needed.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/pre-push.md .claude/commands/new-feature-claude-md-command.md
git commit -m "refactor(commands): condense pre-push and new-feature-claude-md

pre-push: reference stack-detection.md instead of inline logic
new-feature-claude-md: reference update-claude-md for shared rules"
```

---

### Task 5: Fix Hooks

**Goal:** Fix bugs in 5 hooks (same fixes validated on Marketplace).

**Files:**
- Modify: `.claude/hooks/dangerous-command-blocker.py`
- Modify: `.claude/hooks/conventional-commits.py`
- Modify: `.claude/hooks/auto-review-gate.sh`
- Modify: `.claude/hooks/scope-guard.sh`
- Modify: `.claude/hooks/tdd-gate.sh`
- Modify: `.claude/hooks/secret-scanner.py`

**Acceptance Criteria:**
- [ ] dangerous-command-blocker: JSON output, regex backtracking fixed
- [ ] conventional-commits: \r\n Windows fix
- [ ] auto-review-gate: race condition fixed, delegates to scope-guard.sh
- [ ] scope-guard: git diff instead of .git/HEAD mtime
- [ ] tdd-gate: robust JSON parsing
- [ ] secret-scanner: MySQL pattern refined
- [ ] All files pass syntax check

**Verify:**
```bash
python3 -c "import py_compile; py_compile.compile('.claude/hooks/dangerous-command-blocker.py', doraise=True); print('OK')"
python3 -c "import py_compile; py_compile.compile('.claude/hooks/conventional-commits.py', doraise=True); print('OK')"
python3 -c "import py_compile; py_compile.compile('.claude/hooks/secret-scanner.py', doraise=True); print('OK')"
bash -n .claude/hooks/auto-review-gate.sh && echo "OK"
bash -n .claude/hooks/scope-guard.sh && echo "OK"
bash -n .claude/hooks/tdd-gate.sh && echo "OK"
```

**Steps:**

- [ ] **Step 1: Fix dangerous-command-blocker.py**

Read the file. Apply 3 fixes:

1. Add `deny()` helper that outputs JSON instead of emoji stderr:
```python
    def deny(reason):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }}))
        sys.exit(2)
```

2. Replace all `print(f"🔴 BLOCKED:...`, file=sys.stderr); sys.exit(2)` with `deny(f"BLOCKED:...")`

3. Replace `⚠️ WARNING:` with plain `WARNING:`

4. Replace all `.*` in CRITICAL_PATHS patterns with `[^;|&]*`

- [ ] **Step 2: Fix conventional-commits.py**

Change line with `first_line = message.split('\n')[0].strip()` to:
```python
    first_line = message.split('\n')[0].strip('\r\n \t')
```

- [ ] **Step 3: Fix auto-review-gate.sh**

Replace the two git diff lines:
```bash
CHANGED=$(git diff --name-only 2>/dev/null; git diff --name-only --cached 2>/dev/null)
CHANGED=$(echo "$CHANGED" | sort -u | grep -v '^$')
```

With combined call:
```bash
CHANGED=$( { git diff --name-only HEAD 2>/dev/null; git diff --name-only --cached 2>/dev/null; } | sort -u | grep -v '^$')
```

Then replace the inline scope-guard logic (lines 23-58) with delegation:
```bash
# Delegate scope-guard check instead of duplicating logic
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/scope-guard.sh" ]; then
    bash "$SCRIPT_DIR/scope-guard.sh"
fi
```

- [ ] **Step 4: Fix scope-guard.sh**

Replace the `.git/HEAD`-based find commands (lines 8-15) with git diff approach:
```bash
SPEC_FILE=""
if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    SPEC_FILE=$(git -C "$CLAUDE_PROJECT_DIR" diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E '\.spec\.md$' | head -1)
    if [ -n "$SPEC_FILE" ]; then
        SPEC_FILE="$CLAUDE_PROJECT_DIR/$SPEC_FILE"
    fi
fi

if [ -z "$SPEC_FILE" ]; then
    SPEC_FILE=$(git -C "$CLAUDE_PROJECT_DIR" diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E '^docs/superpowers/.*\.md$' | head -1)
    if [ -n "$SPEC_FILE" ]; then
        SPEC_FILE="$CLAUDE_PROJECT_DIR/$SPEC_FILE"
    fi
fi
```

- [ ] **Step 5: Fix tdd-gate.sh**

Replace the brittle JSON parsing line:
```bash
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)
```

With robust version:
```bash
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)
```

- [ ] **Step 6: Fix secret-scanner.py**

Replace:
```python
    (r'mysql://[^\s"\']+', 'MySQL Connection String', 'critical'),
```
With:
```python
    (r'mysql://[^@\s"\']+:[^@\s"\']+@[^\s"\']+', 'MySQL Connection String with Credentials', 'critical'),
```

- [ ] **Step 7: Validate and commit**

```bash
python3 -c "import py_compile; py_compile.compile('.claude/hooks/dangerous-command-blocker.py', doraise=True); print('OK')"
python3 -c "import py_compile; py_compile.compile('.claude/hooks/conventional-commits.py', doraise=True); print('OK')"
python3 -c "import py_compile; py_compile.compile('.claude/hooks/secret-scanner.py', doraise=True); print('OK')"
bash -n .claude/hooks/auto-review-gate.sh && echo "OK"
bash -n .claude/hooks/scope-guard.sh && echo "OK"
bash -n .claude/hooks/tdd-gate.sh && echo "OK"

git add .claude/hooks/
git commit -m "fix(hooks): fix 6 hook bugs — JSON output, regex, race conditions, Windows compat

- dangerous-command-blocker: proper JSON deny, regex backtracking fix
- conventional-commits: Windows \\r\\n handling
- auto-review-gate: combined git diff, delegate to scope-guard.sh
- scope-guard: git diff instead of fragile .git/HEAD mtime
- tdd-gate: robust JSON parsing with error handling
- secret-scanner: MySQL pattern targets credentials only"
```

---

### Task 6: Final Verification

**Goal:** Verify line counts and overall impact.

**Steps:**

- [ ] **Step 1: Verify rules**

```bash
echo "=== Rules ===" && wc -l .claude/rules/*.md
```

Expected: ~420 lines total (from ~517).

- [ ] **Step 2: Verify agents and commands**

```bash
echo "=== Agents ===" && ls .claude/agents/
echo "=== Commands ===" && ls .claude/commands/
```

Expected: 2 agents (doc-writer, test-writer), 13 commands.

- [ ] **Step 3: Verify settings**

```bash
python3 -c "import json; d=json.load(open('.claude/settings.json')); print('plugins:', d.get('enabledPlugins', {})); print('OK')"
```

Expected: `plugins: {}`.

---

## Summary — All Tasks

| Task | Description | Files | Savings |
|------|-------------|-------|---------|
| 0 | Plugins + deletions | 5 | ~1,800 |
| 1 | New automation rules | 3 new | -350 (add) |
| 2 | Condense shared rules | 6 | ~500 |
| 3 | Condense RAG rules | 5 | ~350 |
| 4 | Condense commands | 2 | ~150 |
| 5 | Fix hooks | 6 | 0 (effectiveness) |
| 6 | Verification | 0 | — |
| **Total** | | **27 files** | **~2,450** |

## Dependencies

```
Task 0 (cleanup) → Task 1 (new rules) → Task 2 (shared rules)
                                       → Task 3 (RAG rules)
                                       → Task 4 (commands)
Task 5 (hooks) — independent
Task 6 (verify) — depends on all others
```
