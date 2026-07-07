# Design — account-service SSO login for `redis-client-frontend`

- **Date:** 2026-06-18
- **Service:** `apps-microservices/redis-client-frontend` (Next.js 16 / React 19 admin UI)
- **Goal:** Replace the current "paste a raw `ADMIN_TOKEN` into a cookie" login with a real
  OAuth 2.1 + PKCE SSO login against `account-service`, mirroring how `api-gateway` authenticates
  its browser users.
- **Status:** Approved design (brainstorming). Next step: implementation plan (writing-plans).

---

## 1. Context

`redis-client-frontend` is a browser admin UI that browses and mutates **one shared Redis instance**
(`SCAN` all keys, `GET`/`TTL`/`MEMORY USAGE`, `DEL` one key, **`FLUSHDB` the whole DB**). Today its
auth is `middleware.ts` comparing an `ADMIN_TOKEN` env var against an `admin_token` cookie that the
`app/login/page.tsx` page sets client-side. Weaknesses: shared static secret, cookie not `HttpOnly`,
no real identity, plain string compare, auth disabled entirely when `ADMIN_TOKEN` is unset.

`account-service` is the org's centralized SSO / OAuth 2.1 authorization server. `api-gateway`
already integrates with it as an OAuth client (browser login that gates `/docs`). This design clones
that integration into the Next.js app.

### account-service OAuth contract (as consumed)

- **Two URLs (deliberate split):**
  - `ACCOUNT_PUBLIC_URL` (default `http://localhost:8601`, prod `https://account.hellopro.fr`) —
    **browser-facing**, used in the 302 to `/authorize`. Served by `account-service-frontend` (Vue, host port 8601).
  - `ACCOUNT_BASE_URL` (default `http://account-service-backend:8600`) — **server-to-server**,
    used for the `/token` exchange. `account-service-backend` (Go) is `expose`-only on `services-net`.
- **Endpoints:** `GET {PUBLIC}/authorize`, `POST {BASE}/token`, `GET {PUBLIC}/logout` (RP-initiated).
- **PKCE:** `code_challenge_method=S256` is **mandatory** (OAuth 2.1). `response_type=code`.
- **Client auth at `/token`:** HTTP Basic (`client_id`:`client_secret`), **not** in the body.
- **Token:** an `access_token` that is a **JWT signed HS256 with the shared `JWT_SECRET`**.
  Claims: `sub` = user email, `email`, `aud` = client_id, `iss`, `sid`, `iat`, `exp`.
  **Not OIDC** — no `id_token`, no `/userinfo`. Identity comes from decoding the access token.
  Default access-token TTL is **~60s** (`OAUTH2_DEFAULT_TOKEN_TTL`), refresh TTL 30d.
- **redirect_uri:** **exact-match**, must be pre-registered on the client record; sent on
  `/authorize` and **re-validated identically** at `/token`.
- **Client registration:** `POST {BASE}/api/v1/admin/services` (needs an authenticated
  account-service user JWT) or the Vue admin "Services" page. Returns `client_id` + `client_secret`
  (**shown once**). No static seed file.

---

## 2. Decisions (locked during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Implementation approach | **Native Next.js BFF OAuth client** (hand-rolled PKCE in route handlers + `jose`). Not Auth.js, not gateway-delegation. |
| D2 | Session lifetime | **Own ~8h signed session cookie**, decoupled from the 60s account-service token (BFF pattern). No silent refresh in v1. |
| D3 | Authorization | **Email allow-list** (`ADMIN_EMAILS` env). Authenticated ≠ authorized; only listed emails pass. Protects `FLUSHDB`. |
| D4 | Old paste-token login | **Removed.** SSO is the only auth path. Delete `app/login/page.tsx` + `ADMIN_TOKEN` logic. |
| D5 | Logout | **Local session clear**, plus **optional** RP-initiated central logout to `{PUBLIC}/logout` behind a flag (`SSO_CENTRAL_LOGOUT`). |
| D6 | Improvements over api-gateway reference | (a) **verify** the access-token HS256 signature at callback (gateway skips it); (b) use a **separate `SESSION_SECRET`** for the session cookie, not `JWT_SECRET` (gateway couples them). |

