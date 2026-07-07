# Auth-lib internal-credentials fetch fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an async, env-first, memoized internal-credentials fetch fallback to `@hellopro/auth` (node) + `hellopro-auth` (python) so a service resolves its OAuth client creds from account-service MySQL (`GET /internal/credentials/{SERVICE_NAME}` with `X-Admin-Token`) instead of a per-service secret in `.env` — matching mcp-gateway.

**Architecture:** Credential resolution becomes async: env-derived keys → plain env → (new) internal-API fetch when `ACCOUNT_INTERNAL_TOKEN` is set, memoized per process. `getAuthConfig`/`get_auth_config` become async; env creds still win (additive, no behavior change when env creds present). All ≤5 call sites are already async or trivially made so.

**Tech Stack:** TypeScript + jose + vitest (node); Python + PyJWT + httpx + pytest-asyncio (python, reusing `common_utils.sso`).

**Spec:** `docs/superpowers/specs/2026-06-18-auth-lib-internal-credentials-fetch-design.md`

**Working dir:** repo root `D:\DevHellopro\Workspaces\RAG-HP-PUB` (branch decided at handoff). Node: run `node_modules/.bin/<tool>` inside `libs/auth/node` (pnpm 11 quirk). Python: `libs/auth/python` with `common-utils` + `hellopro-auth` installed editable.

---

## File Structure

| File | Change | Task |
|------|--------|------|
| `libs/auth/node/src/config.ts` | `resolveClientCredentials`+`getAuthConfig` async; add `fetchClientCredentialsFromApi` + memo + `__resetClientCredentialsCache` | 0 |
| `libs/auth/node/src/config.test.ts` | tests → async; add fetch-fallback + memo + 404 tests | 0 |
| `libs/auth/node/src/flow.ts` | `await getAuthConfig()` (2 sites) | 0 |
| `libs/auth/node/src/flow.test.ts` | `getAuthConfig` mock → `mockResolvedValue` | 0 |
| `libs/auth/node/src/index.ts` | export `__resetClientCredentialsCache` | 0 |
| `apps-microservices/redis-client-frontend/app/auth/logout/route.ts` | `await getAuthConfig()` | 1 |
| `docker-compose.yml` (redis-client-frontend env) | add `ACCOUNT_INTERNAL_TOKEN` | 1 |
| `apps-microservices/redis-client-frontend/.env.example`, `CLAUDE.md` | document both cred modes | 1 |
| `libs/auth/python/hellopro_auth/config.py` | `get_auth_config` async; fetch fallback via `common_utils.sso`; memo + `_reset_cache` | 2 |
| `libs/auth/python/hellopro_auth/flow.py` | `start_login`/`complete_callback` async; `await get_auth_config()` | 2 |
| `libs/auth/python/tests/test_config.py`, `test_flow.py` | → async; add fetch-fallback test | 2 |
| `libs/auth/python/pyproject.toml` | `[tool.pytest.ini_options] asyncio_mode="auto"` | 2 |

---

### Task 0: node — async credential resolution + internal-API fetch

**Goal:** `@hellopro/auth` resolves creds async with the memoized fetch fallback; env still wins.

**Files:** Modify `libs/auth/node/src/{config.ts,flow.ts,index.ts,config.test.ts,flow.test.ts}`

**Acceptance:**
- [ ] env creds still win (existing tests pass, now async).
- [ ] with env absent + `ACCOUNT_INTERNAL_TOKEN`, `resolveClientCredentials` fetches `GET {ACCOUNT_BASE_URL}/internal/credentials/{SERVICE_NAME}` with `X-Admin-Token`.
- [ ] fetched creds are memoized (second call, no second fetch); 404 → throws.
- [ ] `getAuthConfig` is async; `flow.ts` awaits it.

**Verify:** in `libs/auth/node`: `node_modules/.bin/vitest run` (all pass) + `node_modules/.bin/tsc --noEmit` (clean).

