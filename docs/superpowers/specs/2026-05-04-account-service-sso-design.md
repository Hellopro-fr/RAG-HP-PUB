# Account Service — Centralized SSO with OAuth2 (skip-consent)

**Status:** Design approved, ready for implementation plan.
**Date:** 2026-05-04
**Owner:** sandrianirinaharivelo@hellopro.fr

## Summary

A new pair of services — `account-service-backend` (Go 1.24 + GORM + MySQL) and `account-service-frontend` (Vue 3 + TailAdmin Pro template) — that provide a centralized login and OAuth2 Authorization Server for the rest of the Hellopro platform. Each downstream service is registered in the admin UI and receives a `client_id` + `client_secret` to perform OAuth 2.1 Authorization Code + PKCE login against `account-service`. Consent screen is intentionally skipped (trusted first-party clients): once the user authenticates via the shared login form, the auth code is issued immediately and the browser is redirected back to the registered `redirect_uri`. Logout is propagated to clients via a back-channel webhook + short access-token TTL.

## Goals

- One login form + one identity store for all internal Hellopro apps.
- Standard OAuth 2.1 with PKCE S256, refresh token rotation, RFC 7591 dynamic client registration, RFC 7662 introspection, RFC 8414 metadata.
- Admin UI (cloned from `public/admin-dashboad/`) to register new client services and manage credentials, redirect URIs, branding, claim mappings, allowed roles, and token TTLs.
- Real-time logout: back-channel webhook to client services + short access-token TTL with refresh-time revocation check.
- Reuse `mcp-gateway-service/internal/authserver/` as the implementation base; strip the consent step.

## Non-Goals

- OpenID Connect ID tokens beyond the JWT we already mint (no separate `id_token` endpoint).
- Multi-tenancy: one Hellopro tenant.
- Federation with external IdPs (only the existing hellopro.fr auth API is proxied).
- Password reset flow / signup flow (users are upserted on first hellopro.fr login).
- Per-service role hierarchy. Each downstream service owns its own role model; account-service only gates SSO via an `allowed_roles` allowlist string set.

---

## Architecture

```
                                          ┌──────────────────────┐
                                          │  hellopro.fr auth    │
                                          │  (external)          │
                                          └─────────▲────────────┘
                                                    │ POST /login (form)
                                                    │
   ┌──────────────────┐                  ┌──────────┴───────────┐
   │ Client Service   │  GET /authorize  │ account-service-     │
   │ (e.g. mcp-       │ ───────────────► │ backend (Go+GORM)    │
   │  gateway)        │                  │ port 8600            │
   │                  │ ◄─────────────── │                      │
   │                  │  302 ?code&state │ - /authorize         │
   │                  │  POST /token     │ - /token             │
   │                  │ ───────────────► │ - /introspect        │
   │                  │ ◄─────────────── │ - /register          │
   │                  │ access + refresh │ - /.well-known/...   │
   │                  │                  │ - /api/v1/login      │
   │ logout webhook   │ ◄─────────────── │ - /api/v1/admin/*    │
   │ POST {logout_url}│                  │                      │
   └──────────────────┘                  └──────────┬───────────┘
                                                    │ MySQL (GORM)
                                                    ▼
                                          ┌──────────────────────┐
                                          │ account_db           │
                                          │ users                │
                                          │ oauth2_clients       │
                                          │ oauth2_auth_codes    │
                                          │ oauth2_refresh_tokens│
                                          │ logout_events        │
                                          │ audit_logs           │
                                          └──────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │ account-service-frontend (Vue 3 + TailAdmin)                 │
   │ port 8601 (nginx → /api/* + /authorize/* → backend :8600)    │
   │                                                              │
   │ /login         dual-mode (admin UI vs OAuth2 SSO)            │
   │ /admin/services   list/create/edit OAuth2 clients            │
   │ /admin/users      list/promote/revoke                        │
   │ /admin/audit      paginated event log                        │
   │ /me               profile + active sessions                  │
   └──────────────────────────────────────────────────────────────┘
```

