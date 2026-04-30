# account_service — Design

**Date:** 2026-04-30
**Author:** sandrianirinaharivelo
**Status:** Draft — pending review

## Goal

Introduce a centralized authentication service (`account_service`) that issues login sessions for multiple consumer services in this monorepo (e.g., `api-gateway`, `mcp-gateway-frontend`, future). It exposes a Vue-based login UI built from the `public/admin-dashboad/` template and a FastAPI backend that delegates credential validation to the upstream HelloPro auth endpoint, then issues OAuth2 tokens consumed by other services.

## Non-Goals (v1)

- Local user account creation, password reset, or profile management (HelloPro owns user identity).
- Role-based access control (RBAC) claims in the JWT.
- Multi-instance horizontal scaling of the backend.
- Sub-access-token-lifetime global revocation propagation.
- External (non-internal) OAuth clients.
- End-to-end browser tests via Playwright.

## Design Decisions (recorded in brainstorm)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Delegate credential validation to HelloPro upstream (no local user DB). | Matches current api-gateway behavior; avoids duplicating identity store. |
| 2 | Different domains per consumer service; cookie scoped per consumer. | Realistic deployment model (`gateway.hellopro.eu`, `mcp.hellopro.eu`, `account.hellopro.eu`). No cross-domain cookie sharing required. |
| 3 | OAuth2 Authorization Code flow with PKCE. | Industry standard; refresh-token-friendly; resists code interception. |
| 4 | DB-backed OAuth client registration (Tortoise model + admin endpoints). | Audit trail; dynamic add/revoke without redeploy; matches api-gateway DB pattern. |
| 5 | Stack: FastAPI + Tortoise ORM + MySQL (separate `account_db` schema, same MySQL instance as api-gateway). | Project convention. |
| 6 | Two containers: `account-service-backend` (FastAPI) + `account-service-frontend` (Vue/Nginx). | Independent scaling; classic SPA + API split; aligns with crawler-monitor pattern in this repo. |
| 7 | Token policy: 15 min RS256-signed JWT access token + 30-day rotating opaque refresh token + DB-backed revocation. Global logout. | Existing api-gateway uses 15min access; rotation prevents refresh-token replay; DB-backed = real revocation. |
| 8 | JWT contains identity claims only (`sub`, `email`, `display_name`, `aud`, `exp`, `iat`, `jti`). No roles. | HelloPro upstream returns no roles today; YAGNI. |
| 9 | Frontend pages v1: Signin, Consent (skippable per-client flag), Logout, Error. | Internal trusted clients auto-skip consent; consent UI exists for future external clients. Signup/forgot deferred — HelloPro owns. |
| 10 | No Redis. All state in MySQL via Tortoise. | YAGNI: each Redis use case has a cheap MySQL alternative for v1; introduce Redis only if/when multi-instance scaling or sub-15min revocation is required. |

## Architecture

### Components

**`apps-microservices/account-service-backend/`** — FastAPI + Tortoise + MySQL.
- Endpoints: `/authorize`, `/token`, `/refresh`, `/revoke`, `/introspect`, `/userinfo`, `/logout`, `/.well-known/jwks.json`, plus admin `/admin/clients/*` (gated by `X-Admin-Key`).
- Delegates credential check to HelloPro auth endpoint via `httpx`.
- Tortoise models in `account_db` (v1): `OAuthClient`, `AuthorizationCode`, `RefreshToken`, `SigningKey`.
- JWT signed with RS256 (asymmetric — consumers verify with cached public key, no shared secret distributed).
- Public JWKS published at `/.well-known/jwks.json`.
- Migrations via Aerich (matching api-gateway).
- Rate limiting via `slowapi`.

**`apps-microservices/account-service-frontend/`** — Vue 3 SPA.
- Forked and pruned from `public/admin-dashboad/` (Tailwind 4, Vue 3.5, Vue Router 4.5, Vite 6).
- Reuses `Auth/Signin.vue` as the visual base. Removes all non-auth views (charts, ecommerce, forms, tables, etc).
- Routes: `/signin`, `/consent`, `/logout`, `/error`.
- Composables: `useOAuthFlow.ts` (PKCE generation, redirect param parsing), `useAuth.ts`.
- Served by Nginx in production. `nginx.conf` proxies `/auth/*` to backend on the internal Docker network and serves SPA `index.html` for unmatched routes.

