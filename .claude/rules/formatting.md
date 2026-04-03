# Formatting Rules

> No project-wide formatter is enforced yet. These rules define the conventions Claude must follow when writing or modifying code, ensuring consistency until formal tooling is adopted.

> **Stack detection:** Always detect the service's stack per `.claude/rules/stack-detection.md` before applying formatting conventions. The sections below cover known stacks. For stacks not listed here, follow the Unknown/New Stack section at the bottom.

## Python (80+ services)

### Style
- **Indentation**: 4 spaces (no tabs).
- **Line length**: 88 characters max (black default, compatible with ruff).
- **Quotes**: Double quotes for strings (`"hello"`), single quotes acceptable in existing code — match the file's convention.
- **Trailing commas**: Use in multi-line structures (lists, dicts, function params).

### Import Ordering
Imports MUST follow this order, with a blank line between each group:
```python
# 1. Standard library
import os
import logging

# 2. Third-party packages
from fastapi import FastAPI
from pydantic import BaseModel

# 3. Shared libraries (libs/)
from common_utils.logging import setup_logging
from grpc_stubs import embedding_pb2

# 4. Local/project imports
from app.core.config import settings
```

- NEVER duplicate imports.
- NEVER leave unused imports after a modification.
- Use `from X import Y` for specific symbols. Use `import X` for modules used with prefix.

### Naming
- Files: `snake_case.py`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Pydantic models: `PascalCase` with descriptive names (`InsertProduitRequest`, not `Request1`)

## Rust (1 service + shared lib)

- Follow `rustfmt` defaults (no config override needed).
- **Indentation**: 4 spaces.
- **Line length**: 100 characters max.
- Use `cargo fmt` conventions: trailing commas, braces on same line.
- No `unwrap()` in production code — use `Result<T, E>`.

## JavaScript / TypeScript (6 frontends)

- **Indentation**: 2 spaces (standard for JS/TS ecosystem).
- **Semicolons**: Required (match existing codebase convention).
- **Quotes**: Single quotes for JS/TS strings.
- **Trailing commas**: Yes, in multi-line structures.
- **React**: Functional components with hooks. PascalCase for components, camelCase for hooks.
- Follow existing ESLint config if present in the service; if absent, follow these defaults.

## When Modifying Existing Code

- **Match the file's existing style.** If a file uses single quotes, keep single quotes. If it uses 2-space indent, keep 2-space.
- NEVER reformat code outside the scope of your change.
- If you notice inconsistent formatting in a file, flag it as a suggestion — do not auto-fix it during an unrelated change.

## Go

- Follow `go fmt` defaults (canonical — no configuration needed).
- **Indentation**: Tabs (Go standard).
- **Line length**: No strict limit, but keep readable (~100 chars).
- **Naming**: Exported = `PascalCase`, unexported = `camelCase`. No underscores in function names.
- **Imports**: Use `goimports` grouping (stdlib, third-party, local).
- **Error handling**: Always check errors. Never ignore returned errors.

## Unknown / New Stack

When a service's stack is not listed above:

1. **Detect the stack** per `.claude/rules/stack-detection.md`.
2. **Infer conventions from existing code**: read 2-3 files to determine indentation (tabs vs spaces, width), quote style, naming patterns.
3. **Apply language-agnostic defaults**:
   - Match the file's existing indentation and style.
   - Consistent naming within the file.
   - Trailing newline at end of file.
4. **Flag for update**: "New stack detected: [stack]. Consider adding formatting conventions to `.claude/rules/formatting.md`."

## Future: When Formatters Are Adopted

When the team adopts formal formatters (ruff, prettier, rustfmt), this rule will be updated to reference their configurations. Until then, these conventions serve as the baseline.