### Trust model

- Account-service trusts hellopro.fr to authenticate username/password. It does not store a password hash.
- Client services trust account-service to authenticate users and to send signed back-channel logout webhooks (HMAC-SHA256 with `client_secret`).
- All clients are first-party. There is no consent screen — once the user has logged into account-service for one client, the cookie session lets them SSO into any other client without re-typing creds (until session expires).

### Service boundaries

- `account-service-backend` is single-binary Go, modeled on `mcp-gateway-service`.
- `account-service-frontend` is a static Vue SPA served by nginx; nginx also reverse-proxies the OAuth2 endpoints to backend on the same origin (so `redirect_uri` and the login form share the same site).
- Webhook delivery is handled by an in-process worker pool. No external queue (RabbitMQ etc.) — the `logout_events` table provides retry persistence.

---

## Components

### Backend (`apps-microservices/account-service-backend/`)

```
cmd/server/main.go
internal/
  api/
    handler.go                    Router + middleware chain
    admin_service_handlers.go     /admin/services CRUD
    admin_user_handlers.go        /admin/users + sessions + revoke
    me_handlers.go                /me + /me/sessions
    audit_handlers.go             /admin/audit
    middleware.go                 Logging, recovery, JSON, RequireAdmin
  auth/                           Admin-UI session login
    handlers.go                   POST /api/v1/login, /logout
                                  → AuthenticateHellopro → upsert user → JWT
    jwt.go                        SignJWT, ValidateJWT (HS256)
    session.go                    SetSession / GetSession / ClearSession (cookie)
    middleware.go                 RequireAuth, RequireAdmin
  authserver/                     OAuth2 Authorization Server (lifted)
    handler.go                    AuthServer struct + route registration
    metadata.go                   GET /.well-known/oauth-authorization-server
    authorize.go                  GET/POST /authorize — login → issueAuthCode
                                    (NO consent rendering)
    token_endpoint.go             POST /token (auth_code + PKCE, refresh)
    register.go                   POST /register (RFC 7591, admin-gated)
    introspect.go                 POST /introspect (RFC 7662)
    pkce.go                       S256 verify
    codes.go                      Auth code gen + SHA-256 hash + single-use
    claim_mapper.go               NEW — apply client.claim_mappings to JWT
    branding.go                   NEW — GET /authorize/branding/{client_id}.json
    templates/login.html          Server-rendered fallback (Vue serves prod)
  logout/
    broadcaster.go                NEW — async POST to client.logout_webhook_url
                                    HMAC-SHA256 signed body, retries 1s/2s/4s
    queue.go                      Buffered channel (256) + 4 workers
                                    Persisted via logout_events for resume
  config/config.go                Env-var loader
  crypto/encrypt.go               AES-256-GCM (encrypt client_secret at rest)
  db/
    models.go                     GORM models
    mysql.go                      Connection, pooling, AutoMigrate
  repository/
    user_repo.go                  + UpsertOnLogin, BootstrapAdminFromEnv
    oauth2_client_repo.go
    authcode_repo.go              + PurgeExpired (called periodically)
    refresh_repo.go               + Rotate, RevokeBySID, RevokeAllForUser
                                  + DetectReuseAndRevokeChain
    audit_repo.go
    logout_event_repo.go
init-db/init-account-db.sql       CREATE DATABASE only
go.mod
Dockerfile                        multi-stage golang:1.24-alpine → alpine:3.20
                                  USER nonroot, EXPOSE 8600, healthcheck /health
CLAUDE.md
```

### Frontend (`apps-microservices/account-service-frontend/`)

