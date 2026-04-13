# Claude Code Configuration Migration Prompt

> **Purpose:** Paste this prompt into a Claude Code session on a target repository to migrate and adapt the Claude configuration from RAG-HP-PUB.
>
> **Prerequisite:** The session must have file access to the RAG-HP-PUB repository.
>
> **Last updated:** 2026-04-04
> **Source config:** 11 rules, 4 agents, 15 commands, 4 skills, 8 hooks, 2 settings, 1 plugin

---

## Instructions

I want you to migrate and adapt the Claude Code configuration from an existing reference project (RAG-HP-PUB) to THIS repository. The reference project has a mature configuration with 11 rules, 4 agents, 15 commands, 4 skills, 8 hooks, 2 settings, and 1 plugin. Your job is NOT to blindly copy — you must analyze this repo first and adapt each config file to fit.

### Phase 1 — Read the source configuration

Read ALL of these files from the RAG-HP-PUB repository (adjust the path if needed):

```
SOURCE_PATH = "<path-to-RAG-HP-PUB>"
```

**Root documentation:**
- `$SOURCE_PATH/CLAUDE.md` — root project documentation (architecture, config reference)

**Rules** (`$SOURCE_PATH/.claude/rules/` — 11 files):
- `code-modification.md` — surgical edit protocol (read first, minimal diff, preserve formatting)
- `commit-messages.md` — bilingual Conventional Commits (EN/FR)
- `language.md` — response language follows user's current message
- `security.md` — no hardcoded secrets/URLs, Pydantic BaseSettings, CORS (internal vs public), JWT, all infra connections
- `impact-awareness.md` — trade-off analysis, bigger-picture context, blast radius on shared components
- `docker-security.md` — pinned images, no root, healthchecks, no secrets in ENV, stack-specific build patterns
- `config-freshness.md` — re-read `.claude/` files mid-conversation before using agents/commands
- `formatting.md` — code style per stack (references stack-detection.md), unknown stack fallback
- `refactoring.md` — when/how to refactor safely, scope rules, known duplication targets
- `stack-detection.md` — single source of truth for detecting service stacks from file indicators
- `critical-thinking.md` — anti-sycophancy, blind spot detection, evidence-based pushback, uncertainty transparency

**Agents** (`$SOURCE_PATH/.claude/agents/` — 4 files):
- `code-reviewer.md` — 7-dimension exhaustive single-pass review with impact awareness and verification evidence
- `debugger.md` — 4-phase root cause investigation, structured fix plan with trade-offs and blast radius
- `doc-writer.md` — documentation specialist, code-immutable, English docstrings only
- `test-writer.md` — stack-agnostic test generation (Python/Rust/Node.js/unknown) with TDD integration and anti-patterns

**Commands** (`$SOURCE_PATH/.claude/commands/` — 15 files):
- `commit-msg.md` — generate bilingual commit message (EN/FR)
- `explain.md` — explain a single file or code block (no modifications)
- `understand.md` — absorb and summarize multiple files or broad topics
- `plan.md` — interactive planning with complexity escalation (simple → full spec with no placeholders)
- `pre-push.md` — pre-push verification with stack detection, verification discipline (evidence-based)
- `new-service-claude-md-command.md` — generate CLAUDE.md for a new service + update root
- `new-feature-claude-md-command.md` — update service CLAUDE.md after a feature addition
- `update-claude-md-command.md` — propose surgical CLAUDE.md updates (mistake prevention, project change, rescan)
- `investigate.md` — evidence-based statement verification (CONFIRMED / PARTIALLY TRUE / FALSE / INCONCLUSIVE)
- `audit-feature.md` — end-to-end feature audit tracing the pipeline across services
- `review-task.md` — Tech Lead review: combined state + diff analysis, verification before verdict, APPROVED / CHANGES REQUESTED / BLOCKED
- `secrets-scanner.md` — full codebase scan for hardcoded secrets, API keys, passwords, connection strings
- `test-coverage.md` — test coverage report across all services (well-tested / minimal / none)
- `dependency-mapper.md` — map cross-service dependencies: imports, gRPC, RabbitMQ, HTTP calls
- `architecture-review.md` — architecture-level review: coupling, cohesion, scalability, observability

**Skills** (`$SOURCE_PATH/.claude/skills/` — 4 directories, each with SKILL.md):
- `fastapi-service-scaffold/SKILL.md` — scaffold a new FastAPI service with all conventions
- `rabbitmq-consumer-scaffold/SKILL.md` — scaffold a new RabbitMQ processor with consumer, DLQ, metrics
- `proto-sync/SKILL.md` — regenerate Python gRPC stubs from protos/ and check breaking changes
- `docker-expert/SKILL.md` — Docker troubleshooting, optimization, and security

**Hooks** (`$SOURCE_PATH/.claude/hooks/` — 5 script files + 3 inline in settings.json):
- `secret-scanner.py` — PreToolUse (Bash): block commits containing hardcoded secrets (60+ regex patterns)
- `dangerous-command-blocker.py` — PreToolUse (Bash): block catastrophic commands, protect critical paths
- `conventional-commits.py` — PreToolUse (Bash): validate commit messages follow Conventional Commits format
- `tdd-gate.sh` — PreToolUse (Edit/Write): block production code edits if no corresponding test file exists
- `scope-guard.sh` — Stop: warn if files modified outside declared spec scope
- (inline) force-push-blocker — PreToolUse (Bash): block `git push --force` and `-f`
- (inline) format-python — PostToolUse (Edit): auto-format Python files after edits (black/ruff)
- (inline) auto-review — Stop (prompt): check CLAUDE.md freshness + self-review modified code

