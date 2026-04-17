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