```
src/
  api/
    client.ts                     Typed fetch wrapper, Bearer + cookie auth
    services.ts                   OAuth2 client CRUD
    users.ts                      User CRUD
    audit.ts                      Audit list
  stores/
    auth.ts                       Pinia: token, user, isAdmin, login, logout
  router/
    index.ts                      Routes + guards
  views/
    LoginView.vue                 Dual-mode (admin UI vs OAuth2 SSO)
    AdminServicesView.vue
    ServiceFormView.vue           Create/edit with sections (identity, branding,
                                    redirects, token policy, allowed_roles,
                                    logout webhook, claim mapper)
    AdminUsersView.vue
    UserSessionsView.vue
    AuditLogView.vue
    MeView.vue
  components/
    layout/                       TailAdmin sidebar/header (kept)
    services/
      RedirectUriList.vue
      ClaimMapperEditor.vue
      BrandingPreview.vue
public/
package.json                      Cloned from public/admin-dashboad
nginx.conf                        Serve SPA + reverse-proxy /api /authorize /token
                                    /introspect /register /.well-known to backend
Dockerfile                        node:22-alpine build → nginx:1.27-alpine
                                  EXPOSE 8601
CLAUDE.md
```

---

## Data Flows

### Flow A — Admin UI login (no OAuth2 query params)

1. Browser GET `/login` → Vue SPA renders form.
2. Form submit → `POST /api/v1/login` JSON `{username,password}`.
3. Backend calls `AuthenticateHellopro(authURL,u,p)` (lifted from mcp-gateway).
4. On success, `userRepo.UpsertOnLogin(email, display_name)` and admin-bootstrap check (env CSV `ADMIN_EMAILS`, or first user ever).
5. `SignJWT(claims{sub,email,is_admin,exp=24h})` and `SetSession` cookie (HttpOnly, SameSite=Lax, Secure in prod).
6. Returns JSON `{token,email,display_name,is_admin}`.
7. Vue auth store stores token, router pushes redirect or `/admin/services` (admin) / `/me` (user).

### Flow B — Service SSO via OAuth2 PKCE (consent skipped)

1. User in client service X clicks "Login".
2. X redirects browser to:
   ```
   GET /authorize?response_type=code
                &client_id=<X.client_id>
                &redirect_uri=https://X/callback
                &code_challenge=<S256(verifier)>
                &code_challenge_method=S256
                &state=<csrf>
                &scope=openid+profile        (optional, ignored beyond logging)
   ```
3. `authserver.HandleAuthorize`:
   - Parse + validate params (response_type=code, S256 method, etc.).
   - `oauth2Repo.GetByID(client_id)` → client (or 400 invalid_request).
   - Validate `redirect_uri` ∈ `client.RedirectURIs` (or 400 + Slack alert).
   - If valid session cookie + JWT exists → skip step 4–5, jump to step 6.
   - Else render Vue login route (302) with the OAuth2 params preserved in the query string.
4. Browser at `/login?client_id=…&redirect_uri=…&code_challenge=…&state=…`.
   Vue `LoginView.vue` reads query, builds hidden form inputs, fetches branding via `/authorize/branding/{client_id}.json` (logo, name, color).
5. Form submit → `POST /authorize` form-encoded with `action=login` + creds + all OAuth2 params.
   Backend calls `AuthenticateHellopro` → upsert → check `user.is_allowed` → check `client.allowed_roles` (if non-empty) vs user role → set session cookie.
6. `authserver.issueAuthCode(client, user, params)`:
   - `rawCode = 32-byte URL-safe random`; `codeHash = SHA256(rawCode)`.
   - INSERT into `oauth2_authorization_codes` with `redirect_uri`, `code_challenge`, `scope`, `expires_at = now + 10 min`, `used = false`.
   - 302 → `redirect_uri?code=<rawCode>&state=<state>`.
   - **No consent template is rendered.**
7. X receives `/callback?code&state`, verifies state.
8. X server-side `POST /token` (HTTP Basic `client_id:client_secret`):
   ```
   grant_type=authorization_code
   code=<raw>
   redirect_uri=<same as step 2>
   code_verifier=<original PKCE verifier>
   ```
