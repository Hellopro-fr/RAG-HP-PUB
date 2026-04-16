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