**Settings** (`$SOURCE_PATH/.claude/settings.json`):
- `permissions.deny` — block reading `.env`, `.env.*`, `secrets/**`, `config/credentials.json`
- `env` — bash timeouts: default 120s, max 600s, max output 100K chars
- `enabledPlugins` — superpowers plugin (structured dev workflow: brainstorming, TDD, subagent orchestration)

After reading, summarize what you understood from the source config (brief, 1 line per file).

### Phase 2 — Analyze THIS repository

Explore this repository thoroughly:

1. **Project structure**: List top-level directories, key files, and overall architecture.
2. **Stack detection**: What languages/frameworks are used? (Check for package.json, requirements.txt, Cargo.toml, go.mod, pom.xml, etc.)
3. **Existing `.claude/` config**: Does any config already exist? If yes, read it all.
4. **Existing CLAUDE.md**: Does a root CLAUDE.md exist?
5. **CI/CD**: Check `.github/workflows/`, `Makefile`, `justfile`, etc.
6. **Docker**: Check for Dockerfiles, docker-compose.
7. **Testing**: Check for test directories, test frameworks.
8. **Shared code**: Check for shared libraries, monorepo structure.
9. **Documentation**: Check docs/ directory.

Present a summary of your findings.

### Phase 3 — Decision matrix

For EACH source config file, decide one of:

| Decision | When |
|----------|------|
| **KEEP** | The rule/command/agent is universal and applies as-is (e.g., `code-modification.md`, `critical-thinking.md`) |
| **ADAPT** | The concept applies but needs modification for this repo (e.g., `security.md` — same principles, different infra) |
| **SKIP** | Not relevant to this repo (e.g., `rabbitmq-consumer-scaffold` if no RabbitMQ) |
| **CREATE NEW** | This repo needs something RAG-HP-PUB doesn't have |

Present the decision matrix as a table:

```
| Source File | Category | Decision | Reason |
|-------------|----------|----------|--------|
| code-modification.md | rule | KEEP | Universal editing protocol |
| security.md | rule | ADAPT | Same principles, different infra stack |
| rabbitmq-consumer-scaffold | skill | SKIP | This repo doesn't use RabbitMQ |
| ... | ... | ... | ... |
```

**Wait for my confirmation before proceeding to Phase 4.**

### Phase 4 — Generate configuration

For each file marked KEEP or ADAPT:

1. **KEEP files**: Copy the content but verify it makes sense for this repo. Adjust any repo-specific references (paths, service names).
2. **ADAPT files**: Rewrite for this repo, keeping the same structure and philosophy but with this repo's actual stacks, services, conventions, and constraints.
3. **CREATE NEW files**: Generate based on this repo's specific needs.

Generate in this order:
1. `.claude/hooks/` — hook scripts (adapted to this repo's stack)
2. `.claude/rules/` — all rule files
3. `.claude/agents/` — all agent files
4. `.claude/commands/` — all command files
5. `.claude/skills/` — all skill files (if applicable)
6. `.claude/settings.json` — hooks, permissions, env, plugins
7. Root `CLAUDE.md` — full project documentation with Claude Code Configuration section

For each file, explain briefly what was changed from the source and why.

### Phase 5 — Review summary

Present a final summary:

```
## Migration Summary

### Source: RAG-HP-PUB
- 11 rules, 4 agents, 15 commands, 4 skills, 8 hooks, 2 settings, 1 plugin

### Target: <this-repo>
- X rules (Y kept, Z adapted, W new)
- X agents (Y kept, Z adapted, W new)
- X commands (Y kept, Z adapted, W new)
- X skills (Y kept, Z adapted, W new)
- X hooks (Y kept, Z adapted, W new)

### Skipped (not applicable)
- [list with reasons]

### New (target-specific)
- [list with reasons]
```

---

## Notes

- The source config follows these principles: SOLID/DRY/KISS, Conventional Commits (bilingual EN/FR), surgical edits, impact awareness, stack-adaptive detection, critical thinking (anti-sycophancy).
- The bilingual commit rule (EN/FR) may need to be adapted if the target team doesn't use French.
- The `stack-detection.md` rule is designed to be extensible — adapt the detection table for this repo's stacks.
- The hooks are the highest-impact items — they enforce rules automatically without manual invocation.
- Skills are project-specific scaffolds — create new ones matching this repo's service patterns.
- The `superpowers` plugin is recommended for any project — install with `/plugin install superpowers@claude-plugins-official`.
- Project commands already integrate superpowers best practices (verification evidence, no-placeholder plans, root-cause-first debugging, TDD integration, anti-rationalization). You get the best of both by default.

## Universal rules (likely KEEP for any project)

These rules apply regardless of tech stack or project type:
- `code-modification.md` — surgical editing protocol
- `config-freshness.md` — mid-session config freshness
- `critical-thinking.md` — anti-sycophancy and intellectual honesty
- `impact-awareness.md` — trade-off and blast radius analysis
- `stack-detection.md` — adaptive stack detection with unknown fallback

## Universal hooks (likely KEEP for any project)

- `secret-scanner.py` — prevent committing secrets
- `dangerous-command-blocker.py` — prevent catastrophic commands
- `force-push-blocker` — prevent force pushes
- `conventional-commits.py` — enforce commit message format
- Auto-review (Stop prompt) — self-review after each response