9. `token_endpoint.HandleToken`:
   - Lookup `oauth2_authorization_codes WHERE code_hash = SHA256(code) AND used = false AND expires_at > now`.
   - Mark `used = true` (in same tx as refresh-token insert) — single-shot.
   - Verify PKCE: `SHA256(code_verifier) == stored.code_challenge` (constant-time).
   - Verify `client_secret` (constant-time compare against decrypted stored secret).
   - Verify `redirect_uri` matches stored.
   - Build JWT claims:
     ```
     iss = GATEWAY_PUBLIC_URL
     sub = user.email
     aud = client_id
     sid = uuid (session id; used for logout webhook)
     iat = now
     exp = now + client.token_ttl_s        (default 60s)
     + custom claims from client.claim_mappings
     ```
   - `access_token = SignJWT(claims)`.
   - `refresh_token = 32-byte random`; store SHA-256 hash + `sid` + `user_email` + `client_id` + `expires_at = now + client.refresh_ttl_s` (default 30 days).
   - Audit `token_issue`.
   - Return JSON:
     ```
     {access_token, token_type:"Bearer",
      expires_in:<token_ttl_s>,
      refresh_token, scope}
     ```

### Flow C — Refresh

```
X POSTs /token grant_type=refresh_token
               refresh_token=<raw>
               + client auth (Basic or body)
```
- Lookup `refresh_tokens WHERE token_hash=SHA256(raw) AND revoked=false AND expires_at>now`.
- **Reuse detection:** if matching row has `revoked=true`, revoke entire chain by `sid` and Slack alert (`token_reuse_attack`).
- Re-check `user.is_allowed` and `user.role ∈ client.allowed_roles` (revocation safety net for Q3 mechanism C).
- Rotate: mark old row `revoked=true, revoked_reason="rotated"`; INSERT new row with same `sid`, new `token_hash`, fresh `expires_at`, `rotated_from = old.id`.
- Issue new access token (sid preserved → logout still targets the chain).

### Flow D — Logout (back-channel)

User-initiated:
```
X → POST /token/revoke {token, token_type_hint:refresh_token}
   refresh_repo.RevokeBySID(sid) → all rows with that sid revoked.
```

Admin-initiated:
```
Admin UI → POST /api/v1/admin/users/{id}/revoke   (revoke all sessions)
        OR POST /api/v1/admin/sessions/{sid}/revoke (single session)
   refresh_repo.RevokeAllForUser(user_email) | RevokeBySID(sid)
```

After mark revoked:
```
logout.broadcaster.Enqueue(user_email, sid, affected_clients)
   → workers (4) consume from buffered channel (256), persist to logout_events
   for each client where logout_webhook_url != "":
       body = {iss, sub:email, sid, iat:now,
               events:{"http://schemas.openid.net/event/backchannel-logout":{}}}
       sig  = HMAC-SHA256(client.client_secret, body_bytes)
       POST {client.logout_webhook_url}
           Header: X-Logout-Signature: sha256=<hex>
                   Content-Type: application/json
           Body:   <body>
           Timeout 5s, retries 1s/2s/4s on 5xx or network error
       update logout_events.status, attempts, last_error
       audit logout / webhook_fired
```

Client X webhook handler (responsibility of each client) MUST:
- Verify HMAC signature.
- Check `iat` within 5-minute window.
- Destroy local sessions matching `sub` (and optionally `sid`).
- Return 204; idempotent on retry.

### Flow E — Token introspection

```
Resource server X on each request (or with TTL cache):
   POST /introspect {token}
   Auth: Basic client_id:secret
   → parse JWT, lookup sid in refresh_tokens (if revoked: active=false)
   → return {active, sub, exp, sid, ...}
```

---

## Data Model (MySQL + GORM)

### `users`
```
id              char(36) PK
email           varchar(255) UNIQUE
display_name    varchar(255)
is_admin        bool default false
is_allowed      bool default true
last_login_at   datetime
created_at, updated_at
```
- `is_admin` set on first login if email in `ADMIN_EMAILS` env CSV, OR if `users` table is empty after first successful login.
- `is_allowed=false` → 403 on every login attempt.

