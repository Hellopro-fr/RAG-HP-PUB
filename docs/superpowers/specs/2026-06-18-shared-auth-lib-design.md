# Design — shared account-service auth lib (`libs/auth/{node,python}`)

- **Date:** 2026-06-18
- **Goal:** Extract the account-service OAuth 2.1 + PKCE login core into reusable, language-partitioned shared libraries so any Node or Python service can add SSO login without re-implementing the flow.
- **Status:** Approved design (brainstorming). Next: implementation plan.
- **Related:** `docs/superpowers/specs/2026-06-18-redis-client-frontend-login-design.md` (the original SSO feature, now the extraction source).

---

## 1. Context

The account-service OAuth 2.1 + PKCE login was first built inside `redis-client-frontend` (`apps-microservices/redis-client-frontend/lib/auth/*`). It is already framework-free and `SERVICE_NAME`-driven (credential keys derived at runtime, mirroring `libs/account-client-go` `DeriveEnvKeys` and `libs/common-utils/src/common_utils/sso`). Making it a shared lib lets future services reuse it.

**Existing packaging precedents in the monorepo:**
- Python: services build from **repo-root Docker context** and `COPY libs/common-utils /app/libs/common-utils && pip install -e /app/libs/common-utils` (e.g. `apps-microservices/api-classification/Dockerfile:13-14`).
- Go: `libs/account-client-go` flat package.
- Node: **no precedent** — no `pnpm-workspace.yaml`, no service consumes a local lib. `redis-client-frontend` currently builds from a per-service context (`context: ./apps-microservices/redis-client-frontend`).

**Credential resolution already shared:** `common_utils.sso` (Python) + `account-client-go` (Go). The **login flow** (PKCE gen, authorize URL, token exchange, verify, session, orchestration) is NOT shared — it lives in `redis-client-frontend/lib/auth` (TS) and `api-gateway/app/routers/sso.py` (Python, FastAPI-coupled).

---

