# mcp-gateway-frontend → account-service SSO Client

**Status:** Design approved (brainstorming session 2026-05-05).
**Date:** 2026-05-05
**Owner:** sandrianirinaharivelo@hellopro.fr
**Parent spec:** [`2026-05-04-account-service-sso-design.md`](./2026-05-04-account-service-sso-design.md)
**Branch:** `features/account-service`

## Context

`account-service-{backend,frontend}` provides centralized SSO for the Hellopro platform (parent spec). `mcp-gateway-frontend` currently has its own admin login form that authenticates directly against `hellopro.fr`. We want the admin UI to instead delegate authentication to `account-service` so users see a single shared login page across all internal apps.

The MCP-protocol `/authorize` + `/token` endpoints in `mcp-gateway-service/internal/authserver/` (used by Claude.ai for MCP Authorization Code flow) are explicitly **out of scope** — they must stay MCP-spec compliant and standalone.

## Decisions

| # | Topic | Choice |
|---|---|---|
| 1 | Token handling pattern | **BFF (backend-for-frontend).** mcp-gateway-backend acts as confidential OAuth2 client. Frontend never touches access/refresh tokens. |
| 2 | Coexistence with existing `/login` | **Feature-flag (`SSO_ENABLED`).** Direct hellopro.fr `/login` path stays available for fallback / dev. |
| 3 | Session storage | **Server-side `sso_sessions` table** keyed by opaque session ID in HttpOnly cookie. |
| 4 | Client credential bootstrap | **Auto-fetch via `libs/account-client-go`** (`GetCredentialsFromAPI`). Static env override available. |
| 5 | Logout cascade | **Implement back-channel webhook receiver** (`POST /api/v1/sso/logout`, HMAC-SHA256 with `client_secret`). |
| 6 | Role source | **Local mcp-gateway DB.** Existing `users.role` (admin/read-only/config-only) — `UpsertOnLogin` reused on SSO callback. Per-service role hierarchy per parent spec. |
| 7 | Refresh strategy | **Lazy.** Middleware refreshes when `access_exp - now < 60s`. |
| 8 | PKCE init location | **mcp-gateway-backend `/sso/login`** (relative, same-origin). Frontend redirects to `/sso/login?return_to=...`. Backend reads `ACCOUNT_PUBLIC_URL` env to build the upstream `${ACCOUNT_PUBLIC_URL}/authorize?...` URL it 302s to. |

## Architecture

### Login flow

```
Browser            mcp-gateway-frontend       mcp-gateway-backend          account-service
  │                          │                          │                          │
  │── any /api/v1 (no cookie)──────────────────────────►│ 401                      │
  │◄── 401 ──────────────────────────────────────────── │                          │
  │── window.location = /sso/login?return_to=... ──────►│                          │
  │      gen verifier+state, set short-lived signed     │                          │
  │      cookie `gw_sso_pending`                        │                          │
  │◄── 302 ${ACCOUNT_PUBLIC_URL}/authorize?... ──────── │                          │
  │                                                                                │
  │── GET /authorize?client_id=mcp-gateway& ─────────────────────────────────────► │
  │      redirect_uri=https://gw/sso/callback&                                     │
  │      code_challenge=<S256>&state=...                                           │
  │   user logs in on account-service LoginView (shared)                           │
  │◄── 302 https://gw/sso/callback?code&state ────────────────────────────────────┤
  │                                                                                │
  │── GET /sso/callback?code&state ─────────────────────►│                         │
  │      verify pending cookie, exchange:                │── POST /token ─────────►│
  │                                                      │   grant_type=auth_code  │
  │                                                      │   client_id+secret      │
  │                                                      │   code_verifier         │
  │                                                      │◄── access+refresh+sub ──┤
  │                                                      │   UpsertOnLogin(email)  │
  │                                                      │   INSERT sso_sessions   │
  │◄── 302 <return_to> + Set-Cookie: gw_session=<sid> ──┤                         │
  │                          │                          │                         │
  │── /api/v1/* (cookie) ────┼─────────────────────────►│ LoadSSOSession middleware:
  │                          │                          │  - decode session id
  │                          │                          │  - load row, decrypt tokens
  │                          │                          │  - if access_exp - now < 60s
  │                          │                          │      refresh via /token
  │                          │                          │      grant_type=refresh_token
  │                          │                          │  - set ctx user/role
```

