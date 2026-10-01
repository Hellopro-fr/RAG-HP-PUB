# Design — internal-credentials fetch fallback for the shared auth lib

- **Date:** 2026-06-18
- **Scope:** `libs/auth/node` (`@hellopro/auth`) + `libs/auth/python` (`hellopro-auth`) + `redis-client-frontend` compose env.
- **Goal:** Let a consuming service resolve its account-service OAuth client credentials from account-service's MySQL (via the admin-token-gated internal endpoint) instead of requiring the per-service `client_id`/`client_secret` in env — matching how `mcp-gateway` (Go) and other fleet services already work.
- **Status:** Approved design (Approach A). Next: implementation plan.
- **Related:** `docs/superpowers/specs/2026-06-18-shared-auth-lib-design.md` (the lib this extends).

---

## 1. Context

`mcp-gateway` and other fleet services resolve their OAuth client credentials at runtime from account-service: `account-client-go` `GetCredentialsFromAPI` (Go) and `common_utils.sso.get_account_client_from_api` (Python) call `GET {ACCOUNT_BASE_URL}/internal/credentials/{SERVICE_NAME}` with an `X-Admin-Token: ACCOUNT_INTERNAL_TOKEN` header. account-service looks the client up in its `oauth2_clients` MySQL table, decrypts the secret server-side, and returns `{client_id, client_secret}`. So those services set only `SERVICE_NAME` + `ACCOUNT_INTERNAL_TOKEN` — no per-service secret in env.