## 2. Decisions (locked in brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Structure | Two sibling framework-free packages under `libs/auth/`: `node/` and `python/`. |
| D2 | Build both now? | **Yes** — build node + python. (Python has no live consumer yet; built + tested, ready for the next Python login service.) |
| D3 | Node consumption | Repo-root Docker context + `package.json` `file:` dependency + `next.config` `transpilePackages` (raw TS, no build step). Mirrors the common-utils precedent. |
| D4 | Extraction line | **Core only** in the lib (config, oauth, session, flow). Framework wiring (Next route handlers + middleware; FastAPI routes) stays per-service. Keeps the lib framework-agnostic. |
| D5 | First node consumer | `redis-client-frontend` migrates to consume `@hellopro/auth` (proves the lib). |
| D6 | api-gateway | **NOT migrated.** Its working `sso.py` stays. Migrating a live auth path = separate later task. |
| D7 | Python credentials | Reuse existing `common_utils.sso` (import, don't duplicate). |
| D8 | Naming | node `@hellopro/auth`; python distribution `hellopro-auth`, import package `hellopro_auth`. |

---

## 3. Architecture

```
libs/auth/
  node/                      # TS package "@hellopro/auth"
    package.json             # name, exports -> ./src/index.ts, dep: jose ^5
    tsconfig.json
    vitest.config.ts
    README.md
    src/
      config.ts              # deriveClientEnvKeys, resolveClientCredentials, getAuthConfig, AuthConfig
      oauth.ts               # generatePkce, randomState, buildAuthorizeUrl, exchangeCode, verifyAndExtract
      session.ts             # createSessionToken, readSession, SESSION_COOKIE, SessionClaims
      flow.ts                # startLogin, completeCallback, LoginStart, CallbackResult
      index.ts               # barrel: re-export public API
      *.test.ts              # the 35 relocated vitest tests
  python/                    # package "hellopro-auth" (import: hellopro_auth)
    pyproject.toml
    README.md
    hellopro_auth/
      __init__.py            # re-export public API
      config.py              # AuthConfig + resolve_client_credentials (reuses common_utils.sso)
      oauth.py               # gen_pkce, build_authorize_url, exchange_code, verify_and_extract
      session.py             # create_session_token, read_session, SESSION_COOKIE
      flow.py                # start_login, complete_callback
    tests/                   # pytest mirroring the node cases
```

Each service keeps its thin, framework-specific wiring and imports the core from the lib.

---

## 4. `libs/auth/node`

### 4.1 Package
- `package.json`: `"name": "@hellopro/auth"`, `"version": "0.1.0"`, `"private": true`, `"type": "module"`, `"exports": { ".": "./src/index.ts" }`, `"dependencies": { "jose": "^5.9.6" }`, `"devDependencies": { "vitest": "^2.1.8" }`, scripts `test`/`test:watch`. No build step — consumers transpile via `transpilePackages`.
- `tsconfig.json`: strict, `moduleResolution: bundler`, targets matching redis-client-frontend.
- `src/index.ts` re-exports the full public API (below).
- `vitest.config.ts`: node environment.

### 4.2 Contents (moved verbatim from `redis-client-frontend/lib/auth/`)
`config.ts`, `oauth.ts`, `session.ts`, `flow.ts` + their `*.test.ts` move unchanged (already framework-free, `SERVICE_NAME`-driven). Internal relative imports (`./config`, etc.) stay valid.

**Public API (`index.ts`):**
- config: `deriveClientEnvKeys`, `resolveClientCredentials`, `getAuthConfig`, `parseAdminEmails`, type `AuthConfig`
- oauth: `generatePkce`, `randomState`, `buildAuthorizeUrl`, `exchangeCode`, `verifyAndExtract`, types `Pkce`, `TokenResponse`, `Identity`
- session: `createSessionToken`, `readSession`, `SESSION_COOKIE`, type `SessionClaims`
- flow: `startLogin`, `completeCallback`, types `LoginStart`, `CallbackResult`

### 4.3 Tests
The 35 vitest tests relocate with the source and run via `node_modules/.bin/vitest run` inside the lib. Same behavior; no new cases required for the move (the SERVICE_NAME-derivation cases already exist).

---

## 5. `redis-client-frontend` migration (first consumer)

### 5.1 Code
- **Delete** `apps-microservices/redis-client-frontend/lib/auth/` (all 8 files).
- `package.json`: add `"@hellopro/auth": "file:../../libs/auth/node"`; keep `jose` (still used indirectly, but the dep now lives in the lib — remove from the service if nothing else imports it directly). Run `pnpm install` to relink.
- `next.config.mjs`: add `transpilePackages: ["@hellopro/auth"]`.
- Repoint imports from `@/lib/auth/{session,flow,config}` → `@hellopro/auth` in: `middleware.ts`, `app/auth/login/route.ts`, `app/auth/callback/route.ts`, `app/auth/logout/route.ts`, `app/page.tsx`.

### 5.2 Docker (the load-bearing change)
- `Dockerfile`: change so `pnpm install` sees the lib. Build from **repo-root context**; COPY both `libs/auth/node` and `apps-microservices/redis-client-frontend` preserving relative paths (so `file:../../libs/auth/node` resolves), then `pnpm install` → build → standalone runner (unchanged).
- `docker-compose.yml` `redis-client-frontend`: `build.context: .`, `build.dockerfile: apps-microservices/redis-client-frontend/Dockerfile`. Keep ports/env/networks/profiles.
- Root `.dockerignore`: ensure the repo-root context excludes `node_modules`, `.next`, `.git`, other services' bulk, so the context stays lean.

### 5.3 Result
The service keeps only its thin Next wiring (`app/auth/*` routes, `middleware.ts`, header UI). All auth logic lives in `@hellopro/auth`. `.env` + runtime behavior unchanged.

---

## 6. `libs/auth/python`

### 6.1 Package (mirrors common-utils packaging)
- `pyproject.toml`: distribution `hellopro-auth`, import package `hellopro_auth`, deps `PyJWT`, `httpx`; optional dep on `common-utils` for credential resolution (or path-install alongside).
- Installed by consumers via the common-utils pattern: repo-root context, `COPY libs/auth/python /app/libs/auth/python && pip install -e /app/libs/auth/python`.

### 6.2 Contents (extracted + generalized from `api-gateway/app/routers/sso.py`)
Framework-free functions, parity with the node core:
- `config.py`: `AuthConfig` dataclass + `resolve_client_credentials()` that **delegates to `common_utils.sso`** (`get_account_credentials` / `derive_env_keys`) plus reads `ACCOUNT_BASE_URL`, `ACCOUNT_PUBLIC_URL`, `ACCOUNT_REDIRECT_URI`, `JWT_SECRET`, `SESSION_SECRET`, `ADMIN_EMAILS`, `SECURE_COOKIE`, `SESSION_TTL`, `SSO_CENTRAL_LOGOUT`.
- `oauth.py`: `gen_pkce()` (`secrets.token_bytes` + `hashlib.sha256`, base64url-no-pad), `random_state()`, `build_authorize_url()` (**URL-encoded** — fixes the raw-concat in sso.py), `exchange_code()` (httpx POST `{base}/token`, HTTP Basic client auth, form body), `verify_and_extract()` (PyJWT HS256, `verify_aud=False`, email from `sub`/`email`).
- `session.py`: `create_session_token()` / `read_session()` — HS256 JWT signed with `SESSION_SECRET` (PyJWT), `SESSION_COOKIE = "rcf_session"` (or a configurable name), 8h default.
- `flow.py`: `start_login()` → `{authorize_url, verifier, state, secure_cookie}`; `complete_callback(code, state, state_cookie, verifier_cookie)` → discriminated result (`ok` / `denied` / `error`) with the same guard order + allow-list as the node `completeCallback`.

### 6.3 Parity contract
Same env-var convention (`ACCOUNT_CLIENT_ID_<SLUG(SERVICE_NAME)>`), same PKCE S256, same claim handling, same session TTL semantics → a Node service and a Python service behave identically against account-service. **api-gateway is not touched.**

---

## 7. Testing

- **node:** the 35 relocated vitest tests run in `libs/auth/node`. `redis-client-frontend` keeps a build smoke (`next build` / `tsc --noEmit` clean on its own files).
- **python:** pytest in `libs/auth/python/tests/` mirroring the node cases:
  - `oauth`: `gen_pkce` challenge == b64url(sha256(verifier)); authorize URL encodes params + `S256`; `exchange_code` sends Basic + form (monkeypatch httpx); `verify_and_extract` accepts valid HS256 / rejects wrong-secret.
  - `session`: sign→read round-trip; expired → None; garbage → None.
  - `config`: `derive_env_keys` slug parity; allow-list parsing.
  - `flow`: `start_login` shape; `complete_callback` error/denied/ok branches.

---

## 8. Out of scope (YAGNI)

- Migrating api-gateway to `hellopro-auth` (defer; keep the live auth path stable).
- Publishing to a private npm/PyPI registry (`file:` dep / `pip install -e` suffice).
- Next-specific helper factories (middleware/route factories) — core only (D4).
- A Go arm — `account-client-go` already covers Go credential needs; no Go login-flow consumer requested.

---

## 9. Risks / must-verify on build

1. **Docker context switch (redis-client-frontend)** — the `file:` dep + `transpilePackages` + repo-root context chain is the load-bearing change and cannot be fully verified without the VM build. Must confirm: root `.dockerignore` keeps the context lean, `pnpm install` resolves `file:../../libs/auth/node`, and the standalone `next build` still succeeds.
2. **`file:` + raw-TS exports** — Next must transpile the linked package's TS (`transpilePackages`); verify no "module not found / cannot use import outside a module" at build.
3. **Python lib unused at first** — no runtime consumer until the next Python login service adopts it; its correctness rests on the pytest suite alone until then.
4. **common-utils coupling (python)** — `hellopro_auth.config` importing `common_utils.sso` means a Python consumer must install both libs (already the norm — most Python services install common-utils).

---

## 10. Suggested implementation phases (for the plan)

- **Phase A — node lib + redis-client-frontend migration** (the validated, shippable deliverable): create `libs/auth/node`, move code+tests, migrate the service (imports + Docker context), verify build.
- **Phase B — python lib** (build + test, no live consumer): create `libs/auth/python`, extract from sso.py, pytest.

Phases are independent; Phase A is the priority (it proves the pattern end-to-end).