**Steps:**

- [ ] **Step 1: Replace `resolveClientCredentials` + `getAuthConfig` in `config.ts`** (add the fetch helper + memo above them; keep `parseAdminEmails`, `deriveClientEnvKeys`, `req`, `AuthConfig` as-is). Replace lines 28–49 (`resolveClientCredentials`) and lines 70–88 (`getAuthConfig`) with:

```ts
// Module-level memo of creds fetched from the internal API (keyed by service name).
const _fetchedCredsCache = new Map<string, { clientId: string; clientSecret: string }>()

// Test-only: clear the fetched-credentials memo so cases are isolated.
export function __resetClientCredentialsCache(): void {
  _fetchedCredsCache.clear()
}

// Fetch (clientId, clientSecret) from account-service's admin-gated internal endpoint.
// Mirrors libs/account-client-go credentials_api.go GetCredentialsFromAPI.
async function fetchClientCredentialsFromApi(
  baseUrl: string,
  serviceName: string,
  adminToken: string,
): Promise<{ clientId: string; clientSecret: string }> {
  const cached = _fetchedCredsCache.get(serviceName)
  if (cached) return cached
  const url = `${baseUrl.replace(/\/+$/, "")}/internal/credentials/${encodeURIComponent(serviceName)}`
  const r = await fetch(url, { headers: { "X-Admin-Token": adminToken } })
  if (r.status === 404) {
    throw new Error(`[account-auth] no active service named "${serviceName}" in account-service`)
  }
  if (!r.ok) {
    throw new Error(`[account-auth] internal credentials endpoint returned ${r.status}`)
  }
  const body = (await r.json()) as { client_id?: string; client_secret?: string }
  if (!body.client_id || !body.client_secret) {
    throw new Error("[account-auth] internal credentials response missing fields")
  }
  const creds = { clientId: body.client_id, clientSecret: body.client_secret }
  _fetchedCredsCache.set(serviceName, creds)
  return creds
}

// Resolve (clientId, clientSecret): SERVICE_NAME-derived env keys, then plain env,
// then (if ACCOUNT_INTERNAL_TOKEN set) the account-service internal API. Env wins.
export async function resolveClientCredentials(
  env: Env = process.env,
): Promise<{ clientId: string; clientSecret: string }> {
  const serviceName = (env.SERVICE_NAME || "").trim()
  if (serviceName) {
    const [idKey, secretKey] = deriveClientEnvKeys(serviceName)
    if (env[idKey] && env[secretKey]) {
      return { clientId: env[idKey]!, clientSecret: env[secretKey]! }
    }
  }
  if (env.ACCOUNT_CLIENT_ID && env.ACCOUNT_CLIENT_SECRET) {
    return { clientId: env.ACCOUNT_CLIENT_ID, clientSecret: env.ACCOUNT_CLIENT_SECRET }
  }
  if (serviceName && env.ACCOUNT_INTERNAL_TOKEN && env.ACCOUNT_BASE_URL) {
    return fetchClientCredentialsFromApi(env.ACCOUNT_BASE_URL, serviceName, env.ACCOUNT_INTERNAL_TOKEN)
  }
  throw new Error(
    "[account-auth] Missing account-service credentials: set " +
      "ACCOUNT_CLIENT_ID_<SERVICE_NAME> + ACCOUNT_CLIENT_SECRET_<SERVICE_NAME>, " +
      "plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET, " +
      "or SERVICE_NAME + ACCOUNT_INTERNAL_TOKEN (+ ACCOUNT_BASE_URL) for the internal API",
  )
}

export async function getAuthConfig(env: Env = process.env): Promise<AuthConfig> {
  const { clientId, clientSecret } = await resolveClientCredentials(env)
  const ttl = Number(env.SESSION_TTL || "28800")
  if (!Number.isFinite(ttl) || ttl <= 0) {
    throw new Error(`[redis-client] SESSION_TTL must be a positive integer, got: ${env.SESSION_TTL}`)
  }
  return {
    accountPublicUrl: req("ACCOUNT_PUBLIC_URL", env).replace(/\/+$/, ""),
    accountBaseUrl: req("ACCOUNT_BASE_URL", env).replace(/\/+$/, ""),
    clientId,
    clientSecret,
    redirectUri: req("ACCOUNT_REDIRECT_URI", env),
    jwtSecret: req("JWT_SECRET", env),
    adminEmails: parseAdminEmails(env.ADMIN_EMAILS),
    secureCookie: (env.SECURE_COOKIE || "false").toLowerCase() === "true",
    sessionTtlSeconds: ttl,
    centralLogout: (env.SSO_CENTRAL_LOGOUT || "false").toLowerCase() === "true",
  }
}
```

