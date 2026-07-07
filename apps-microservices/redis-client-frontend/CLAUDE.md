# redis-client-frontend

Web UI for browsing and managing Redis cache entries.

## Tech Stack

- **Framework:** Next.js 16 (React 19, TypeScript)
- **UI:** Radix UI (alert-dialog, slot, toast), Tailwind CSS 4, shadcn/ui
- **Redis:** `redis` npm package (v4)
- **Package Manager:** pnpm

## Commands

| Action | Command |
|--------|---------|
| Dev | `pnpm dev` |
| Build | `pnpm build` |
| Start | `pnpm start` |
| Lint | `pnpm lint` (eslint) |

## Docker

- Multi-stage pnpm build, standalone output
- Port: **3000**
- Non-root user (`nextjs:nodejs`)

## Folder Structure

```
app/
  page.tsx                    # Main Redis browser page (Server Component)
  layout.tsx
  globals.css
  auth/
    login/route.ts            # GET — initiates OAuth PKCE flow → redirect to account-service
    callback/route.ts         # GET — receives authorization code, exchanges for token, sets session
    logout/route.ts           # GET — clears session cookie (+ optional RP-logout at account-service)
    denied/page.tsx           # Shown when email is not in ADMIN_EMAILS allow-list
  actions/
    cache-actions.ts          # Server actions for Redis mutations
middleware.ts                 # Auth middleware — gates all routes on rcf_session cookie
components/                   # UI components (cache-header, cache-table, confirm-dialog)
hooks/
lib/
  auth/
    config.ts                 # Reads and validates all SSO env vars
    oauth.ts                  # PKCE S256 gen, authorize URL, token exchange, HS256 token verify
    session.ts                # Sign/verify rcf_session cookie (HS256 via SESSION_SECRET)
    flow.ts                   # startLogin/completeCallback orchestration (framework-free)
  domain/cache-entry.ts      # CacheEntry + CacheMetadata interfaces
  infrastructure/             # Redis repository (Singleton + SCAN)
  application/                # getCachedData use case (parallel fetches)
  utils.ts                    # cn(), formatBytes()
public/
```

## Conventions

- `output: 'standalone'` in next.config.mjs
- TypeScript build errors are enforced (`ignoreBuildErrors: false`)
- Redis uses `SCAN` (not `KEYS *`) for non-blocking key enumeration
- **Authentication via account-service SSO (OAuth 2.1 + PKCE S256):**
  - `middleware.ts` gates every route on a signed `rcf_session` cookie (HS256, `SESSION_SECRET`).
  - Unauthenticated GET → `/auth/login` → account-service `/authorize` (PKCE S256, `code_challenge_method=S256`).
  - account-service redirects to `/auth/callback` with the authorization code; the app exchanges it for a JWT at `{ACCOUNT_BASE_URL}/token` (HTTP Basic client auth), verifies the JWT with `JWT_SECRET` (HS256), then sets the 8h `rcf_session` cookie.
  - Authorization: signed-in email must be in the `ADMIN_EMAILS` allow-list; non-allow-listed emails are redirected to `/auth/denied`.
  - Sign out via `/auth/logout` — clears the `rcf_session` cookie; if `SSO_CENTRAL_LOGOUT=true`, also calls account-service RP-logout endpoint.
  - **The old `ADMIN_TOKEN` paste-login page (`app/login/`) has been removed.**
- Server actions validate key format before Redis operations
- Shared `formatBytes()` utility in `lib/utils.ts`

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `REDIS_HOST` | Yes | Redis server hostname |
| `REDIS_PORT` | Yes | Redis server port |
| `REDIS_SECRET` | Yes | Redis password |
| `SERVICE_NAME` | Yes | Identifies this service to account-service (`redis-client-frontend`) |
| `ACCOUNT_BASE_URL` | Yes | Server-to-server URL for token exchange (e.g. `http://account-service-backend:8600`) |
| `ACCOUNT_PUBLIC_URL` | Yes | Browser-facing base URL for `/authorize` redirect (e.g. `http://localhost:8601`) |
| `ACCOUNT_REDIRECT_URI` | Yes | Callback URL registered on the OAuth client (e.g. `http://localhost:3551/auth/callback`) |
| `ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND` | Yes | OAuth client ID — obtained at client registration |
| `ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND` | Yes | OAuth client secret — shown once at registration |
| `JWT_SECRET` | Yes | Shared HS256 secret to verify account-service access tokens |
| `SESSION_SECRET` | Yes | Independent secret used to sign/verify the `rcf_session` cookie |
| `ADMIN_EMAILS` | Yes | Comma-separated email allow-list (e.g. `alice@hellopro.fr,bob@hellopro.fr`) |
| `SECURE_COOKIE` | No | Set `true` in prod behind HTTPS (default: `false`) |
| `SESSION_TTL` | No | Session lifetime in seconds (default: `28800` = 8h) |
| `SSO_CENTRAL_LOGOUT` | No | `true` to also RP-logout at account-service on sign-out (default: `false`) |

> When running via root `docker-compose`, several of these vars are sourced from namespaced host keys (`REDIS_CLIENT_*` / `ACCOUNT_SECURE_COOKIE`). See `.env.example` for the exact mapping.

## account-service client registration

Before the SSO flow works, register `redis-client-frontend` as an OAuth client on the account-service.

**Option A — Vue admin UI:** Open `{ACCOUNT_PUBLIC_URL}` → "Services" page → "Add service". Fill in:
- **Name:** `redis-client-frontend`
- **Redirect URIs:** `http://localhost:3551/auth/callback` (add prod URL alongside in production)

**Option B — API:**
```bash
curl -X POST "{ACCOUNT_BASE_URL}/api/v1/admin/services" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "redis-client-frontend",
    "redirect_uris": [
      "http://localhost:3551/auth/callback",
      "https://<prod-domain>/auth/callback"
    ]
  }'
```

The response returns `client_id` and `client_secret` (shown **once**). Copy them into:
```
ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND=<client_id>
ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND=<client_secret>
```

## Manual E2E Checklist

After deploying with the env vars set:

- [ ] `GET http://localhost:3551/` → redirected to `/auth/login` (not the Redis browser page)
- [ ] `/auth/login` → redirected to account-service `/authorize` URL (check browser address bar)
- [ ] Sign in with an email in `ADMIN_EMAILS` → lands on Redis browser page; email visible in header
- [ ] Sign in with an email **not** in `ADMIN_EMAILS` → redirected to `/auth/denied`
- [ ] `/auth/logout` → session cookie cleared; subsequent `GET /` redirects to `/auth/login`
- [ ] With `SSO_CENTRAL_LOGOUT=true`: logout also invalidates the session at account-service

## Dependencies

- **Redis** server (connection via `redis` npm package)