### Logout cascades

- **User-initiated** (`POST /logout`):
  1. Backend reads session row, calls `POST ${ACCOUNT_PUBLIC_URL}/token/revoke` for the refresh token (with `client_id`+`secret`).
  2. Backend deletes the `sso_sessions` row.
  3. Backend clears the `gw_session` cookie.
  4. Frontend receives 302 to `/login` (or homepage).
- **Account-service-initiated** (`POST /api/v1/sso/logout`):
  1. account-service POSTs `{sub, sid?, iat}` JSON to mcp-gateway with header `X-Account-Signature: hmac-sha256=<hex>` (HMAC of body using `client_secret`).
  2. mcp-gateway recomputes HMAC, constant-time compares, then deletes matching `sso_sessions` rows (`DELETE WHERE sub = ? [AND id = ?]`).
  3. Returns 204.

## Components

### Backend — `apps-microservices/mcp-gateway-service/`

```
internal/sso/                     # NEW package
  client.go                       # Build /authorize URL; POST /token (auth_code, refresh, revoke)
  pkce.go                         # gen verifier (32B base64url-no-pad), S256 challenge
  state.go                        # Sign/verify pending cookie (HMAC w/ JWT_SECRET, 5-min TTL)
                                  #   payload: {verifier, state, return_to, exp}
  handlers.go                     # GET /sso/login, GET /sso/callback,
                                  #   POST /logout (SSO mode), POST /api/v1/sso/logout
  webhook.go                      # HMAC-SHA256 verify (constant-time)
  session.go                      # SessionData struct + cookie set/get/clear
                                  #   cookie: gw_session, HttpOnly, Secure, SameSite=Lax
  middleware.go                   # LoadSSOSession: cookie → row → refresh-if-needed → ctx
  bootstrap.go                    # On boot: accountclient.GetCredentialsFromAPI(...)

internal/repository/
  sso_session_repo.go             # NEW — GORM CRUD over sso_sessions

internal/db/models.go             # +SSOSession model (auto-migrated)

internal/auth/handlers.go         # Flag-gated: if cfg.SSOEnabled → return early
internal/auth/middleware.go       # When SSOEnabled, defer identity to internal/sso
internal/api/handler.go           # /api/v1/me unchanged; /api/v1/sso/logout new route

internal/config/config.go         # +Config fields:
                                  #   SSOEnabled bool          (SSO_ENABLED, default false)
                                  #   AccountPublicURL string  (ACCOUNT_PUBLIC_URL)
                                  #   AccountInternalURL string (ACCOUNT_INTERNAL_URL, optional, defaults to public)
                                  #   AccountInternalToken string (ACCOUNT_INTERNAL_TOKEN)
                                  #   SSOClientID string        (SSO_CLIENT_ID, optional override)
                                  #   SSOClientSecret string    (SSO_CLIENT_SECRET, optional override)
                                  #   SSOClientName string      (SSO_CLIENT_NAME, default "mcp-gateway")
                                  #   SSORedirectURI string     (SSO_REDIRECT_URI, default ${PUBLIC_URL}/sso/callback)

cmd/server/main.go                # If cfg.SSOEnabled:
                                  #   1. ssoCreds := bootstrap.FetchOrEnv(cfg)  (fail-closed)
                                  #   2. ssoRepo := repository.NewSSOSessionRepo(database, encryptor)
                                  #   3. ssoClient := sso.NewClient(cfg, ssoCreds, encryptor)
                                  #   4. sso.RegisterHandlers(mux, ssoClient, ssoRepo, userRepo)
                                  #   5. authMiddleware := sso.LoadSSOSession(ssoClient, ssoRepo)
                                  # else current auth.RegisterHandlers + auth middleware.
                                  # +reaper goroutine: deletes expired sessions every 1h.
```