### `oauth2_clients`
```
id                   char(36) PK
client_id            varchar(64) UNIQUE
client_secret_enc    blob              AES-256-GCM ciphertext
name                 varchar(255)
description          text
logo_url             varchar(512)
brand_color          varchar(16)       hex
redirect_uris        json              ["https://x/callback", ...]
allowed_roles        json              [] | null  empty/null = any
logout_webhook_url   varchar(512)
token_ttl_s          int default 60
refresh_ttl_s        int default 2592000
claim_mappings       json              {"email":"sub","display_name":"name",...}
scope                varchar(512)
is_active            bool default true
created_by           varchar(255)      email
created_at, updated_at
```

### `oauth2_authorization_codes`
```
code_hash       char(64) PK     SHA-256 hex
client_id       varchar(64)
user_email      varchar(255)
redirect_uri    varchar(512)
code_challenge  varchar(128)
scope           varchar(512)
used            bool default false
expires_at      datetime
created_at
```
Index `(client_id, expires_at)` for purge sweep.

### `oauth2_refresh_tokens`
```
id              char(36) PK
token_hash      char(64) UNIQUE        SHA-256 hex
sid             char(36)               session id (also in JWT)
client_id       varchar(64)
user_email      varchar(255)
expires_at      datetime
revoked         bool default false
revoked_at      datetime
revoked_reason  varchar(64)            rotated|user_logout|admin_revoke|reuse_attack
rotated_from    char(36)               parent row when rotated
created_at, last_used_at
```
Indexes: `(sid)`, `(user_email, revoked)`, `(token_hash)` UNIQUE.

### `logout_events`
```
id               char(36) PK
client_id        varchar(64)
user_email       varchar(255)
sid              char(36)
webhook_url      varchar(512)
status           enum('pending','sent','failed') default 'pending'
attempts         int default 0
last_error       text
next_attempt_at  datetime
created_at, updated_at
```
Index `(status, next_attempt_at)` for worker pickup. Survives restart.

### `audit_logs`
```
id            bigint PK
event         enum('login','login_fail','token_issue','token_refresh',
                   'token_reuse_attack','logout','client_create',
                   'client_update','client_revoke','user_promote',
                   'user_demote','user_block','session_revoke',
                   'webhook_fired','webhook_failed')
actor_email   varchar(255)
target_email  varchar(255)
client_id     varchar(64)
ip_addr       varchar(64)
user_agent    varchar(512)
metadata      json
created_at
```
Index `(actor_email, created_at)`, `(event, created_at)`.

### Pool & migration
- `MaxOpen=25, MaxIdle=5, ConnMaxLifetime=1h` (matches mcp-gateway).
- `db.AutoMigrate(...)` on boot.

---

## API Surface

### Public OAuth2 (no auth or client auth)
| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/.well-known/oauth-authorization-server` | none | RFC 8414 |
| GET/POST | `/authorize` | session cookie or login form | skip-consent |
| POST | `/token` | client_id+secret (Basic or body) | grants: `authorization_code`, `refresh_token` |
| POST | `/token/revoke` | client auth | revoke refresh token by sid |
| POST | `/introspect` | client auth | RFC 7662 |
| POST | `/register` | admin session | RFC 7591 (also exposed in admin UI) |
| GET | `/authorize/branding/{client_id}.json` | none | `{name,logo_url,brand_color}` |

### Admin UI (`/api/v1/`)
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/login` | none | hellopro proxy + session cookie |
| POST | `/logout` | session | clear cookie |
| GET | `/me` | session | current user |
| GET | `/me/sessions` | session | active refresh tokens for self |
| POST | `/me/revoke-all` | session | logout-all-devices |
| GET/POST | `/admin/services` | admin | list / create OAuth2 client |
| GET/PUT/DELETE | `/admin/services/{id}` | admin | detail / update / soft-delete |
| POST | `/admin/services/{id}/rotate-secret` | admin | new secret, returns once |
| POST | `/admin/services/{id}/test-webhook` | admin | dry-run logout payload |
| GET | `/admin/users` | admin | list with filters |
| POST | `/admin/users/{id}/promote` | admin | set is_admin=true |
| POST | `/admin/users/{id}/demote` | admin | set is_admin=false |
| POST | `/admin/users/{id}/block` | admin | set is_allowed=false |
| POST | `/admin/users/{id}/unblock` | admin | set is_allowed=true |
| POST | `/admin/users/{id}/revoke` | admin | revoke all sessions |
| GET | `/admin/users/{id}/sessions` | admin | list sessions |
| POST | `/admin/sessions/{sid}/revoke` | admin | revoke one session |
| GET | `/admin/audit` | admin | paginated, filters |
| GET | `/health` | none | `{status, db, version}` |
| GET | `/metrics` | none (or basic-auth) | Prometheus |