---

## 3. Architecture & flow

```
Browser                    redis-client-frontend (Next 16)              account-service
  GET / (no session) ─────► middleware: rcf_session missing
  ◄── 302 /auth/login
  GET /auth/login ────────► route(nodejs): verifier=rand(32)→b64url
                            challenge=b64url(SHA256(verifier)); state=rand(16)
                            Set-Cookie oauth_verifier, oauth_state (HttpOnly,Lax,~600s)
  ◄── 302 {PUBLIC}/authorize?response_type=code&client_id&redirect_uri
        &code_challenge&code_challenge_method=S256&state   (all URL-encoded)
  ──────────────────────────────────────────────────────────► Vue login form (8601)
  ◄────────────── 302 {redirect_uri}?code=&state= ────────────
  GET /auth/callback ─────► route(nodejs):
                            • code+state present? state == oauth_state cookie?
                            • POST {BASE}/token  (Basic client_id:secret;
                                grant_type=authorization_code, code,
                                redirect_uri, code_verifier)
                            ◄── { access_token }
                            • jose.jwtVerify(access_token, JWT_SECRET, HS256)
                            • email = claims.sub (fallback claims.email)
                            • email ∈ ADMIN_EMAILS?  ── no ──► 302 /auth/denied
                            • session = jose.SignJWT({email,name}, SESSION_SECRET, exp=+8h)
                            • Set-Cookie rcf_session (HttpOnly,Secure*,Lax,8h); clear PKCE cookies
  ◄── 302 /   (authed; middleware verifies rcf_session on every protected request)
```
`*Secure` gated by `SECURE_COOKIE` env (true in prod / HTTPS).

---

## 4. Components (file-by-file)

### New

- **`lib/auth/config.ts`** — single source of auth config, read + validated once.
  - `accountPublicUrl` (`ACCOUNT_PUBLIC_URL`), `accountBaseUrl` (`ACCOUNT_BASE_URL`).
  - `clientId` / `clientSecret` — prefer `ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND` /
    `ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND` (matching account-service's `SERVICE_NAME` →
    `ACCOUNT_CLIENT_ID_<SLUG>` convention), fall back to plain `ACCOUNT_CLIENT_ID` /
    `ACCOUNT_CLIENT_SECRET`.
  - `redirectUri` (`ACCOUNT_REDIRECT_URI`, e.g. `http://localhost:3551/auth/callback`).
  - `jwtSecret` (`JWT_SECRET`, verify account-service token), `sessionSecret` (`SESSION_SECRET`, sign our session).
  - `adminEmails` — parse `ADMIN_EMAILS` csv → normalized lowercase set.
  - `secureCookie` (`SECURE_COOKIE`), `sessionTtlSeconds` (`SESSION_TTL`, default 28800),
    `centralLogout` (`SSO_CENTRAL_LOGOUT`).
  - Fail fast with a clear error if a required var is missing.

- **`lib/auth/oauth.ts`** — OAuth/PKCE primitives (no framework coupling, unit-testable).
  - `generatePkce()` → `{ verifier, challenge }` using **Web Crypto** (`crypto.getRandomValues`,
    `crypto.subtle.digest('SHA-256')`) so it is portable; base64url-no-pad encoding.
  - `randomState()`.
  - `buildAuthorizeUrl({challenge, state})` → string, **all query params `encodeURIComponent`-ed**
    (fixes the api-gateway raw-concat bug).
  - `exchangeCode({code, verifier})` → `fetch(POST {BASE}/token)` with `Authorization: Basic …`
    and form body; returns the raw token JSON; throws typed errors on non-200 / network failure.
  - `verifyAndExtract(accessToken)` → `jose.jwtVerify` (HS256, `jwtSecret`, `verify_aud:false`);
    returns `{ email, name }`.

- **`lib/auth/session.ts`** — our own session cookie.
  - `createSessionCookie({email, name})` → signed `jose` JWT (`SESSION_SECRET`, HS256, `exp=+TTL`);
    returns cookie value + options (`name: 'rcf_session'`, `httpOnly`, `secure`, `sameSite:'lax'`, `path:'/'`, `maxAge`).
  - `readSession(token)` → verified claims or `null` (edge-compatible — used in middleware).
  - `SESSION_COOKIE = 'rcf_session'` exported constant.

