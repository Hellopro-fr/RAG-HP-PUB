# Claude Code Configuration Migration Prompt

> **Purpose:** Paste this prompt into a Claude Code session on a target repository to migrate and adapt the Claude configuration from RAG-HP-PUB.
>
> **Prerequisite:** The session must have file access to the RAG-HP-PUB repository.

---

## Instructions

I want you to migrate and adapt the Claude Code configuration from an existing reference project (RAG-HP-PUB) to THIS repository. The reference project has a mature configuration with 10 rules, 4 agents, 11 commands, 3 skills, and 1 hook. Your job is NOT to blindly copy — you must analyze this repo first and adapt each config file to fit.

### Phase 1 — Read the source configuration

Read ALL of these files from the RAG-HP-PUB repository (adjust the path if needed):

```
SOURCE_PATH = "<path-to-RAG-HP-PUB>"
```

**Files to read:**
- `$SOURCE_PATH/CLAUDE.md` — root project documentation (architecture reference)
- `$SOURCE_PATH/.claude/settings.json` — hooks and settings
- `$SOURCE_PATH/.claude/rules/` — ALL files:
  - `code-modification.md` — surgical edit protocol
  - `commit-messages.md` — bilingual Conventional Commits
  - `language.md` — response language rules
  - `security.md` — secrets, CORS, JWT, input validation
  - `impact-awareness.md` — trade-off and blast radius analysis
  - `docker-security.md` — Dockerfile and compose best practices
  - `config-freshness.md` — re-read config mid-session
  - `formatting.md` — code style per stack
  - `refactoring.md` — when/how to refactor safely
  - `stack-detection.md` — detect service stack from file indicators
- `$SOURCE_PATH/.claude/agents/` — ALL files:
  - `code-reviewer.md` — exhaustive single-pass review
  - `debugger.md` — structured fix plan with trade-offs
  - `doc-writer.md` — documentation specialist
  - `test-writer.md` — stack-agnostic test generation
- `$SOURCE_PATH/.claude/commands/` — ALL files:
  - `commit-msg.md`, `explain.md`, `understand.md`, `plan.md`
  - `pre-push.md`, `investigate.md`, `audit-feature.md`, `review-task.md`
  - `new-service-claude-md-command.md`, `new-feature-claude-md-command.md`, `update-claude-md-command.md`
- `$SOURCE_PATH/.claude/skills/` — ALL SKILL.md files:
  - `fastapi-service-scaffold/SKILL.md`
  - `rabbitmq-consumer-scaffold/SKILL.md`
  - `proto-sync/SKILL.md`

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
| **KEEP** | The rule/command/agent is universal and applies as-is (e.g., `code-modification.md`, `config-freshness.md`) |
| **ADAPT** | The concept applies but needs modification for this repo (e.g., `security.md` — same principles, different infra) |
| **SKIP** | Not relevant to this repo (e.g., `rabbitmq-consumer-scaffold` if no RabbitMQ) |
| **CREATE NEW** | This repo needs something RAG-HP-PUB doesn't have |

Present the decision matrix as a table:

```
| Source File | Decision | Reason |
|-------------|----------|--------|
| code-modification.md | KEEP | Universal editing protocol |
| security.md | ADAPT | Same principles, different infra stack |
| rabbitmq-consumer-scaffold | SKIP | This repo doesn't use RabbitMQ |
| ... | ... | ... |
```

**Wait for my confirmation before proceeding to Phase 4.**

### Phase 4 — Generate configuration

For each file marked KEEP or ADAPT:

1. **KEEP files**: Copy the content but verify it makes sense for this repo. Adjust any repo-specific references (paths, service names).
2. **ADAPT files**: Rewrite for this repo, keeping the same structure and philosophy but with this repo's actual stacks, services, conventions, and constraints.
3. **CREATE NEW files**: Generate based on this repo's specific needs.

Generate in this order:
1. `.claude/rules/` — all rule files
2. `.claude/agents/` — all agent files
3. `.claude/commands/` — all command files
4. `.claude/skills/` — all skill files (if applicable)
5. `.claude/settings.json` — hooks and settings
6. Root `CLAUDE.md` — full project documentation

For each file, explain briefly what was changed from the source and why.

### Phase 5 — Review summary

Present a final summary:

```
## Migration Summary

### Source: RAG-HP-PUB
- 10 rules, 4 agents, 11 commands, 3 skills, 1 hook

### Target: <this-repo>
- X rules (Y kept, Z adapted, W new)
- X agents (Y kept, Z adapted, W new)
- X commands (Y kept, Z adapted, W new)
- X skills (Y kept, Z adapted, W new)
- X hooks

### Skipped (not applicable)
- [list with reasons]

### New (target-specific)
- [list with reasons]
```

---

## Notes

- The source config follows these principles: SOLID/DRY/KISS, Conventional Commits (bilingual EN/FR), surgical edits, impact awareness, stack-adaptive detection.
- The bilingual commit rule (EN/FR) may need to be adapted if the target team doesn't use French.
- The `stack-detection.md` rule is designed to be extensible — adapt the detection table for this repo's stacks.
- The `Stop` hook (auto-review + CLAUDE.md refresh) is highly recommended for any project.
- Skills are project-specific scaffolds — create new ones matching this repo's service patterns.