---

## Frontend Routes

| Path | View | Auth | Min role |
|---|---|---|---|
| `/login` | `LoginView.vue` | none | — |
| `/admin/services` | `AdminServicesView.vue` | yes | admin |
| `/admin/services/new` | `ServiceFormView.vue` | yes | admin |
| `/admin/services/:id/edit` | `ServiceFormView.vue` | yes | admin |
| `/admin/users` | `AdminUsersView.vue` | yes | admin |
| `/admin/users/:id/sessions` | `UserSessionsView.vue` | yes | admin |
| `/admin/audit` | `AuditLogView.vue` | yes | admin |
| `/me` | `MeView.vue` | yes | user |
| `/` | redirect | — | admin → `/admin/services`, user → `/me` |

`router.beforeEach`:
1. `requiresAuth=false` → pass.
2. Not authenticated → `await authStore.checkSession()`; on failure → `/login?redirect=<from>`.
3. `meta.minRole==='admin' && !isAdmin` → `/me`.

`LoginView.vue` has dual-mode:
- Default: posts JSON to `/api/v1/login`.
- When query has `client_id`+`redirect_uri`+`code_challenge`: posts form-encoded to `/authorize` with `action=login` + hidden OAuth2 fields. Backend issues 302; browser follows to client.
- Branding fetched via `GET /authorize/branding/{client_id}.json` on mount.

`ServiceFormView.vue` collapsible cards:
1. Identity — name, description.
2. Branding — logo upload (multipart), `brand_color` HEX picker.
3. Redirect URIs — `RedirectUriList.vue` (validates `https://` or `http://localhost`).
4. Token policy — `token_ttl_s` (30–3600), `refresh_ttl_s` (300–7776000).
5. Access control — `allowed_roles` free-text tags.
6. Logout webhook — URL + "Test" button (POSTs sample, shows response status).
7. Claim mappings — `ClaimMapperEditor.vue` rows of `user_field → jwt_claim_name`. Defaults: `sub=email`, `name=display_name`.

On create: backend returns `client_id`+`client_secret` ONCE → modal with copy buttons + warning.

---

## Configuration (env vars)

| Var | Default | Description |
|---|---|---|
| `ACCOUNT_PORT` | 8600 | backend listen port |
| `ACCOUNT_PUBLIC_URL` | — | issuer claim + metadata `issuer` (required) |
| `MYSQL_DSN` | — | MySQL connection (required) |
| `ENCRYPTION_KEY` | — | hex 32-byte AES-256 (required) |
| `JWT_SECRET` | — | HS256 signing secret (required) |
| `JWT_AUDIENCE` | `https://www.hellopro.fr` | default JWT audience for admin UI session |
| `AUTH_URL` | — | hellopro.fr login endpoint (required) |
| `FALLBACK_USER` / `_PASS` / `_EMAIL` | — | optional dev fallback (matches mcp-gateway) |
| `ADMIN_EMAILS` | — | CSV of emails auto-promoted on first login |
| `OAUTH2_DEFAULT_TOKEN_TTL` | 60 | seconds |
| `OAUTH2_DEFAULT_REFRESH_TTL` | 2592000 | seconds (30d) |
| `OAUTH2_AUTH_CODE_TTL` | 600 | seconds (10m) |
| `LOGOUT_WEBHOOK_TIMEOUT` | 5 | seconds |
| `LOGOUT_WEBHOOK_RETRIES` | 3 | total attempts |
| `LOGOUT_WORKERS` | 4 | broadcaster goroutine pool size |
| `SECURE_COOKIE` | true | set `Secure` on session cookies |
| `SLACK_WEBHOOK_URL` | — | reuse mcp-gateway slack package |
| `SLACK_AUTH_ALERT_COOLDOWN` | 600 | s |