- **`app/auth/login/route.ts`** — `export const runtime = 'nodejs'`; `GET` generates PKCE, sets the
  two PKCE cookies, 302 to the authorize URL.

- **`app/auth/callback/route.ts`** — `runtime = 'nodejs'`; `GET` runs the callback sequence in §3.
  Open-redirect-safe: only ever redirects to internal paths (`/`, `/auth/denied`).

- **`app/auth/logout/route.ts`** — `GET` deletes `rcf_session`; if `centralLogout` → 302 to
  `{PUBLIC}/logout?post_logout_redirect_uri=…` (the redirect target must also be registered on the
  client record); else redirect to `/auth/login`.

- **`app/auth/denied/page.tsx`** — static "Your account (`<email>`) is not authorized for the Redis
  manager. Contact an admin." + a sign-out link. (Email passed via a short-lived cookie or query, not the session.)

### Changed

- **`middleware.ts`** — rewrite. Read `rcf_session`, `readSession()`; valid → `NextResponse.next()`.
  Invalid/absent → POST (server actions) ⇒ `401 JSON`, GET ⇒ 302 `/auth/login`. Matcher excludes
  `_next/static`, `_next/image`, `favicon.ico`, `icon-*`, `apple-icon`, **and `/auth/*`** (login,
  callback, logout, denied must be reachable unauthenticated).

- **`components/cache-header.tsx`** — small addition: show the logged-in email and a "Sign out"
  link to `/auth/logout`. (Email read in `app/page.tsx` server component from the session and passed as a prop.)

- **`app/page.tsx`** — read session (server-side) to pass `email` to `CacheHeader`. No logic change to data fetch.

### Removed

- **`app/login/page.tsx`** — the paste-token page.
- All `ADMIN_TOKEN` references in `middleware.ts`.

### Dependencies

- Add **`jose`** (`^5`) to `package.json` — JWT sign/verify, works in both the Node route handlers
  and the Edge middleware runtime. No other new runtime deps (PKCE uses Web Crypto).

---

## 5. Config & infrastructure prerequisites

These are **required for the feature to work at all** and are part of the deliverable.

### 5.1 docker-compose (`docker-compose.yml`, redis-client-frontend block ~L1425)

- **Add `networks: [services-net]`** — **hard blocker**: today the service declares no network, so it
  lands on the default project network and **cannot resolve `account-service-backend:8600`** for the
  token exchange.
- Add env (api-gateway block as template):
  ```yaml
  environment:
    - REDIS_HOST=${REDIS_HOST}
    - REDIS_PORT=${REDIS_PORT}
    - REDIS_SECRET=${REDIS_SECRET}
    - SERVICE_NAME=redis-client-frontend
    - ACCOUNT_BASE_URL=${ACCOUNT_BASE_URL:-http://account-service-backend:8600}
    - ACCOUNT_PUBLIC_URL=${ACCOUNT_PUBLIC_URL:-http://localhost:8601}
    - ACCOUNT_REDIRECT_URI=${REDIS_CLIENT_REDIRECT_URI:-http://localhost:3551/auth/callback}
    - ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND=${ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND:-}
    - ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND=${ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND:-}
    - JWT_SECRET=${JWT_SECRET}
    - JWT_ALGO=${JWT_ALGO:-HS256}
    - SESSION_SECRET=${REDIS_CLIENT_SESSION_SECRET}
    - ADMIN_EMAILS=${REDIS_CLIENT_ADMIN_EMAILS}
    - SECURE_COOKIE=${ACCOUNT_SECURE_COOKIE:-false}
    - SESSION_TTL=${REDIS_CLIENT_SESSION_TTL:-28800}
    - SSO_CENTRAL_LOGOUT=${REDIS_CLIENT_CENTRAL_LOGOUT:-false}
  networks:
    - services-net
  ```

### 5.2 Register the OAuth client in account-service

