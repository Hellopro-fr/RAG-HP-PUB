# Refactoring Rules

> Guidelines for when and how to refactor code safely in the RAG-HP-PUB monorepo.

## When to Refactor

Refactoring is appropriate when:
- A code-reviewer finding explicitly flags duplication or SOLID violation.
- A file exceeds ~300 lines and has multiple responsibilities.
- The same logic exists in 3+ services and should move to `libs/common-utils`.
- The user explicitly requests a refactoring task.

## When NOT to Refactor

- **During a bug fix.** Fix the bug, commit, then refactor separately if needed. Never mix fix and refactor in the same change.
- **During a feature addition.** Build the feature first. Refactor afterward if the new code reveals opportunities.
- **Unprompted.** Do not refactor code that "looks messy" unless the user asks or a reviewer flagged it. Working code has value — leave it alone.
- **Without tests.** If the code has no tests, flag: "Refactoring without tests is risky. Consider adding tests first via `@test-writer`."

## Scope Rules

### Single-Service Refactoring
- Acceptable without special approval.
- Apply `impact-awareness.md`: even within one service, check for downstream effects (exported functions, shared schemas).

### Shared Component Refactoring (`libs/`, `protos/`)
- ALWAYS use `/plan` first.
- List ALL downstream consumers (grep for import statements).
- Ensure backward compatibility: additive changes (new function) are safe; breaking changes (rename/remove) need migration.
- Commit the library change separately from consumer updates.

### Cross-Service Refactoring
- ALWAYS use `/plan with file details` first.
- Work one service at a time. Commit after each service.
- If the refactoring pattern is identical across services (e.g., logging migration), propose a batch approach.

## Known Duplication to Address

These are documented, ongoing refactoring targets. When touching these areas, consider consolidating:

| Pattern | Current State | Target |
|---------|--------------|--------|
| Logging setup | 5/80+ services use `setup_logging()`, 11 still use `print()` | All services should use `common_utils.logging.setup_logging()` |
| Config/credentials | 45 duplicate `credentials.py` with identical fields | Consider a shared `BaseServiceSettings` in common-utils |
| Service structure | 15 services deviate from `main.py + app/{core,router,schemas}/` | Standardize when the service is next modified |

## Refactoring Commit Convention

- Use `refactor(scope):` prefix (Conventional Commits).
- Each refactoring should be a separate commit from feature/fix work.
- Commit message should explain *why* the refactoring was done, not just *what* changed.