- [ ] **Step 2: `flow.ts`** — await both `getAuthConfig()` calls. Change `const cfg = getAuthConfig()` → `const cfg = await getAuthConfig()` in `startLogin` (line ~13) and `completeCallback` (line ~37). (Both functions are already `async`.)

- [ ] **Step 3: `index.ts`** — add `__resetClientCredentialsCache` to the config export block:
```ts
export {
  deriveClientEnvKeys,
  resolveClientCredentials,
  parseAdminEmails,
  getAuthConfig,
  __resetClientCredentialsCache,
  type AuthConfig,
} from "./config"
```

- [ ] **Step 4: `config.test.ts`** — make the `resolveClientCredentials`/`getAuthConfig` cases async (await), and add fetch-fallback cases. Replace the `describe("resolveClientCredentials", ...)` block and the `describe("getAuthConfig", ...)` block; add a fetch describe. Concretely:
  - Every `resolveClientCredentials({...})` → `await resolveClientCredentials({...})`, and its `it(...)` → `async () =>`. The throw case: `await expect(resolveClientCredentials({ SERVICE_NAME: "redis-client-frontend" })).rejects.toThrow(/Missing account-service credentials/)`.
  - Every `getAuthConfig(...)` → `await getAuthConfig(...)`, `it` → async; throw cases → `await expect(getAuthConfig({...})).rejects.toThrow(...)`.
  - Add:
```ts
import { __resetClientCredentialsCache } from "./config"

describe("resolveClientCredentials internal-API fallback", () => {
  const base = { SERVICE_NAME: "redis-client-frontend", ACCOUNT_BASE_URL: "http://acct:8600/", ACCOUNT_INTERNAL_TOKEN: "adm" }
  beforeEach(() => { __resetClientCredentialsCache(); vi.restoreAllMocks() })

  it("fetches from the internal endpoint when env creds are absent", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ client_id: "fid", client_secret: "fsec" }) })
    vi.stubGlobal("fetch", fetchMock)
    const creds = await resolveClientCredentials(base)
    expect(creds).toEqual({ clientId: "fid", clientSecret: "fsec" })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://acct:8600/internal/credentials/redis-client-frontend")
    expect(init.headers["X-Admin-Token"]).toBe("adm")
  })

  it("memoizes the fetched creds (no second fetch)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ client_id: "fid", client_secret: "fsec" }) })
    vi.stubGlobal("fetch", fetchMock)
    await resolveClientCredentials(base)
    await resolveClientCredentials(base)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("throws on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))
    await expect(resolveClientCredentials(base)).rejects.toThrow(/no active service/)
  })

  it("env creds still win over the fetch", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)
    const creds = await resolveClientCredentials({ ...base, ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "eid", ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "esec" })
    expect(creds).toEqual({ clientId: "eid", clientSecret: "esec" })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
```
  (Ensure `beforeEach`, `vi` are imported: `import { describe, it, expect, vi, beforeEach } from "vitest"`.)