#### `sso_sessions` schema

```sql
CREATE TABLE sso_sessions (
  id              VARCHAR(64)   PRIMARY KEY,             -- hex(32 random bytes), set in cookie
  user_id         BIGINT        NOT NULL,
  sub             VARCHAR(255)  NOT NULL,                -- account-service `sub` claim
  email           VARCHAR(255)  NOT NULL,
  access_token    VARBINARY(2048) NOT NULL,              -- AES-256-GCM ciphertext
  refresh_token   VARBINARY(512)  NOT NULL,              -- AES-256-GCM ciphertext
  access_exp      DATETIME      NOT NULL,
  refresh_exp     DATETIME      NOT NULL,
  created_at      DATETIME      NOT NULL,
  last_seen_at    DATETIME      NOT NULL,
  user_agent      VARCHAR(255),
  client_ip       VARCHAR(45),
  KEY idx_sso_sub         (sub),
  KEY idx_sso_user        (user_id),
  KEY idx_sso_refresh_exp (refresh_exp),
  CONSTRAINT fk_sso_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

Encryption uses the existing `internal/crypto` AES-256-GCM helper (requires `ENCRYPTION_KEY`). When SSO is enabled `ENCRYPTION_KEY` becomes mandatory — config validation rejects boot otherwise.

### Frontend — `apps-microservices/mcp-gateway-frontend/`

```
src/router/index.ts               # On 401 from checkSession or guard:
                                  #   if VITE_SSO_MODE: window.location.href =
                                  #     `/sso/login?return_to=${encodeURIComponent(to.fullPath)}`
                                  #   else current /login push.
                                  # /login route kept for SSO_MODE=false fallback.
src/stores/auth.ts                # Drop localStorage `auth_token` when VITE_SSO_MODE.
                                  # checkSession: GET /api/v1/me with credentials:'include'.
                                  # logout: POST /logout (cookie attached) → window.location='/'.
                                  # Same exported names so views stay unchanged.
src/api/client.ts                 # Add credentials:'include' to all fetches.
                                  # 401 handler: if VITE_SSO_MODE → window.location=/sso/login.
                                  # Drop Authorization: Bearer header in SSO mode.
src/views/LoginView.vue           # Kept for SSO_MODE=false fallback (current implementation).
                                  # Router redirects out before mount when SSO_MODE=true.
vite.config.ts                    # Read VITE_SSO_MODE (default 'true').
Dockerfile                        # ARG VITE_SSO_MODE, pass to npm run build.
nginx.conf                        # +location =/sso/login {proxy_pass $backend; ...}
                                  # +location =/sso/callback {proxy_pass $backend; ...}
                                  # +location =/api/v1/sso/logout {proxy_pass $backend; ...}