**Consumers** (api-gateway, mcp-gateway-frontend, etc.)
- Registered in `OAuthClient` table with `client_id`, `client_secret_hash`, allowed `redirect_uris`, allowed `post_logout_redirect_uris`, and `skip_consent` flag.
- Each consumer adds:
  - `/auth/callback` route — exchanges code for tokens, stores tokens in HttpOnly Secure SameSite=Lax cookies on the consumer's own domain.
  - JWT verification middleware — verifies RS256 signature locally using cached JWKS public key (cache TTL 24h, refetch on `kid` mismatch).
  - `/auth/logout` route — revokes refresh token via account_service then clears local cookies.
- Required env vars: `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_AUTHORIZE_URL`, `OAUTH_TOKEN_URL`, `OAUTH_JWKS_URL`, `OAUTH_REVOKE_URL`.

## Data Flows

### Login (Authorization Code + PKCE)

```
1. User → Consumer/protected-page
2. Consumer detects no/expired session → 302:
     GET account-frontend/signin
       ?client_id=api-gateway
       &redirect_uri=https://gateway.hellopro.eu/auth/callback
       &state=<CSRF-random>
       &code_challenge=<sha256(verifier) base64url>
       &code_challenge_method=S256
3. Vue SPA renders signin form. User submits email + password.
4. Vue POST → account-backend /authorize
     body: {email, password, client_id, redirect_uri, state, code_challenge, code_challenge_method}
5. Backend:
     a. Validates client_id active + redirect_uri exact-match against OAuthClient.redirect_uris.
     b. Calls HelloPro auth endpoint via httpx (5s timeout, 1 retry on 5xx).
     c. On success, inserts AuthorizationCode row (TTL 60s) with code_hash = sha256(raw_code).
     d. If client.skip_consent is False → returns 200 {next: "/consent", code_temp}.
        Else → returns 200 {redirect: "<redirect_uri>?code=<raw>&state=<state>"}.
6. Vue performs the redirect → browser hits Consumer/auth/callback?code=...&state=...
7. Consumer backend:
     a. Verifies state matches its server-side stored state (CSRF guard).
     b. POST account-backend /token
          body: {grant_type:"authorization_code", code, redirect_uri,
                 client_id, client_secret, code_verifier}
     c. Backend validates: code exists, not expired, not consumed, redirect_uri matches issuance,
        sha256(code_verifier) == code_challenge, client_secret matches client_secret_hash.
        Marks code consumed (one-shot).
     d. Issues JWT access token (15 min, RS256) + opaque refresh token (32 bytes,
        stored hashed in RefreshToken table, 30-day TTL).
     e. Returns {access_token, refresh_token, token_type:"Bearer", expires_in:900}.
8. Consumer stores tokens in HttpOnly Secure SameSite=Lax cookies on its own domain.
9. Consumer redirects user to original protected page.
```

### Refresh

Consumer backend POST `/token` with `grant_type=refresh_token`. Backend validates refresh, marks old as `revoked_at=NOW()`, issues new access + new refresh (with `rotated_from_id` chain). Returns the same response shape as initial issuance.

### Validation (per request, fast path)

Consumer reads `access_token` cookie → verifies RS256 signature with cached JWKS public key → reads claims (`sub`, `email`, `aud`, `exp`). No backend round-trip. JWKS fetched once and cached 24h, refetched on `kid` mismatch.

### Logout (global)

```
1. User clicks logout in Consumer.
2. Consumer POST account-backend /revoke {refresh_token, client_id, client_secret}.
3. Backend deletes / marks revoked the RefreshToken row (and rotation chain).
4. Consumer clears its local cookies.
5. Consumer redirects to account-frontend/logout?post_logout_redirect_uri=<url>.
6. Frontend confirms logout, then redirects to post_logout_redirect_uri.
```

Other consumers see global logout the next time they refresh (refresh fails → forced re-login). Within the access-token lifetime (≤15 min), other consumer sessions remain valid — this is the standard OAuth2 trade-off.

### Introspect (rare)

Consumer POST `/introspect` with `{token, client_id, client_secret}` → returns `{active: bool, sub, exp, ...}`. Used only when a consumer needs to confirm immediate revocation (not the hot path).

## Data Models

### MySQL `account_db` (Tortoise)

