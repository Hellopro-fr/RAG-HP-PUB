# RAG-HP-PUB Claude Configuration Optimization — Design Spec

> **Date:** 2026-04-16
> **Scope:** RAG-HP-PUB project config (.claude/)
> **Goal:** Reduce token consumption by ~20-25% per conversation by applying the same optimization pattern validated on Marketplace — removing unused plugins, condensing rules, fixing hook bugs, adding automation rules.

---

## Context

This follows the successful optimization of the Marketplace project's Claude Code configuration. RAG-HP-PUB shares the same config structure (11 rules, 4 agents, 15 commands, 6 hooks) with similar verbosity and the same bugs.

### Constraints

- **Shared GitHub repo** — changes affect all team members
- **Plugins are personal** — each team member manages their own plugins in local settings, so project-level enabledPlugins can be emptied
- **Agents/commands not directly invoked** — team doesn't call @code-reviewer or /plan directly, so redundant ones can be removed
- **Content must be preserved** — condensation removes verbosity, not information

---

## Section 1 — Plugins + Agents + Commands (Deletions)

### Plugins

Empty the `enabledPlugins` block in `.claude/settings.json` → `{}`. Each person manages plugins in their personal `~/.claude/settings.json`.

### Agents to Delete

| Agent | Lines | Reason |
|-------|-------|--------|
| `code-reviewer.md` | 79 | Redundant — superpowers-extended-cc has requesting-code-review |
| `debugger.md` | 57 | Redundant — superpowers-extended-cc has systematic-debugging |

Keep: `doc-writer.md` (31 lines), `test-writer.md` (99 lines)

### Commands to Delete

| Command | Lines | Reason |
|---------|-------|--------|
| `review-task.md` | 105 | Redundant — superpowers skills cover this |
| `plan.md` | 26 | Redundant — writing-plans skill covers this |

---

## Section 2 — Rules Condensation (517 → ~350 lines)

### Condensation Principles

Same as Marketplace: keep imperative rules/constraints/anti-patterns, remove explanatory context, compact lists to tables.

### Per-Rule Plan

| Rule | Current | Target | Changes |
|------|---------|--------|---------|
| `code-modification.md` | 22 | 15 | Merge Mental Model into protocol |
| `commit-messages.md` | 40 | 20 | Remove output template |
| `config-freshness.md` | 24 | 12 | Merge 4 cases into single rule |
| `critical-thinking.md` | 55 | 30 | Dense bullet points, remove phrasing examples |
| `formatting.md` | 92 | 55 | Compact stack sections to tables (Python/Rust/Node/Go) |
| `impact-awareness.md` | 41 | 35 | Compact blast radius table |
| `language.md` | 33 | 20 | Remove explanations, keep dry rules |
| `refactoring.md` | 52 | 30 | Remove Known Technical Debt table |
| `security.md` | 36 | 22 | Tighten |
| `stack-detection.md` | 61 | 45 | Remove meta-sections |
| `docker-security.md` | 61 | 40 | Condense examples, keep checklist |

### New Rules (Automation)

| Rule | Lines | Purpose |
|------|-------|---------|
| `auto-simplify.md` | ~21 | Post-implementation simplification pass |
| `auto-documentation.md` | ~21 | Fetch docs via context7 when using external libraries |
| `frontend-design-guidelines.md` | ~28 | Design principles when building UI |

---

## Section 3 — Commands Condensation

| Command | Current | Target | Changes |
|---------|---------|--------|---------|
| `pre-push.md` | 62 | 30 | Reference stack-detection.md instead of inline logic |
| `new-feature-claude-md-command.md` | 43 | 22 | Reference update-claude-md for shared rules |

---

## Section 4 — Hooks Bug Fixes

Apply the same fixes validated on Marketplace. Read each RAG-HP-PUB hook file first to verify it has the same bugs before applying.

| Hook | Fixes |
|------|-------|
| `dangerous-command-blocker.py` | JSON output (replace emoji stderr), regex backtracking (.*→[^;\|&]*), whitespace tolerance |
| `conventional-commits.py` | Strip `\r\n` for Windows |
| `auto-review-gate.sh` | Combine git diff calls (race condition) |
| `tdd-gate.sh` | Robust JSON parsing with error handling, add jsx/tsx support |
| `secret-scanner.py` | Refine MySQL pattern to match credentials only |

Note: `scope-guard.sh` and `php-dependency-checker.py` may not exist in RAG — check before applying.

---

## Impact Summary

| Category | Tokens Saved | Risk |
|----------|-------------|------|
| Plugin removal | ~1,500 | Zero — personal management |
| Agent/command deletion | ~300 | Low — not directly invoked |
| Rules condensation (net with 3 new) | ~500 | Low — content preserved |
| Commands condensation | ~150 | Zero |
| Hook fixes | 0 (external) | Zero — pure improvements |
| **Total** | **~2,450** | **Low** |

### Before vs After

| Metric | Before | After |
|--------|--------|-------|
| Plugins (project) | 5 active | 0 |
| Agents | 4 (266 lines) | 2 (~130 lines) |
| Commands | 15 | 13 |
| Rules (files) | 11 (517 lines) | 14 (~420 lines) |
| Hook bugs | ~5-8 | 0 |
| Est. tokens/conversation | ~12,000-15,000 | ~9,000-11,000 |

---

## Out of Scope

- **Sub-service CLAUDE.md files** (93 files) — not loaded in context per conversation
- **docs/superpowers/ archival** — historical plans, not in context
- **Marketplace configuration** — already optimized
