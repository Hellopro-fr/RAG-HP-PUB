---
name: fastapi-service-scaffold
description: Scaffold a new Python FastAPI microservice following project conventions (main.py, Dockerfile, CLAUDE.md, tests/, config)
argument-hint: <service-name> <short-description>
---

# Scaffold a New FastAPI Service

Create a new microservice named `$0` with description: `$1`.

## Steps

### 1. Create the service directory structure

```
apps-microservices/$0/
  main.py
  Dockerfile
  requirements.txt
  CLAUDE.md
  app/
    __init__.py
    core/
      __init__.py
      config.py          # Pydantic BaseSettings
    router/
      __init__.py
      health.py          # GET / health check
    schemas/
      __init__.py
  tests/
    __init__.py
    conftest.py
    test_health.py
```

### 2. Follow project conventions

- **main.py**: FastAPI app with CORS middleware, Prometheus metrics mount, lifespan or startup/shutdown events.
- **config.py**: Pydantic `BaseSettings` with `PROJECT_NAME`, `PROJECT_VERSION`, service-specific env vars. NEVER hardcode URLs.
- **Dockerfile**: Based on `python:3.10-slim`, install `libs/common-utils` and `libs/grpc-stubs` via editable install, compile protos if needed.
- **Health check**: `GET /` returns `{"status": "ok", "service": "$0"}`.
- **Logging**: Use `from common_utils.logging import setup_logging; setup_logging("$0")`.
- **Metrics**: Mount Prometheus via `common_utils.metrics.prometheus`.
- **CORS**: `allow_origins=["*"]` with comment `# Internal service only — not exposed publicly` (adjust if public-facing).

### 3. Generate CLAUDE.md

Use the `/new-service-claude-md` command conventions. Keep under 80 lines.

### 4. Generate basic tests

- `conftest.py`: FastAPI TestClient fixture, mock env vars.
- `test_health.py`: Test that `GET /` returns 200 with expected JSON.

### 5. Update root files

- Add service to root `CLAUDE.md` Service Map table.
- Add `@apps-microservices/$0/CLAUDE.md` to Per-Service Instructions.

### 6. Show summary

List all created files and ask the user to review before committing.

## Rules

- Read at least 2 existing similar services before generating (to match exact conventions).
- Apply `.claude/rules/security.md` (no hardcoded URLs/secrets).
- Apply `.claude/rules/docker-security.md` (pinned base image, no root, healthcheck).
- NEVER copy-paste from another service blindly — adapt to the new service's purpose.