```

### Account-service registration

One row in `account-service-backend.oauth2_clients`:

| Field | Value |
|---|---|
| `client_id` | `mcp-gateway` |
| `client_secret` | random 32B hex (encrypted at rest) |
| `name` | `MCP Gateway` |
| `redirect_uris` | `${MCP_GATEWAY_PUBLIC_URL}/sso/callback` |
| `grant_types` | `authorization_code`, `refresh_token` |
| `scope` | `openid profile email` |
| `logout_webhook_url` | `${MCP_GATEWAY_PUBLIC_URL}/api/v1/sso/logout` |
| `allowed_roles` | (empty — gateway enforces locally) |
| `branding.name` | `MCP Gateway` |
| `branding.logo_url` | `/images/servers/hp-logo.svg` |

Provisioning: `account-service-frontend` `/admin/services` UI. The `client_secret` is then served by `GET /internal/credentials/mcp-gateway` to mcp-gateway at boot.

### docker-compose

`mcp-gateway-service` env additions:

```
SSO_ENABLED=true
ACCOUNT_PUBLIC_URL=${ACCOUNT_PUBLIC_URL}            # already in .env
ACCOUNT_INTERNAL_URL=http://account-service-backend:8600
ACCOUNT_INTERNAL_TOKEN=${ACCOUNT_INTERNAL_TOKEN}     # already in .env
SSO_CLIENT_NAME=mcp-gateway
SSO_REDIRECT_URI=${MCP_GATEWAY_PUBLIC_URL}/sso/callback
ENCRYPTION_KEY=${ENCRYPTION_KEY}                     # already required
JWT_SECRET=${JWT_SECRET}                             # already required (used for state cookie too)
```

`mcp-gateway-frontend` build arg:

```
VITE_SSO_MODE=true
```

## Goals

- Single shared login page (account-service-frontend `LoginView`) for the mcp-gateway admin UI.
- Standards-compliant OAuth 2.1 + PKCE S256 + refresh-token rotation client.
- Real-time logout propagation in both directions (gateway-initiated and account-service-initiated).
- Feature-flag rollout: zero behavior change when `SSO_ENABLED=false`.

## Non-Goals

- Replacing `internal/authserver/` (MCP-protocol flow for Claude.ai).
- Changing role hierarchy or moving role state to account-service.
- Multi-IdP / federation.
- SCIM-style user provisioning (UpsertOnLogin remains the only path).
- Migrating existing local sessions — users get re-prompted on cutover.

## Verification

End-to-end smoke test once implemented:

1. Set `SSO_ENABLED=false` → existing `/login` flow works unchanged. **Regression gate.**
2. Set `SSO_ENABLED=true` → start mcp-gateway, account-service. Open `https://gw/dashboard` in fresh browser:
   - Expect 302 → `/sso/login` → 302 → `${ACCOUNT_PUBLIC_URL}/login?...&client_id=mcp-gateway&...`.
   - Submit credentials. Expect 302 → `/sso/callback?code=...` → 302 → `/dashboard` with `gw_session` cookie set.
3. `GET /api/v1/me` returns user payload identical to non-SSO mode.
4. `POST /logout`: verify `sso_sessions` row deleted, `/token/revoke` hit on account-service.
5. Trigger account-service `/admin/users/{id}/revoke-sessions`: account-service POSTs `/api/v1/sso/logout`. Verify 204 + row deleted within ≤1s.
6. Force access-token expiry (set TTL to 60s in account-service for the test client). Verify gateway middleware refreshes silently on next API call.
7. Tamper with `gw_session` cookie value → expect 401 → redirect to `/sso/login`.
8. Tamper with `X-Account-Signature` on webhook → expect 401, no row deleted.
9. `cargo` not applicable (Go service); run `go test ./internal/sso/... ./internal/repository/sso_session_repo_test.go ./internal/api/...`.

## Migration & rollout

1. Land backend + frontend code with `SSO_ENABLED=false` default. **No behavior change for users.**
2. Provision the `mcp-gateway` client row in account-service via admin UI.
3. Flip `SSO_ENABLED=true` in staging compose. Smoke test. Rollback by flipping flag back.
4. Promote to prod once stable. Schedule a follow-up ticket to remove the legacy `auth.RegisterHandlers` path entirely (Decision 2 → option A).

## Open follow-ups (out of scope)

- Same migration for `account-service-frontend` (it already IS the SSO server, so doesn't need to be a client of itself — but its `/me` admin UI could optionally reuse the same LoginView component instead of duplicating).
- Other internal frontends (api-html-recherche, etc.) — same pattern, separate tickets.
- Migrating away from cookie-based session lookup to a stateless signed-cookie variant if the `sso_sessions` table grows hot.
