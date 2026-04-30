# account-service-backend

OAuth2 Authorization Code + PKCE provider. FastAPI + Tortoise + MySQL (`account_db`). Issues RS256 JWT access tokens (15 min) + opaque rotating refresh tokens (30 d). Delegates credential validation to upstream HelloPro auth endpoint (`HELLOPRO_AUTH_URL`).

## Tech Stack

- Python 3.10, FastAPI, Tortoise-ORM (asyncmy/MySQL), Aerich
- PyJWT[crypto], cryptography (Fernet), bcrypt
- httpx (upstream), slowapi (rate limit)
- pytest + pytest-asyncio + respx + aiosqlite (in-memory tests)

## Run

```bash
# Tests (in-memory sqlite, no external deps)
pytest -v

# Local dev (against MySQL)
export MYSQL_HOST=... MYSQL_USER=... MYSQL_PASS=... MYSQL_DB=account_db
export HELLOPRO_AUTH_URL=https://auth.hellopro.fr/api/login
export JWT_KEY_ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
export GATEWAY_ADMIN_KEY=...
uvicorn main:app --reload --port 8000
```

## Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Liveness check |
| `/.well-known/jwks.json` | GET | Public RSA keys for JWT verification |
| `/authorize` | POST | Validate creds via HelloPro, issue auth code |
| `/token` | POST | Exchange code or refresh for access+refresh pair |
| `/revoke` | POST | Revoke refresh token chain (idempotent) |
| `/introspect` | POST | Validate access token (rare path) |
| `/userinfo` | GET | Bearer-protected — returns sub/email/display_name |
| `/logout` | GET | Post-logout confirmation page |
| `/admin/clients` | POST/GET | Register/list OAuth clients (X-Admin-Key) |
| `/admin/clients/{client_id}` | DELETE | Soft-delete (mark inactive) |

## File Inventory

```
main.py                        FastAPI + lifespan + middleware
app/
  core/
    settings.py                Pydantic BaseSettings (env)
    security.py                PKCE check, bcrypt, sha256, random tokens
    jwt_keys.py                RSA gen, Fernet encrypt, JWKS, ensure_signing_key
    jwt_tokens.py              issue/decode RS256 access tokens
  db/
    database.py                Tortoise init + TORTOISE_ORM (Aerich)
    models.py                  OAuthClient, AuthorizationCode, RefreshToken, SigningKey
  services/
    hellopro_client.py         httpx -> HELLOPRO_AUTH_URL (1 retry on 5xx)
    code_service.py            issue + consume one-shot auth codes
    token_service.py           access+refresh issuance, rotation, reuse detect
    client_service.py          OAuthClient CRUD + bcrypt secret check
  routers/                     one file per endpoint
  schemas.py                   Pydantic request/response models
  middleware.py                request_id + log redaction
  rate_limit.py                slowapi limiter (10/min /authorize, 60/min /token)
scripts/seed_clients.py        idempotent client seeder
migrations/                    Aerich (committed)
tests/                         pytest suite (sqlite in-memory)
```

## Conventions

- Tortoise ORM with MySQL in production, sqlite in-memory in tests.
- Migrations via Aerich; commit them.
- `verify_pkce` rejects everything except `S256`.
- `decode_access_token` rejects any `alg` != RS256 (no `none`, no HS*).
- Refresh-token reuse triggers full chain revocation (RFC 6819).
- `redirect_uri` matched exactly — no substring/wildcard.
- Sensitive headers redacted by middleware before logging.

## What This Provides to Other Services

- Centralized identity issuance for any monorepo service via OAuth2 Authorization Code + PKCE.
- Public JWKS endpoint for stateless JWT verification at consumers.
- Admin endpoints to manage consumer clients dynamically.
- Companion integration guide: `docs/superpowers/specs/account-service-README.md`.