---

## Security

- **No password storage.** Hellopro.fr remains source of truth.
- **HTTPS only** on `AUTH_URL` (validated at boot, copied from mcp-gateway).
- **Client secrets encrypted at rest** with AES-256-GCM (`ENCRYPTION_KEY`). Plaintext returned to admin only at create / rotate, never on read.
- **PKCE S256 mandatory** on `/authorize`.
- **Single-use auth codes** (transactional `used` flip).
- **Refresh rotation** with reuse detection → revoke entire chain by `sid` + Slack alert.
- **Constant-time comparison** for `client_secret`, `code_challenge`, JWT signatures.
- **HttpOnly + Secure + SameSite=Lax** session cookie. CSRF for non-OAuth2 admin POSTs (already in mcp-gateway pattern).
- **HMAC-signed logout webhook** (`X-Logout-Signature: sha256=<hex>`) using `client_secret` as key. `iat` ≤ 5 min replay window.
- **Admin gate** on `/admin/*` and `/register` via `RequireAdmin` middleware.
- **Slack alerts**: login_fail (rate-limited per ip+username), redirect_uri mismatch, token reuse attack, all-clients webhook failure, panic, shutdown.
- **No secrets in logs** — sensitive headers redacted (Authorization, Cookie, X-Admin-Token).
- **Bcrypt-free**: no local passwords ⇒ no hashing concerns.
- **Brand assets**: logo upload validated MIME (PNG/SVG/JPEG, <512 KiB), stored under `/static/uploads/{client_id}.{ext}`; served by nginx with cache headers.

---

## Error Handling

| Layer | Class | Response | Logged | Slack |
|---|---|---|---|---|
| `auth.handleLoginAction` | hellopro 5xx / network | 401 `Erreur d'authentification` | yes | yes (rate-limited) |
| `auth.handleLoginAction` | invalid creds | 401 `Identifiants invalides` | yes | yes |
| `auth.handleLoginAction` | `is_allowed=false` | 403 explanatory | yes | yes |
| `authserver.parseAuthorizeParams` | bad params | 400 `invalid_request` | yes | no |
| `authserver.HandleAuthorize` | unknown client_id | 400 `invalid_request` | yes | no |
| `authserver.HandleAuthorize` | redirect_uri mismatch | 400 `invalid_request` | yes | yes |
| `authserver.handleLogin` | role not in `allowed_roles` | 403 + redirect to /login banner | yes | yes |
| `token_endpoint` | code expired/used | 400 `invalid_grant` | yes | no |
| `token_endpoint` | PKCE mismatch | 400 `invalid_grant` | yes | yes |
| `token_endpoint` | client_secret mismatch | 401 `invalid_client` | yes | yes |
| `token_endpoint` | refresh reuse | 400 `invalid_grant` + revoke chain | yes | yes |
| `logout.broadcaster` | webhook 5xx/timeout | retry 3× exp; final → `failed` | yes | only if all clients fail for one logout |
| `middleware.recovery` | panic | 500 + Slack panic notify | yes | yes |
| `db.mysql` | connection lost | 503 + restart by orchestrator | yes | yes |

Body: `{"error":"<code>","error_description":"<human>"}` — RFC 6749 codes on OAuth2 paths, project codes on `/api/v1/*`.