```python
class OAuthClient(Model):
    id = fields.UUIDField(pk=True)
    client_id = fields.CharField(max_length=64, unique=True, index=True)
    client_secret_hash = fields.CharField(max_length=255)              # bcrypt
    name = fields.CharField(max_length=128)
    redirect_uris = fields.JSONField()                                  # list[str]
    post_logout_redirect_uris = fields.JSONField()                      # list[str]
    skip_consent = fields.BooleanField(default=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class AuthorizationCode(Model):
    code_hash = fields.CharField(max_length=64, pk=True)                # sha256 of raw code
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128)
    code_challenge = fields.CharField(max_length=255)
    code_challenge_method = fields.CharField(max_length=10)             # "S256"
    redirect_uri = fields.CharField(max_length=512)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)                       # +60s
    consumed_at = fields.DatetimeField(null=True)


class RefreshToken(Model):
    id = fields.UUIDField(pk=True)
    token_hash = fields.CharField(max_length=64, unique=True, index=True)
    client_id = fields.CharField(max_length=64, index=True)
    sub = fields.CharField(max_length=128, index=True)
    issued_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(index=True)                       # +30d
    revoked_at = fields.DatetimeField(null=True)
    rotated_from_id = fields.UUIDField(null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    ip = fields.CharField(max_length=45, null=True)


class SigningKey(Model):
    kid = fields.CharField(max_length=64, pk=True)
    private_pem_encrypted = fields.TextField()                          # Fernet-encrypted
    public_pem = fields.TextField()
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    rotated_at = fields.DatetimeField(null=True)


# Deferred to v2 (observability) — not implemented in v1:
# - UserSession: per-(sub, refresh_token_id) session tracking for "list my devices" UX.
# - AccessTokenAudit: jti / client_id / sub log of every issued access token.
# Excluded from v1 to keep the schema focused on auth correctness.
```

### JWT signing keys

- RS256 keypair generated at first start, persisted in `SigningKey`.
- Private PEM encrypted at rest with `JWT_KEY_ENCRYPTION_KEY` env var (Fernet).
- Rotation: admin endpoint generates a new keypair, marks old `is_active=False` but keeps it for verification until all tokens issued under it have expired. JWKS endpoint serves all non-rotated keys.

### Upstream identity

No user data is stored locally beyond `sub` (HelloPro user id/email) + `last_seen_at`. `email` and `display_name` are fetched from the upstream response on each login and embedded in JWT claims at issuance.

## Error Handling

### `/authorize`

| Condition | HTTP | Response |
|-----------|------|----------|
| Unknown / inactive `client_id` | 400 | `{"error":"invalid_client"}` |
| `redirect_uri` not in whitelist | 400 | `{"error":"invalid_redirect_uri"}` — never redirect (open-redirect prevention) |
| Bad PKCE params | 400 | `{"error":"invalid_request","error_description":"..."}` |
| HelloPro rejects credentials | 401 | `{"error":"access_denied"}` (frontend shows generic "wrong credentials") |
| HelloPro timeout / 5xx | 503 | `{"error":"upstream_unavailable"}` |

### `/token`

| Condition | HTTP | Response |
|-----------|------|----------|
| Bad code (unknown / expired / consumed) | 400 | `{"error":"invalid_grant"}` |
| `code_verifier` fails PKCE check | 400 | `{"error":"invalid_grant"}` |
| `client_secret` wrong | 401 | `{"error":"invalid_client"}` |
| `redirect_uri` mismatch | 400 | `{"error":"invalid_grant"}` |
| Refresh revoked / expired | 400 | `{"error":"invalid_grant"}` |
| Refresh reuse detected | 400 | `{"error":"invalid_grant"}` + revoke entire rotation chain (RFC 6819 §5.2.2.3) |

### Refresh-reuse detection

Each `RefreshToken` row has `rotated_from_id`. If the incoming refresh is already `revoked_at IS NOT NULL` AND any other row has `rotated_from_id == incoming.id`, this is replay of an already-rotated token. Revoke the whole chain (all `RefreshToken` rows where `sub == incoming.sub AND client_id == incoming.client_id`). User must re-login.

### Consumer-side errors (in `/auth/callback`)

| Condition | Action |
|-----------|--------|
| `state` mismatch | 400, log CSRF attempt, redirect to error page |
| Code exchange fails | 502 to user, log details server-side |
| JWT signature invalid | clear cookies, redirect to `/signin` |
| JWT expired + refresh fails | clear cookies, redirect to `/signin` |
| JWKS fetch fails (key-rotation race) | retry once with cache bypass, then 503 |