`POST {ACCOUNT_BASE_URL}/api/v1/admin/services` (authenticated) with:
```json
{
  "name": "redis-client-frontend",
  "redirect_uris": ["http://localhost:3551/auth/callback", "https://<prod-host>/auth/callback"],
  "description": "Redis cache manager admin UI"
}
```
Capture the returned `client_id` / `client_secret` (shown once) into the env vars above
(secrets manager / `.env`, never committed). Every callback origin (dev + prod) must be listed
exactly. If `SSO_CENTRAL_LOGOUT=true`, also register the post-logout redirect URL.

### 5.3 Public origin / redirect_uri

The app's public origin is **`:3551`** in dev (compose maps `3551→3000`). `redirect_uri` is built from
the explicit `ACCOUNT_REDIRECT_URI` env (not from the request host), so it always matches the
registered value. Prod origin is **[to confirm at deploy]** and must be registered before go-live.

---

## 6. Error handling

| Condition | Response |
|-----------|----------|
| `/auth/callback` missing `code`/`state` | 400 |
| `state` ≠ `oauth_state` cookie, or verifier cookie missing | 400 (possible CSRF / expired PKCE) |
| `/token` non-200 or network error | log (redact secrets) → 302 `/auth/login?error=exchange` |
| access-token signature invalid / expired at callback | 401 → `/auth/login?error=token` |
| email not in `ADMIN_EMAILS` | 302 `/auth/denied` |
| account-service unreachable | 502 page with retry guidance |
| Required env var missing at startup | hard fail with explicit message |

All logs redact `client_secret`, tokens, `Authorization`. Server actions (`cache-actions.ts`) remain
protected because middleware returns 401 on unauthenticated POST — no logic change needed there.

---

## 7. Security notes

- Session cookie: `HttpOnly`, `Secure` (prod via `SECURE_COOKIE`), `SameSite=Lax`, `Path=/`, 8h `maxAge`.
- PKCE cookies: `HttpOnly`, `SameSite=Lax`, short `maxAge` (~600s), deleted on successful callback.
- Verify the account-service token signature (HS256/`JWT_SECRET`) at callback — do not trust an unverified payload.
- `SESSION_SECRET` is independent of `JWT_SECRET`; rotating one does not weaken the other.
- Authorize-URL params are URL-encoded.
- Callback redirects restricted to internal paths (no open redirect).
- `ADMIN_EMAILS` compared case-insensitively against the normalized `sub`/`email` claim.
- The destructive `FLUSHDB` ("Clear All") remains gated behind both SSO + allow-list now; consider
  (out of scope here) a future confirmation that names the shared blast radius.

---

## 8. Testing

Frontend is local-runnable (`pnpm build`/`pnpm lint`). Add **`vitest`** (no test setup exists yet) for:

- `lib/auth/oauth.ts`: PKCE — `challenge === b64url(SHA256(verifier))`; authorize URL is correctly
  encoded and contains all required params; `verifyAndExtract` accepts a valid HS256 token and
  rejects a tampered/expired one; `exchangeCode` builds the Basic header + form body correctly (mock `fetch`).
- `lib/auth/session.ts`: sign→verify round-trip; expired session → `null`; tampered token → `null`.
- `lib/auth/config.ts`: client-id resolution precedence (prefixed over plain); `ADMIN_EMAILS` parsing/normalization.

Manual E2E against a running account-service (remote / dev compose): full login → allowed → denied →
logout. Integration with a live account-service cannot run in CI (remote dependency).

---

## 9. Out of scope (v1)

- Silent token refresh using the 30d refresh token (D2 deferred).
- Role-based authorization via account-service `AllowedRoles` (token emits no role claims by default;
  would need an account-service backend change).
- Making the `/auth/logout-webhook` back-channel logout effective (needs a server-side session store;
  our session is a stateless signed cookie).
- Any change to the Redis browsing/mutation logic itself.

---

## 10. Open questions / to confirm at implementation

- **Prod public origin** of redis-client-frontend (for the registered `redirect_uri`) — unknown from the repo.
- Whether to raise the account-service client's `token_ttl_s` above 60s — **not needed** given D2
  (we mint our own session and only read the token once at callback).
- TDD gate: the project's `tdd-gate.sh` hook may require test files alongside new `lib/auth/*` —
  the plan should create tests first (aligns with §8).