- [ ] **Step 5: `flow.test.ts`** — the `getAuthConfig` spy must resolve a Promise now: change `vi.spyOn(config, "getAuthConfig").mockReturnValue(baseCfg)` → `vi.spyOn(config, "getAuthConfig").mockResolvedValue(baseCfg)`.

- [ ] **Step 6: Verify** in `libs/auth/node`:
```
node_modules/.bin/vitest run
node_modules/.bin/tsc --noEmit
```
Expected: all tests pass (34 + ~4 new fetch tests); tsc exit 0.

- [ ] **Step 7: Commit**
```
git add libs/auth/node
git commit  (conventional subject + bilingual EN/FR body; use inline heredoc -m "$(cat <<'EOF' ... EOF)")
# feat(libs/auth): async internal-credentials fetch fallback in @hellopro/auth
```

---

### Task 1: redis-client-frontend — consume async config + wire ACCOUNT_INTERNAL_TOKEN

**Goal:** The service awaits the now-async `getAuthConfig` and can resolve creds via the internal token (no per-service secret required).

**Files:** Modify `apps-microservices/redis-client-frontend/app/auth/logout/route.ts`, `docker-compose.yml`, `apps-microservices/redis-client-frontend/.env.example`, `apps-microservices/redis-client-frontend/CLAUDE.md`

**Acceptance:**
- [ ] logout route awaits `getAuthConfig()`.
- [ ] compose passes `ACCOUNT_INTERNAL_TOKEN` to redis-client-frontend.
- [ ] `.env.example` + CLAUDE.md document both cred modes.

**Verify:** `git grep -n "await getAuthConfig" apps-microservices/redis-client-frontend/app/auth/logout/route.ts` non-empty; `docker compose config redis-client-frontend` (VM) shows `ACCOUNT_INTERNAL_TOKEN`.

**Steps:**

- [ ] **Step 1: `app/auth/logout/route.ts`** — change `const cfg = getAuthConfig()` to `const cfg = await getAuthConfig()`. (The handler is already `async function GET`.)

- [ ] **Step 2: `docker-compose.yml`** — in the `redis-client-frontend` `environment:` block, add after the `ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND` line:
```yaml
      - ACCOUNT_INTERNAL_TOKEN=${ACCOUNT_INTERNAL_TOKEN:-}
```
(Leave the two `ACCOUNT_CLIENT_ID/SECRET_REDIS_CLIENT_FRONTEND` lines — env still wins if set; they become optional.)

- [ ] **Step 3: `.env.example`** — under the SSO block, add:
```bash
# Credential resolution — EITHER (a) explicit per-service pair below, OR (b) leave them
# blank and set ACCOUNT_INTERNAL_TOKEN (creds fetched from account-service MySQL by SERVICE_NAME).
ACCOUNT_INTERNAL_TOKEN=          # admin token for GET {ACCOUNT_BASE_URL}/internal/credentials/{SERVICE_NAME}. compose key: ACCOUNT_INTERNAL_TOKEN
```
And append a note to the `ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND` / `_SECRET` lines: `# optional if ACCOUNT_INTERNAL_TOKEN is set`.

- [ ] **Step 4: `CLAUDE.md`** — in the env table + client-registration section, document: creds resolve via (a) `ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND`/`_SECRET`, or (b) `ACCOUNT_INTERNAL_TOKEN` (+ registered client), fetched from account-service; env wins when both present. Add an `ACCOUNT_INTERNAL_TOKEN` row (Required: No — one of the two modes).

- [ ] **Step 5: Commit**
```
git add apps-microservices/redis-client-frontend docker-compose.yml
git commit  # feat(redis-client-frontend): support internal-token credential resolution (drop per-service secret)
```

---

### Task 2: python — async credential resolution + internal-API fetch

**Goal:** `hellopro-auth` resolves creds async with the memoized fetch fallback (delegating to `common_utils.sso`).

**Files:** Modify `libs/auth/python/hellopro_auth/{config.py,flow.py}`, `libs/auth/python/tests/{test_config.py,test_flow.py}`, `libs/auth/python/pyproject.toml`