### Frontend UX

- "Invalid credentials" generic message — no enumeration of email vs password.
- Network errors → "Try again" button.
- Consent denied → redirect with `?error=access_denied&state=...`.
- Account locked / upstream 5xx → "Service temporarily unavailable".

### Logging policy

- Always log: `client_id`, `sub` (when known), `error_code`, `request_id`, `ip`.
- Never log: passwords, raw tokens (only sha256 prefix), `client_secret`, `code_verifier`.
- Redact `Authorization` and `Cookie` headers in middleware (per project security rule).

### Rate limiting (slowapi)

- `/authorize` (login attempt): 10/min per IP+email. Lockout 15 min after 10 failed attempts per email.
- `/token`: 60/min per `client_id`.
- `/refresh`: 10/min per refresh token id.
- In-memory limiter for v1 (single backend instance). Note for v2 if scaling out.

### Retries

- HelloPro upstream: 1 retry on 5xx; 5s total timeout. No retry on 4xx.

## Testing

### Backend (pytest + pytest-asyncio)

| Layer | What | How |
|-------|------|-----|
| Unit | PKCE verifier, JWT issuance, secret hashing, redirect_uri validator, rotation-chain detector | pure functions, no DB |
| Integration | Full OAuth flow with Tortoise + SQLite in-memory | `Tortoise.init_models` with `sqlite://:memory:` |
| Contract | HelloPro upstream | `respx` mocks for 200 / 401 / 5xx / timeout |
| Security | redirect_uri exact-match (no substring/wildcard bypass), code one-shot, refresh-reuse detection, signature tampering, `alg=none` rejection, expired token rejection | dedicated `tests/test_security.py` |
| Rate limit | exceed thresholds → 429 | slowapi test client |

Coverage target: ≥85% backend lines. Required tests for every new endpoint.

### Frontend (Vitest + Vue Test Utils)

| Layer | What |
|-------|------|
| Unit | composables (`useAuth`, `useOAuthFlow`), URL param builders, code_verifier generator |
| Component | `Signin.vue` (form validation, error display, loading state), `Consent.vue` (allow/deny buttons) |
| E2E | deferred to v2 (Playwright happy-path against running backend) |

### Consumer integration test

`apps-microservices/account-service-backend/tests/integration/test_consumer_flow.py` spins up the backend, simulates a fake consumer, walks the full code → token → validate → refresh → revoke flow. Serves as a live contract for downstream consumers.

## Deployment

### Folder layout

```
apps-microservices/
├── account-service-backend/
│   ├── app/
│   │   ├── core/         # settings.py, security.py (PKCE, JWT), keys.py
│   │   ├── db/           # database.py, models.py
│   │   ├── routers/      # authorize.py, token.py, revoke.py, introspect.py,
│   │   │                 # userinfo.py, jwks.py, admin_clients.py, logout.py
│   │   ├── services/     # hellopro_client.py, token_service.py, code_service.py
│   │   ├── schemas.py
│   │   └── middleware.py # rate limit, request id, redact-logs
│   ├── main.py
│   ├── tests/
│   ├── requirements.txt  # fastapi, uvicorn, tortoise-orm, pyjwt[crypto],
│   │                     # cryptography, bcrypt, httpx, slowapi, common-utils
│   ├── Dockerfile        # python:3.10-slim, multi-stage, USER nonroot
│   └── CLAUDE.md
└── account-service-frontend/
    ├── src/              # forked from public/admin-dashboad/, pruned to auth-only
    │   ├── views/Auth/   # Signin.vue, Consent.vue, Logout.vue, Error.vue
    │   ├── composables/  # useOAuthFlow.ts (PKCE), useAuth.ts
    │   ├── router/       # /signin, /consent, /logout, /error
    │   └── App.vue, main.ts
    ├── package.json      # vue 3.5, vue-router 4.5, vite 6, tailwind 4
    ├── nginx.conf        # proxies /auth/* to backend, serves SPA index for SPA routes
    ├── Dockerfile        # multi-stage: node:22-alpine build → nginx:1.27-alpine
    └── CLAUDE.md
```

### docker-compose.yml additions

