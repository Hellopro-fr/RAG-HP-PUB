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