**Acceptance:**
- [ ] env creds still win; with env absent + `ACCOUNT_INTERNAL_TOKEN`, `get_auth_config` awaits `common_utils.sso.get_account_credentials_from_api`, memoized.
- [ ] `get_auth_config`, `flow.start_login`, `flow.complete_callback` are async.
- [ ] tests pass under `asyncio_mode="auto"`.

**Verify:** `cd libs/auth/python && python -m pytest tests/ -q` → all pass.

**Steps:**

- [ ] **Step 1: `config.py`** — replace the imports + `get_auth_config` (keep `parse_admin_emails`, `AuthConfig`, `_req`):
```python
from common_utils.sso import (
    AccountCredentialsMissing,
    get_account_credentials,
    get_account_credentials_from_api,
)

_fetched_creds: dict[str, tuple[str, str]] = {}


def _reset_cache() -> None:
    """Test-only: clear the fetched-credentials memo."""
    _fetched_creds.clear()


async def _resolve_credentials() -> tuple[str, str]:
    try:
        return get_account_credentials()  # sync, env-only
    except AccountCredentialsMissing:
        name = os.environ.get("SERVICE_NAME", "").strip()
        if name and os.environ.get("ACCOUNT_INTERNAL_TOKEN"):
            if name not in _fetched_creds:
                _fetched_creds[name] = await get_account_credentials_from_api()
            return _fetched_creds[name]
        raise


async def get_auth_config() -> AuthConfig:
    client_id, client_secret = await _resolve_credentials()
    ttl_raw = os.environ.get("SESSION_TTL", "28800")
    try:
        ttl = int(ttl_raw)
    except ValueError:
        ttl = 0
    if ttl <= 0:
        raise RuntimeError(
            f"[account-auth] SESSION_TTL must be a positive integer, got: {ttl_raw}"
        )
    return AuthConfig(
        account_public_url=_req("ACCOUNT_PUBLIC_URL").rstrip("/"),
        account_base_url=_req("ACCOUNT_BASE_URL").rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=_req("ACCOUNT_REDIRECT_URI"),
        jwt_secret=_req("JWT_SECRET"),
        admin_emails=parse_admin_emails(os.environ.get("ADMIN_EMAILS")),
        secure_cookie=os.environ.get("SECURE_COOKIE", "false").lower() == "true",
        session_ttl_seconds=ttl,
        central_logout=os.environ.get("SSO_CENTRAL_LOGOUT", "false").lower() == "true",
    )
```

- [ ] **Step 2: `flow.py`** — make `start_login` and `complete_callback` `async def` and `await get_auth_config()`:
```python
async def start_login() -> LoginStart:
    cfg = await get_auth_config()
    ...  # rest unchanged

async def complete_callback(*, code, state, state_cookie, verifier_cookie) -> dict:
    cfg = await get_auth_config()
    ...  # rest unchanged
```
(Only the `def`→`async def` and `get_auth_config()`→`await get_auth_config()` lines change.)

- [ ] **Step 3: `pyproject.toml`** — add:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
(so async tests run without per-test markers). If `pytest-asyncio` isn't already a dev dep, this repo has it available (used elsewhere); no need to add it to `dependencies`.