```yaml
account-service-backend:
  build: ./apps-microservices/account-service-backend
  environment:
    - MYSQL_HOST=mysql
    - MYSQL_PORT=3306
    - MYSQL_USER=${ACCOUNT_MYSQL_USER}
    - MYSQL_PASS=${ACCOUNT_MYSQL_PASS}
    - MYSQL_DB=account_db
    - HELLOPRO_AUTH_URL=${HELLOPRO_AUTH_URL}
    - JWT_KEY_ENCRYPTION_KEY=${JWT_KEY_ENCRYPTION_KEY}
    - GATEWAY_ADMIN_KEY=${GATEWAY_ADMIN_KEY}
    - ACCESS_TOKEN_EXPIRE_MINUTES=15
    - REFRESH_TOKEN_EXPIRE_DAYS=30
  expose: ["8000"]
  depends_on: [mysql]
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 5s
    retries: 3

account-service-frontend:
  build: ./apps-microservices/account-service-frontend
  environment:
    - BACKEND_URL=http://account-service-backend:8000
  expose: ["80"]
  depends_on: [account-service-backend]
  healthcheck:
    test: ["CMD", "wget", "-qO-", "http://localhost:80/healthz"]
    interval: 30s
    timeout: 5s
    retries: 3
```

External reverse proxy (existing nginx/traefik) routes `account.hellopro.eu` → `account-service-frontend` → `account-service-backend` for `/auth/*`. All consumer services are hosted under `*.hellopro.eu`. The upstream HelloPro credential validation endpoint (`HELLOPRO_AUTH_URL`) is on a different parent domain (`hellopro.fr`) — this is purely a backend-to-backend call from `account-service-backend` and is not exposed to browsers or consumers.

### Migrations

Aerich initialized for `account_db`, matching the api-gateway pattern. Initial migration creates 4 tables (`OAuthClient`, `AuthorizationCode`, `RefreshToken`, `SigningKey`).

### Bootstrap

`scripts/seed_clients.py` — idempotent. Reads `OAUTH_CLIENTS_SEED_JSON` env var (list of `{client_id, name, redirect_uris, post_logout_redirect_uris, skip_consent}`) and upserts into `OAuthClient`. Generated `client_secret` is logged once on first creation only — operator captures it and configures consumers.

### Consumer integration deltas (separate PRs after account_service ships)

1. **api-gateway**:
   - Add `/auth/callback` route.
   - Replace existing `/login` Jinja flow with redirect to `account-service-frontend/signin`.
   - Keep `DocsAuthMiddleware` but switch to JWT validation via JWKS (drop direct HelloPro call).
   - Add env vars listed above.
2. **mcp-gateway-frontend**: same pattern, smaller surface.
3. **Other consumers** as needed.

### CI/CD

- `.github/workflows/ci_services_account_service_backend.yml` — lint (ruff) + pytest.
- `.github/workflows/ci_services_account_service_frontend.yml` — eslint + vitest + `vue-tsc`.
- `.github/workflows/cd_build_push_account_service_backend.yml` — Docker build + push.
- `.github/workflows/cd_build_push_account_service_frontend.yml` — Docker build + push.

## Security Notes

- All HTTP traffic in production must be HTTPS (cookies marked `Secure`).
- `client_secret` stored hashed (bcrypt). Plain secret returned exactly once at creation.
- `redirect_uri` matched exactly (no substring or wildcard) to prevent open-redirect attacks.
- `state` parameter mandatory in `/authorize` request — CSRF guard.
- PKCE `code_verifier` length ≥ 43 chars; `code_challenge_method=S256` only (reject `plain`).
- JWT signed with RS256; consumers reject any token with `alg` ≠ RS256 and `alg=none` explicitly.
- Refresh-token reuse triggers full chain revocation.
- Rate limiting on all auth endpoints (slowapi).
- Sensitive headers (`Authorization`, `Cookie`, `X-Admin-Key`) redacted in logs.
- All connection strings via Pydantic `BaseSettings`; no hardcoded URLs or secrets.
- Docker images: pinned base, non-root user, healthcheck, multi-stage where applicable, `--no-cache-dir` on pip.

## Out of Scope (v2+)

- Signup, password reset (HelloPro upstream owns).
- RBAC roles / scopes claims.
- Multi-instance horizontal scaling — would need Redis or DB row-lock for one-shot code consumption.
- Sub-15 min global revocation (would require Redis-based revocation list).
- Playwright end-to-end tests.
- External (non-internal) OAuth clients.
- Consent screen polish for external clients.