Frontend: central interceptor in `api/client.ts` (401 on `/api/v1/*` → clear token + push `/login`).

---

## Observability

- `/health` → `{status, db, version}`.
- `/metrics` (Prometheus client_golang):
  - `account_login_total{result}`
  - `account_token_issue_total{grant_type,client_id}`
  - `account_logout_webhook_total{status}` — sent/failed/retried
  - `account_active_refresh_tokens` gauge
  - `account_token_reuse_attacks_total{client_id}`
  - `http_request_duration_seconds{path,method,status}` histogram
- Structured JSON logs via `log/slog` (Go 1.24): `event`, `actor`, `client_id`, `sid`, `request_id`.

---

## Testing

### Backend (Go)

| Layer | Type | Tool |
|---|---|---|
| `auth/jwt.go` | unit table-driven | `go test` |
| `authserver/pkce.go` | unit | property-style |
| `authserver/codes.go` | unit | gen → hash → single-use lookup |
| `authserver/authorize.go` | integration | `httptest` + testcontainers MySQL |
| `authserver/token_endpoint.go` | integration | code grant + refresh + reuse detection |
| `repository/*` | integration | testcontainers MySQL |
| `logout/broadcaster.go` | unit | `httptest.NewServer` mock client; assert retries, signature, success, all-fail |
| `auth/middleware.go` | unit | bearer parse, role gate |
| `api/admin_*` | integration | testcontainers MySQL |

Mirror mcp-gateway: `*_test.go` colocated, `setupTestDB` helper, `t.Cleanup`.

### Frontend (Vue)

| Layer | Tool |
|---|---|
| `LoginView.vue` oauthMode toggle | Vitest + @vue/test-utils |
| `auth` store | Vitest |
| `ClaimMapperEditor.vue` | component test |
| router guards | unit with mock store |

E2E (optional, separate target): playwright + docker-compose stack — happy path covers admin creates client → user SSO → logout webhook fires → audit shows event.

### CI gates
- `go vet ./...`
- `go test ./...` (with testcontainers MySQL)
- `vue-tsc --build`
- `vitest run`
- Trivy scan on Dockerfiles
- Conventional Commits gate (existing project hook)

---

## Migration & Rollout

1. Branch off `main`: spec lands first.
2. New service is additive — no existing service depends on it.
3. First registered client: mcp-gateway (replace its built-in login), to dogfood the flow before onboarding others.
4. Until mcp-gateway is migrated, both auth surfaces co-exist (no breaking change).

---

## Open Questions / Flags

- **Logo storage**: simplest path is local `/static/uploads/`. If multi-replica, move to S3/GCS later. Flag for revisit if we scale to >1 instance.
- **Forgot-password flow**: deferred. Hellopro.fr handles password reset out-of-band today.
- **OIDC compliance**: not a goal yet, but JWT shape is compatible. We can add `id_token` issuance later without breaking existing clients.
- **Multi-tenant**: out of scope.
- **Session storage**: cookie is JWT-backed (stateless on read, stateful only via `refresh_tokens.revoked`). If the JWT_SECRET is rotated, all sessions invalidate by design.

---

## Done When

- Backend boots, connects MySQL, auto-migrates 6 tables, exposes documented endpoints with healthcheck.
- Frontend renders login + admin views from cloned TailAdmin template; both build cleanly under `vue-tsc`.
- An admin can register a client, copy the secret once, edit it later, regenerate the secret, configure the logout webhook, run the test-webhook button, and see a 200 response from a sample client.
- A test client service can complete the full PKCE flow (`/authorize` → `/token` → access+refresh) and use the access token against its own resource.
- Refreshing a token rotates correctly; reusing an already-rotated refresh token revokes the chain.
- Logging out triggers the back-channel webhook with a verifiable HMAC signature; client receiving 5xx triggers retry; final failure shows in `/admin/audit` and `UserSessionsView`.
- All Go and Vue tests pass in CI. Trivy scan clean. Conventional Commits hook passes.
