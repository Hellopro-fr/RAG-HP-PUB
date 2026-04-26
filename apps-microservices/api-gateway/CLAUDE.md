# api-gateway

Reverse-proxy gateway that authenticates requests (JWT + API key) and routes them to downstream microservices. Also aggregates OpenAPI specs from all registered services.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn (uvloop)
- **DB:** MySQL via Tortoise-ORM (asyncmy)
- **Cache:** Redis (access-token TTL)
- **Proxy:** Nginx sidecar (port 8050) for crawler/comparator routes
- **Shared lib:** `common_utils` (Redis cache_service)

## Build / Run

- **Port:** 8500 (FastAPI), 8050 (Nginx)
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8500 --workers ${UVICORN_WORKERS:-10}`
- **Docker build context:** monorepo root (needs `libs/common-utils`)

## Folder Structure

```
api-gateway/
  main.py                  # FastAPI app, proxy route, OpenAPI aggregator
  nginx.conf               # Nginx reverse-proxy config
  app/
    core/
      auth.py              # DocsAuthMiddleware, verify_api_token
      settings.py          # Configuration, SERVICE_MAP (dynamic from env)
    db/
      database.py          # Tortoise-ORM config
      models.py            # ApiCallHistory, InfoRefreshToken, InfoAccessToken
      schemas.py           # Pydantic response models
    routers/
      login.py             # GET/POST /login, /logout (session-based)
      tokens.py            # /auth/token/* endpoints
    utils/
      token_service.py     # JWT generation helpers
  templates/
    login.html
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `*` | `/{service}/{path}` | Bearer | Proxy to downstream service |
| `WS` | `/{service}/{path}` | None | WebSocket proxy |
| `POST` | `/auth/token/generate` | AdminCle | Create refresh + access token |
| `POST` | `/auth/token/refresh` | Public | Exchange refresh for access token |
| `POST` | `/auth/token/revoke` | AdminCle | Revoke a service's tokens |
| `GET` | `/auth/token/refresh-tokens` | Public | List refresh tokens for a service |
| `GET` | `/auth/token/all-refresh-tokens` | AdminCle | List all refresh tokens |
| `GET` | `/auth/logs` | AdminCle | Paginated audit log |
| `GET` | `/login` | None | Login page |
| `GET` | `/docs` | Session | Swagger UI (admin/public split) |

## Conventions

- Service routing is env-driven: `SERVICE_<NAME>=http://url` registers `/<name>-service`.
- Sensitive headers are redacted before persisting to `ApiCallHistory`.
- Admin endpoints require `X-Admin-Key` header matching `GATEWAY_ADMIN_KEY` env var.

## Per-Service Downstream Timeouts

The gateway applies per-service HTTP timeouts via `Configuration.DOWNSTREAM_TIMEOUTS_S` in `app/core/settings.py`. Services NOT in the map use `timeout=None` (current behavior preserved — zero blast radius on unlisted services).

Currently configured:
- `api-detection-langue-fr-service`: 180s total, 10s connect

Add a service to the map only after understanding its request-duration profile. On timeout, the gateway returns `504` to the caller. Downstream `503` responses (typically from admission middleware load-shedding) are logged at WARNING and passed through with `Retry-After` intact.

Spec: `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`.

## Dependencies on Other Services

- All registered microservices (fetches their `/openapi.json` for spec aggregation)
- MySQL (Tortoise-ORM for token + history storage)
- Redis (access-token TTL cache)
- External: `hellopro.fr` auth endpoint for docs login