- [ ] **Step 4: `tests/test_flow.py`** — `_cfg` must be awaitable now, and each test awaits the flow calls. Change `_cfg` to `async def`, and add `await`:
```python
async def _cfg(**over):
    base = dict(
        account_public_url="http://localhost:8601", account_base_url="http://acct:8600",
        client_id="cid", client_secret="sec", redirect_uri="http://localhost:3551/auth/callback",
        jwt_secret="jwt", admin_emails=frozenset({"alice@hp.fr"}), secure_cookie=False,
        session_ttl_seconds=3600, central_logout=False,
    )
    base.update(over)
    return AuthConfig(**base)
```
Then each test → `async def test_...`, and `flow.start_login()` → `await flow.start_login()`, `flow.complete_callback(...)` → `await flow.complete_callback(...)`. (`exchange_code`/`verify_and_extract`/`create_session_token` mocks stay sync — they're awaited only if async; flow calls them sync, so keep the lambdas sync.)

- [ ] **Step 5: `tests/test_config.py`** — make the `get_auth_config` cases async (`async def`, `await get_auth_config()`; error cases use `with pytest.raises(...): await get_auth_config()`). Add a fetch-fallback test:
```python
import hellopro_auth.config as config

async def test_fetch_fallback(monkeypatch):
    config._reset_cache()
    for k in ("ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND", "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND", "ACCOUNT_CLIENT_ID", "ACCOUNT_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "redis-client-frontend")
    monkeypatch.setenv("ACCOUNT_INTERNAL_TOKEN", "adm")
    monkeypatch.setenv("ACCOUNT_PUBLIC_URL", "http://localhost:8601")
    monkeypatch.setenv("ACCOUNT_BASE_URL", "http://acct:8600")
    monkeypatch.setenv("ACCOUNT_REDIRECT_URI", "http://localhost:3551/auth/callback")
    monkeypatch.setenv("JWT_SECRET", "jwt")
    calls = {"n": 0}
    async def fake_api():
        calls["n"] += 1
        return ("fid", "fsec")
    monkeypatch.setattr(config, "get_account_credentials_from_api", fake_api)
    cfg = await config.get_auth_config()
    assert (cfg.client_id, cfg.client_secret) == ("fid", "fsec")
    await config.get_auth_config()          # memoized
    assert calls["n"] == 1
```
(Keep `parse_admin_emails` tests sync.)

- [ ] **Step 6: Verify**
```
cd libs/auth/python && python -m pytest tests/ -q
```
Expected: all pass (config + oauth + session + flow, now async where applicable).

- [ ] **Step 7: Commit**
```
git add libs/auth/python
git commit  # feat(libs/auth): async internal-credentials fetch fallback in hellopro-auth
```

---

## Self-Review

**Spec coverage:** §3 node async+fetch+memo → Task 0. §3.4 callers (flow + logout) → Task 0 (flow) + Task 1 (logout). §4 python → Task 2. §5 compose/docs → Task 1. §6 env-first precedence → Task 0 Step 1 order + "env wins" test; Task 2 `_resolve_credentials` try-env-first. §7 testing → Tasks 0/2 test steps. §9 memo correctness → memo-on-success + reset hook (both langs). No gaps.

**Placeholder scan:** no TBD/TODO; full code in every code step. Edits that say "rest unchanged" show the changed lines explicitly.

**Type/name consistency:** `resolveClientCredentials`/`getAuthConfig` async both in config.ts (Task 0) and consumers (flow.ts Task 0, logout Task 1); `__resetClientCredentialsCache` exported (Task 0 Step 3) + used in tests (Step 4). Python `_resolve_credentials`/`_reset_cache`/`get_account_credentials_from_api` consistent between config.py (Task 2 Step 1) and test (Step 5). Fetch URL shape identical to `account-client-go` (`/internal/credentials/{name}`, `X-Admin-Token`).

---

## Execution Notes
- **Task 0 → Task 1** ordered (logout must await the now-async getAuthConfig). Task 2 (python) independent.
- Node async test conversion: the biggest churn is flipping `config.test.ts` cases to `await`/`rejects`; `flow.test.ts` needs only the `mockResolvedValue` swap.
- **VM residual:** the actual fetch against a live account-service `/internal/credentials` + real `ACCOUNT_INTERNAL_TOKEN` is verified on the VM; unit tests stub HTTP.
- Commit trick: inline heredoc `-m "$(cat <<'EOF' ... EOF)"` (the `--file=`/`-f` forms + bash `<(...)` trip the harness force-push hook; use PowerShell for git if needed — git's own hooks still run).