The shared auth lib built earlier (`@hellopro/auth` node + `hellopro-auth` python) resolves credentials **env-only** (`ACCOUNT_CLIENT_ID_<SLUG>` + plain fallback, else raise). The internal-API fetch was deliberately deferred (YAGNI, based on api-gateway's explicit-env example). `mcp-gateway` shows the fleet standard is the MySQL/API-fetch mode, so `redis-client-frontend` currently needs a per-service secret in `.env` that no other service does. This adds the fetch fallback.

**Call sites (why the ripple is bounded):** `getAuthConfig`/`get_auth_config` is called only in `flow.{ts,py}` (`startLogin`/`completeCallback`) and the node logout route. `resolveClientCredentials`/`get_account_credentials` is called only inside `getAuthConfig`. All node call sites are already async; the two python sites are sync today but their callers are async FastAPI handlers.

---

## 2. Decision (Approach A, approved)

Make credential resolution **async with an env-first, then internal-API-fetch fallback, memoized per process**. `getAuthConfig`/`get_auth_config` become async (mechanical `await` at the ≤5 call sites, all already async or trivially made so). No `AuthConfig` reshape — `client_id`/`client_secret` stay fields.

Rejected **Approach D** (keep `getAuthConfig` sync + a separate async cred resolver): would force removing creds from `AuthConfig` and rewiring `flow.ts`, more surgery for no gain since all callers are async.

---

## 3. node — `@hellopro/auth`

### 3.1 `resolveClientCredentials` → async, with fetch fallback
```
async resolveClientCredentials(env = process.env):
  1. serviceName-derived env pair (ACCOUNT_CLIENT_ID_<SLUG> / _SECRET) → return
  2. plain ACCOUNT_CLIENT_ID / ACCOUNT_CLIENT_SECRET → return
  3. NEW: if env.ACCOUNT_INTERNAL_TOKEN set:
       return await fetchClientCredentialsFromApi(baseUrl, serviceName, internalToken)  # memoized
  4. else throw (same message)
```
- New `fetchClientCredentialsFromApi(baseUrl, serviceName, token)`: `fetch(GET {baseUrl}/internal/credentials/{encodeURIComponent(serviceName)}, headers {"X-Admin-Token": token})`; on 404 → throw "no active service named…"; non-200 → throw with status; parse `{client_id, client_secret}`; throw if either missing. Mirrors `account-client-go` `credentials_api.go`.
- **Memoization:** module-level cache of the fetched pair (keyed by serviceName), populated on first successful fetch. Mirrors `account-client-go`'s `_cached_client`. A `__resetCredentialsCacheForTests()` export (or equivalent) resets it so tests are isolated. Env-path (steps 1–2) is not memoized (cheap, deterministic).

### 3.2 `getAuthConfig` → async
`const { clientId, clientSecret } = await resolveClientCredentials(env)`. Rest unchanged. Return type `Promise<AuthConfig>`.

### 3.3 Config
Read `ACCOUNT_INTERNAL_TOKEN` from env inside `resolveClientCredentials` (and `ACCOUNT_BASE_URL`, already read by `getAuthConfig`; pass it in). No new `AuthConfig` field required (internal token is only used during resolution).

### 3.4 Callers
- `flow.ts`: `const cfg = await getAuthConfig()` in `startLogin` + `completeCallback` (both already async).
- `app/auth/logout/route.ts`: `const cfg = await getAuthConfig()` (already an async GET handler).

### 3.5 Edge-safety
`getAuthConfig` is never called in `middleware.ts` (edge) — it uses `readSession` only. The `fetch` therefore never runs on the edge runtime. `fetch` is edge-safe regardless.

---

## 4. python — `hellopro-auth`

### 4.1 `get_auth_config` → async
```
async def get_auth_config():
    try:
        client_id, client_secret = get_account_credentials()        # sync, env-only (common_utils.sso)
    except AccountCredentialsMissing:
        if os.environ.get("ACCOUNT_INTERNAL_TOKEN"):
            client_id, client_secret = await _cached_fetch()        # get_account_credentials_from_api (common_utils.sso)
        else:
            raise
    ... (rest unchanged)
```
- Reuses `common_utils.sso.get_account_credentials` (env) + `get_account_credentials_from_api` (async API fetch) — **near-zero new code**, just orchestration + memo.
- **Memoization:** module-level cache of the fetched pair, reset hook for tests.

### 4.2 Callers
`flow.py` `start_login`/`complete_callback` → `async def`, `cfg = await get_auth_config()`. FastAPI consumers (per-service) already `await` route handlers.

---

## 5. redis-client-frontend

### 5.1 compose env
Add to the `redis-client-frontend` service `environment` block:
```yaml
- ACCOUNT_INTERNAL_TOKEN=${ACCOUNT_INTERNAL_TOKEN:-}
```
The `ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND` / `_SECRET` lines stay (env still wins if set) but become **optional** — with `ACCOUNT_INTERNAL_TOKEN` set and the client registered in account-service, the fetch resolves them.

### 5.2 `.env.example` + CLAUDE.md
Document both modes: (a) explicit env creds, or (b) `ACCOUNT_INTERNAL_TOKEN` + registered client (no per-service secret). Note env wins when both present.

---

## 6. Precedence & compatibility

Env creds → **win** (services with explicit `ACCOUNT_CLIENT_ID_<SLUG>` set behave exactly as before — byte-compatible). Only when env creds are absent AND `ACCOUNT_INTERNAL_TOKEN` is present does the fetch run. When neither → same error as today. So the change is additive; no existing behavior changes.

---

## 7. Testing

- **node:** `config.test.ts` — convert `getAuthConfig` cases to `await`; keep env-path `resolveClientCredentials` cases (now `await`); ADD a fetch-fallback test (stub global `fetch`: env absent + `ACCOUNT_INTERNAL_TOKEN` set → returns `{client_id, client_secret}`; assert; and a 404/non-200 → throws). `flow.test.ts` — `getAuthConfig` mock returns a resolved Promise. Reset the memo between tests.
- **python:** `test_config.py`/`test_flow.py` → `pytest-asyncio` (`@pytest.mark.asyncio`, already installed). Env-path cases `await get_auth_config()`. ADD a fetch-fallback test monkeypatching `common_utils.sso.get_account_credentials_from_api`. Reset memo between tests. `test_flow.py` monkeypatch of `get_auth_config` returns an awaitable.

---

## 8. Out of scope (YAGNI)

- Migrating other services (api-gateway etc.) — untouched.
- Refresh/rotation of fetched creds beyond first-fetch memo (account-service creds are stable; process restart re-fetches).
- Any `AuthConfig` field for the internal token (used only transiently during resolution).

---

## 9. Risks

1. **Async conversion churn** — `getAuthConfig`/`resolveClientCredentials` (node) + `get_auth_config`/flow (python) + their tests flip to async. Mechanical but touches the just-merged lib; full test re-run required (node 34→~36, python 28→~30).
2. **Memoization correctness** — a stale/wrong first fetch would be cached process-wide. Mitigate: only memo on success; reset hook for tests; per-serviceName key.
3. **VM-only** — the actual fetch against a live account-service `/internal/credentials` + `ACCOUNT_INTERNAL_TOKEN` is verified on the VM; unit tests stub the HTTP.
4. **`ACCOUNT_INTERNAL_TOKEN` is a high-value secret** (admin-gated) — it's already fleet-shared; just ensure it's not logged (the fetch code must not log the token).
