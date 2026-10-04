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

## Characterization Before Refactoring

Record on the **unchanged** code, and keep green before and after the change:

1. The output **with its order** — assert `list(result.items())`, not a dict `==` (which ignores key order).
2. The **sequence of expensive or side-effecting calls** per branch — spies built on the saved originals, never
   delegating to the patched attribute (a stub that calls the patched name recurses into itself).

Output equality alone lets a refactor stay correct while doing more work (e.g. eager evaluation replacing a
short-circuit).

## Commit Convention

- `refactor(scope):` prefix. Separate commit from fix/feature. Explain *why* in message.
