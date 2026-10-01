# Shared account-service Auth Lib — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the account-service OAuth 2.1 + PKCE login core into `libs/auth/node` (TS, `@hellopro/auth`) and `libs/auth/python` (`hellopro-auth`), and migrate `redis-client-frontend` to consume the node lib.

**Architecture:** Framework-free cores in `libs/auth/{node,python}`; each service keeps its thin framework wiring. Node consumed via repo-root Docker context + `file:` dep + `transpilePackages`; Python via `pip install -e` (common-utils pattern). Python reuses `common_utils.sso` for credential resolution and is built + tested with no live consumer yet.

**Tech Stack:** TypeScript + jose + vitest (node); Python + PyJWT + httpx + pytest.

**Spec:** `docs/superpowers/specs/2026-06-18-shared-auth-lib-design.md`

**Working dir:** repo root `D:\DevHellopro\Workspaces\RAG-HP-PUB` (branch `features/poc`). Windows; run node tools via `node_modules/.bin/<tool>` (pnpm 11 `ERR_PNPM_IGNORED_BUILDS` quirk). No local `node_modules` on the redis-client-frontend checkout — node tests run where deps exist (lib after its own install, or the VM build); python tests need `pip install -e libs/common-utils libs/auth/python` + pytest.

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `libs/auth/node/package.json` | `@hellopro/auth`, exports→src/index.ts, dep jose | A0 |
| `libs/auth/node/tsconfig.json`, `vitest.config.ts` | build/test config | A0 |
| `libs/auth/node/src/{config,oauth,session,flow}.ts` (+ `*.test.ts`) | moved core + tests | A0 |
| `libs/auth/node/src/index.ts` | public barrel | A0 |
| `apps-microservices/redis-client-frontend/package.json`, `next.config.mjs` | file: dep + transpilePackages | A1 |
| redis-client-frontend `middleware.ts`, `app/auth/*/route.ts`, `app/page.tsx` | repoint imports | A1 |
| redis-client-frontend `Dockerfile`, root `docker-compose.yml`, root `.dockerignore` | repo-root context | A2 |
| `libs/auth/python/pyproject.toml`, `hellopro_auth/{__init__,config}.py` (+ tests) | python package + config | B0 |
| `libs/auth/python/hellopro_auth/oauth.py` (+ tests) | PKCE/exchange/verify | B1 |
| `libs/auth/python/hellopro_auth/session.py` (+ tests) | session JWT | B2 |
| `libs/auth/python/hellopro_auth/flow.py` (+ tests), `README.md` | orchestration | B3 |

---

## PHASE A — node lib + redis-client-frontend migration

### Task A0: Create `libs/auth/node` and move the core

**Goal:** Stand up the `@hellopro/auth` package with the four core modules + their tests moved verbatim from `redis-client-frontend/lib/auth`.

**Files:**
- Create: `libs/auth/node/package.json`, `libs/auth/node/tsconfig.json`, `libs/auth/node/vitest.config.ts`, `libs/auth/node/src/index.ts`, `libs/auth/node/README.md`
- Move (git mv): `redis-client-frontend/lib/auth/{config,oauth,session,flow}.ts` and their `.test.ts` → `libs/auth/node/src/`

**Acceptance Criteria:**
- [ ] `libs/auth/node` installs and its 35 tests pass.
- [ ] `src/index.ts` re-exports the full public API.

**Verify:** in `libs/auth/node`: `pnpm install && node_modules/.bin/vitest run` → 35 passed.

**Steps:**

- [ ] **Step 1: Move the 8 files** (preserves history; internal `./config` etc. imports stay valid):
```bash
mkdir -p libs/auth/node/src
git mv apps-microservices/redis-client-frontend/lib/auth/config.ts        libs/auth/node/src/config.ts
git mv apps-microservices/redis-client-frontend/lib/auth/config.test.ts   libs/auth/node/src/config.test.ts
git mv apps-microservices/redis-client-frontend/lib/auth/oauth.ts         libs/auth/node/src/oauth.ts
git mv apps-microservices/redis-client-frontend/lib/auth/oauth.test.ts    libs/auth/node/src/oauth.test.ts
git mv apps-microservices/redis-client-frontend/lib/auth/session.ts       libs/auth/node/src/session.ts
git mv apps-microservices/redis-client-frontend/lib/auth/session.test.ts  libs/auth/node/src/session.test.ts
git mv apps-microservices/redis-client-frontend/lib/auth/flow.ts          libs/auth/node/src/flow.ts
git mv apps-microservices/redis-client-frontend/lib/auth/flow.test.ts     libs/auth/node/src/flow.test.ts
```

- [ ] **Step 2: `libs/auth/node/package.json`**
```json
{
  "name": "@hellopro/auth",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.ts"
  },
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "jose": "^5.9.6"
  },
  "devDependencies": {
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 3: `libs/auth/node/tsconfig.json`**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "esnext",
    "moduleResolution": "bundler",
    "lib": ["dom", "esnext"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 4: `libs/auth/node/vitest.config.ts`**
```ts
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: { environment: "node" },
})
```

- [ ] **Step 5: `libs/auth/node/src/index.ts`** (public barrel)
```ts
export {
  deriveClientEnvKeys,
  resolveClientCredentials,
  parseAdminEmails,
  getAuthConfig,
  type AuthConfig,
} from "./config"
export {
  generatePkce,
  randomState,
  buildAuthorizeUrl,
  exchangeCode,
  verifyAndExtract,
  type Pkce,
  type TokenResponse,
  type Identity,
} from "./oauth"
export {
  createSessionToken,
  readSession,
  SESSION_COOKIE,
  type SessionClaims,
} from "./session"
export {
  startLogin,
  completeCallback,
  type LoginStart,
  type CallbackResult,
} from "./flow"
```

- [ ] **Step 6: `libs/auth/node/README.md`**
```markdown
# @hellopro/auth

Framework-free account-service OAuth 2.1 + PKCE login core (config, oauth, session, flow).
Service-agnostic: reads `SERVICE_NAME` to derive `ACCOUNT_CLIENT_ID_<SLUG>`.

## Consume (Node/Next service)
1. `package.json`: `"@hellopro/auth": "file:../../libs/auth/node"`
2. Next: add `transpilePackages: ["@hellopro/auth"]` to `next.config`.
3. Docker: build from repo-root context, `COPY libs/auth/node` + your service, `pnpm install`.
4. Import: `import { startLogin, completeCallback, readSession, SESSION_COOKIE } from "@hellopro/auth"`.

Keep your own thin route handlers + middleware (framework wiring). See redis-client-frontend for a reference consumer.
```

- [ ] **Step 7: Verify** in `libs/auth/node`:
```bash
cd libs/auth/node && pnpm install && node_modules/.bin/vitest run
```
Expected: `Test Files 4 passed (4)`, `Tests 35 passed (35)`.

- [ ] **Step 8: Commit**
```bash
git add libs/auth/node
git commit -m "feat(libs/auth): extract account-service login core to @hellopro/auth node lib"
```

---

### Task A1: Migrate redis-client-frontend to `@hellopro/auth`

**Goal:** Point the service at the shared lib; delete its local `lib/auth`.

**Files:**
- Modify: `apps-microservices/redis-client-frontend/package.json`, `next.config.mjs`, `middleware.ts`, `app/auth/login/route.ts`, `app/auth/callback/route.ts`, `app/auth/logout/route.ts`, `app/page.tsx`
- Delete: `apps-microservices/redis-client-frontend/lib/auth/` (now empty after A0 moves — remove the dir)

**Acceptance Criteria:**
- [ ] No `@/lib/auth` imports remain; all auth imports come from `@hellopro/auth`.
- [ ] `lib/auth/` no longer exists in the service.
- [ ] Service TS files typecheck (given the lib is linked).

**Verify:** `git grep -n "@/lib/auth" apps-microservices/redis-client-frontend` → empty.

**Steps:**

- [ ] **Step 1: `package.json`** — add the dep, drop direct `jose` (now transitive via the lib). In `apps-microservices/redis-client-frontend/package.json` dependencies: remove `"jose": "..."`, add `"@hellopro/auth": "file:../../libs/auth/node"`. Then `pnpm install` in the service to relink.

- [ ] **Step 2: `next.config.mjs`** — add `transpilePackages`:
```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
  output: 'standalone',
  transpilePackages: ['@hellopro/auth'],
}

export default nextConfig
```

- [ ] **Step 3: Repoint imports.** Change these exact import lines:
  - `middleware.ts`: `import { readSession, SESSION_COOKIE } from "@/lib/auth/session"` → `from "@hellopro/auth"`
  - `app/auth/login/route.ts`: `import { startLogin } from "@/lib/auth/flow"` → `from "@hellopro/auth"`
  - `app/auth/callback/route.ts`: `import { completeCallback } from "@/lib/auth/flow"` and `import { SESSION_COOKIE } from "@/lib/auth/session"` → merge to `import { completeCallback, SESSION_COOKIE } from "@hellopro/auth"`
  - `app/auth/logout/route.ts`: `import { getAuthConfig } from "@/lib/auth/config"` and `import { SESSION_COOKIE } from "@/lib/auth/session"` → `import { getAuthConfig, SESSION_COOKIE } from "@hellopro/auth"`
  - `app/page.tsx`: `import { readSession, SESSION_COOKIE } from "@/lib/auth/session"` → `from "@hellopro/auth"`

- [ ] **Step 4: Remove the now-empty dir**
```bash
rmdir apps-microservices/redis-client-frontend/lib/auth 2>/dev/null || true
```

- [ ] **Step 5: Verify**
```bash
git grep -n "@/lib/auth" apps-microservices/redis-client-frontend
```
Expected: no matches. (Full typecheck happens in the VM build — Task A2 — since this checkout has no `node_modules`.)

- [ ] **Step 6: Commit**
```bash
git add apps-microservices/redis-client-frontend
git commit -m "refactor(redis-client-frontend): consume @hellopro/auth, drop local lib/auth"
```

---

### Task A2: Repo-root Docker context for redis-client-frontend

**Goal:** Make the service's Docker build see `libs/auth/node` so `pnpm install` resolves the `file:` dep.

**Files:**
- Modify: `apps-microservices/redis-client-frontend/Dockerfile`
- Modify: `docker-compose.yml` (`redis-client-frontend` block)
- Create: `.dockerignore` (repo root) — or extend if present

**Acceptance Criteria:**
- [ ] Dockerfile copies both `libs/auth/node` and the service, preserving `../../` relative path.
- [ ] compose builds from repo-root context.
- [ ] (VM) `docker compose build redis-client-frontend` succeeds and the container serves.

**Verify:** VM: `docker compose --profile app build redis-client-frontend` → success. (Cannot run locally — no Docker/node_modules here.)

**Steps:**

- [ ] **Step 1: Rewrite `apps-microservices/redis-client-frontend/Dockerfile`** for repo-root context (paths now relative to repo root; the service + lib keep their tree positions so `file:../../libs/auth/node` resolves):
```dockerfile
# Build context = repo root. Preserves libs/auth/node at ../../ relative to the service.
FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm

# Shared lib (the file: dependency target) + the service, keeping their relative tree.
COPY libs/auth/node ./libs/auth/node
COPY apps-microservices/redis-client-frontend ./apps-microservices/redis-client-frontend

WORKDIR /app/apps-microservices/redis-client-frontend
RUN pnpm install
RUN pnpm build

# Production runner
FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 nextjs && \
    adduser --system --uid 1001 nextjs

ENV SVC=/app/apps-microservices/redis-client-frontend
COPY --from=builder --chown=nextjs:nextjs $SVC/public ./public
COPY --from=builder --chown=nextjs:nextjs $SVC/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs $SVC/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000
ENV NODE_ENV production
CMD ["node", "server.js"]
```
Note: Next `standalone` output traces the linked `@hellopro/auth` files into `.next/standalone` automatically; the runner copies the standalone bundle as before. (The `deps`/`pnpm fetch` cache stage is dropped — with a `file:` dep, `pnpm fetch` of a workspace-local path adds no value; `pnpm install` handles it. Removing it also avoids a stale-lock fetch mismatch.)

- [ ] **Step 2: Update the `redis-client-frontend` service in `docker-compose.yml`** — change `build` to repo-root context (keep environment/networks/ports/logging from the SSO work):
```yaml
  redis-client-frontend:
    profiles: [ "app" ]
    build:
      context: .
      dockerfile: apps-microservices/redis-client-frontend/Dockerfile
    ports:
      - "3551:3000"
    environment:
      # ... (unchanged SSO + Redis env block from the login feature) ...
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
      - SESSION_SECRET=${REDIS_CLIENT_SESSION_SECRET}
      - ADMIN_EMAILS=${REDIS_CLIENT_ADMIN_EMAILS}
      - SECURE_COOKIE=${ACCOUNT_SECURE_COOKIE:-false}
      - SESSION_TTL=${REDIS_CLIENT_SESSION_TTL:-28800}
      - SSO_CENTRAL_LOGOUT=${REDIS_CLIENT_CENTRAL_LOGOUT:-false}
    networks:
      - services-net
    logging: *logging_defaults
```

- [ ] **Step 3: Ensure a repo-root `.dockerignore`** keeps the (now repo-root) context lean. If `.dockerignore` exists at root, confirm it excludes the heavy paths; else create it:
```
**/node_modules
**/.next
.git
**/__pycache__
graphify-out
docs
*.stackdump
```
(Adjust to not exclude `libs/auth/node` or `apps-microservices/redis-client-frontend`.)

- [ ] **Step 4: Verify on VM**
```bash
docker compose --profile app build redis-client-frontend
```
Expected: build succeeds (pnpm resolves `@hellopro/auth` from `file:../../libs/auth/node`, `next build` passes). Smoke: `docker compose --profile app up -d redis-client-frontend` then browse `http://localhost:3551/` → redirects to `/auth/login`.

- [ ] **Step 5: Commit**
```bash
git add apps-microservices/redis-client-frontend/Dockerfile docker-compose.yml .dockerignore
git commit -m "build(redis-client-frontend): repo-root context to bundle @hellopro/auth"
```

---

## PHASE B — `libs/auth/python`

> Independent of Phase A. Build + test only; no live consumer (api-gateway untouched). Setup for tests: `pip install -e libs/common-utils libs/auth/python pytest`.

### Task B0: Package skeleton + config (reuses common_utils.sso)

**Goal:** Create `hellopro-auth` with the config module delegating credential resolution to `common_utils.sso`.

**Files:**
- Create: `libs/auth/python/pyproject.toml`, `libs/auth/python/hellopro_auth/__init__.py`, `libs/auth/python/hellopro_auth/config.py`, `libs/auth/python/tests/test_config.py`, `libs/auth/python/README.md`

**Acceptance Criteria:**
- [ ] `get_auth_config()` reads all env; `resolve` reuses `common_utils.sso.get_account_credentials`.
- [ ] `parse_admin_emails` normalizes; `SESSION_TTL` guard rejects non-positive.

**Verify:** `cd libs/auth/python && python -m pytest tests/test_config.py -q` → pass.

**Steps:**

- [ ] **Step 1: `pyproject.toml`** (setuptools, mirrors common-utils):
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "hellopro-auth"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["PyJWT>=2.8", "httpx>=0.27"]

[tool.setuptools.packages.find]
where = ["."]
include = ["hellopro_auth*"]
```
Note: `common_utils` is a runtime import (credential resolution) but intentionally NOT a hard dependency here — consumers already `pip install -e libs/common-utils`. Documented in README.

- [ ] **Step 2: Write failing test `tests/test_config.py`**
```python
import pytest
from hellopro_auth.config import parse_admin_emails, get_auth_config

BASE = {
    "SERVICE_NAME": "redis-client-frontend",
    "ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND": "cid",
    "ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND": "sec",
    "ACCOUNT_PUBLIC_URL": "http://localhost:8601/",
    "ACCOUNT_BASE_URL": "http://account-service-backend:8600/",
    "ACCOUNT_REDIRECT_URI": "http://localhost:3551/auth/callback",
    "JWT_SECRET": "jwt",
}


def test_parse_admin_emails():
    s = parse_admin_emails(" Alice@HP.fr , bob@hp.fr ,, ")
    assert s == {"alice@hp.fr", "bob@hp.fr"}
    assert parse_admin_emails(None) == set()


def test_get_auth_config_defaults(monkeypatch):
    for k, v in BASE.items():
        monkeypatch.setenv(k, v)
    cfg = get_auth_config()
    assert cfg.account_public_url == "http://localhost:8601"
    assert cfg.client_id == "cid" and cfg.client_secret == "sec"
    assert cfg.session_ttl_seconds == 28800
    assert cfg.secure_cookie is False


def test_bad_session_ttl(monkeypatch):
    for k, v in BASE.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("SESSION_TTL", "abc")
    with pytest.raises(RuntimeError, match="SESSION_TTL"):
        get_auth_config()
```

- [ ] **Step 3: Run test → FAIL** (`ModuleNotFoundError: hellopro_auth`).

- [ ] **Step 4: `hellopro_auth/config.py`**
```python
"""Auth config: resolve account-service OAuth client creds + settings from env.
Credential resolution delegates to common_utils.sso (shared convention)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from common_utils.sso import get_account_credentials


def parse_admin_emails(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


@dataclass(frozen=True)
class AuthConfig:
    account_public_url: str
    account_base_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    jwt_secret: str
    admin_emails: set[str]
    secure_cookie: bool
    session_ttl_seconds: int
    central_logout: bool


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"[account-auth] Missing required env var: {name}")
    return v


def get_auth_config() -> AuthConfig:
    client_id, client_secret = get_account_credentials()
    ttl_raw = os.environ.get("SESSION_TTL", "28800")
    try:
        ttl = int(ttl_raw)
    except ValueError:
        ttl = 0
    if ttl <= 0:
        raise RuntimeError(f"[account-auth] SESSION_TTL must be a positive integer, got: {ttl_raw}")
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

- [ ] **Step 5: `hellopro_auth/__init__.py`** (barrel — will grow as B1-B3 land)
```python
from .config import AuthConfig, get_auth_config, parse_admin_emails

__all__ = ["AuthConfig", "get_auth_config", "parse_admin_emails"]
```

- [ ] **Step 6: `README.md`** — note: consumers `pip install -e libs/common-utils libs/auth/python`; import `from hellopro_auth import ...`; keep your own FastAPI routes.

- [ ] **Step 7: Run test → PASS.** Commit:
```bash
git add libs/auth/python
git commit -m "feat(libs/auth): hellopro-auth python package + config (reuses common_utils.sso)"
```

---

### Task B1: `oauth.py` (PKCE / exchange / verify)

**Goal:** Framework-free OAuth2 + PKCE primitives, parity with the node core.

**Files:** Create `libs/auth/python/hellopro_auth/oauth.py`, `libs/auth/python/tests/test_oauth.py`; update `__init__.py`.

**Acceptance Criteria:**
- [ ] `gen_pkce().challenge == b64url(sha256(verifier))`; authorize URL is urlencoded + `S256`.
- [ ] `exchange_code` posts Basic auth + form; raises on non-200.
- [ ] `verify_and_extract` accepts valid HS256 (email from `sub`), rejects wrong secret.

**Verify:** `python -m pytest tests/test_oauth.py -q` → pass.

**Steps:**

- [ ] **Step 1: `tests/test_oauth.py`**
```python
import base64, hashlib
import jwt
import pytest
from hellopro_auth.oauth import (
    gen_pkce, random_state, build_authorize_url, exchange_code, verify_and_extract,
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def test_pkce_challenge():
    p = gen_pkce()
    assert p.challenge == _b64url(hashlib.sha256(p.verifier.encode()).digest())
    assert "=" not in p.verifier


def test_authorize_url():
    url = build_authorize_url(
        public_url="http://localhost:8601", client_id="cid",
        redirect_uri="http://localhost:3551/auth/callback", challenge="chal", state="st",
    )
    assert url.startswith("http://localhost:8601/authorize?")
    assert "code_challenge_method=S256" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A3551%2Fauth%2Fcallback" in url


def test_exchange_code(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"access_token": "tok"}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        captured.update(url=url, data=data, auth=auth)
        return FakeResp()

    monkeypatch.setattr("hellopro_auth.oauth.httpx.post", fake_post)
    out = exchange_code(
        base_url="http://acct:8600", client_id="cid", client_secret="sec",
        code="c", redirect_uri="r", verifier="v",
    )
    assert out["access_token"] == "tok"
    assert captured["url"] == "http://acct:8600/token"
    assert captured["auth"] == ("cid", "sec")
    assert captured["data"]["grant_type"] == "authorization_code"


def test_exchange_code_non_200(monkeypatch):
    class FakeResp:
        status_code = 401
    monkeypatch.setattr("hellopro_auth.oauth.httpx.post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="401"):
        exchange_code(base_url="b", client_id="c", client_secret="s", code="x", redirect_uri="r", verifier="v")


def test_verify_and_extract():
    tok = jwt.encode({"sub": "alice@hp.fr"}, "secret", algorithm="HS256")
    assert verify_and_extract(tok, "secret").email == "alice@hp.fr"
    with pytest.raises(Exception):
        verify_and_extract(jwt.encode({"sub": "a@hp.fr"}, "wrong", algorithm="HS256"), "secret")
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: `hellopro_auth/oauth.py`**
```python
"""Framework-free OAuth2 + PKCE primitives (parity with libs/auth/node oauth.ts)."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str


def gen_pkce() -> Pkce:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return Pkce(verifier=verifier, challenge=challenge)


def random_state() -> str:
    return _b64url(secrets.token_bytes(16))


def build_authorize_url(*, public_url: str, client_id: str, redirect_uri: str,
                        challenge: str, state: str) -> str:
    query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"{public_url}/authorize?{query}"


def exchange_code(*, base_url: str, client_id: str, client_secret: str, code: str,
                  redirect_uri: str, verifier: str, timeout: float = 10.0) -> dict:
    resp = httpx.post(
        f"{base_url}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"[account-auth] token exchange failed: {resp.status_code}")
    return resp.json()


@dataclass(frozen=True)
class Identity:
    email: str
    name: str | None = None


def verify_and_extract(access_token: str, jwt_secret: str) -> Identity:
    # aud intentionally not verified (account-service sets aud=client_id).
    payload = jwt.decode(access_token, jwt_secret, algorithms=["HS256"],
                         options={"verify_aud": False})
    email = payload.get("sub") or payload.get("email")
    if not email:
        raise RuntimeError("[account-auth] token missing sub/email claim")
    return Identity(email=email, name=payload.get("name"))
```

- [ ] **Step 4: Run → PASS.** Update `__init__.py` to also export `gen_pkce, random_state, build_authorize_url, exchange_code, verify_and_extract, Pkce, Identity`.

- [ ] **Step 5: Commit**
```bash
git add libs/auth/python/hellopro_auth/oauth.py libs/auth/python/tests/test_oauth.py libs/auth/python/hellopro_auth/__init__.py
git commit -m "feat(libs/auth): hellopro-auth oauth primitives (PKCE/exchange/verify)"
```

---

### Task B2: `session.py`

**Goal:** Signed `rcf_session` JWT, parity with node session.ts.

**Files:** Create `libs/auth/python/hellopro_auth/session.py`, `tests/test_session.py`; update `__init__.py`.

**Acceptance Criteria:**
- [ ] round-trip `{email, name}`; expired → None; garbage → None; missing `SESSION_SECRET` raises (before decode).

**Verify:** `python -m pytest tests/test_session.py -q` → pass.

**Steps:**

- [ ] **Step 1: `tests/test_session.py`**
```python
import pytest
from hellopro_auth.session import create_session_token, read_session, SESSION_COOKIE, SessionClaims


def test_cookie_name():
    assert SESSION_COOKIE == "rcf_session"


def test_round_trip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    tok = create_session_token(SessionClaims(email="alice@hp.fr", name="Alice"), 3600)
    got = read_session(tok)
    assert got == SessionClaims(email="alice@hp.fr", name="Alice")


def test_expired(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    assert read_session(create_session_token(SessionClaims(email="a@hp.fr"), -1)) is None


def test_garbage(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s")
    assert read_session("nope") is None
    assert read_session(None) is None


def test_missing_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        read_session("any.jwt")
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: `hellopro_auth/session.py`**
```python
"""Signed rcf_session JWT (HS256, SESSION_SECRET). Parity with libs/auth/node session.ts."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import jwt

SESSION_COOKIE = "rcf_session"


def _session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError("[account-auth] Missing SESSION_SECRET")
    return secret


@dataclass(frozen=True)
class SessionClaims:
    email: str
    name: str | None = None


def create_session_token(claims: SessionClaims, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {"sub": claims.email, "name": claims.name, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def read_session(token: str | None) -> SessionClaims | None:
    if not token:
        return None
    secret = _session_secret()  # raise loudly on misconfig, before the try
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    return SessionClaims(email=email, name=payload.get("name"))
```

- [ ] **Step 4: Run → PASS.** Update `__init__.py` to export `create_session_token, read_session, SESSION_COOKIE, SessionClaims`.

- [ ] **Step 5: Commit**
```bash
git add libs/auth/python/hellopro_auth/session.py libs/auth/python/tests/test_session.py libs/auth/python/hellopro_auth/__init__.py
git commit -m "feat(libs/auth): hellopro-auth signed session module"
```

---

### Task B3: `flow.py` + finalize

**Goal:** Framework-free orchestration, parity with node flow.ts.

**Files:** Create `libs/auth/python/hellopro_auth/flow.py`, `tests/test_flow.py`; finalize `__init__.py`.

**Acceptance Criteria:**
- [ ] `start_login` returns authorize_url/verifier/state/secure_cookie.
- [ ] `complete_callback` error branches (missing/mismatch/verifier/exchange/token), denied (non-allow-listed), ok (allowed).

**Verify:** `python -m pytest tests/ -q` → all pass.

**Steps:**

- [ ] **Step 1: `tests/test_flow.py`**
```python
from dataclasses import dataclass
import hellopro_auth.flow as flow
from hellopro_auth.config import AuthConfig
from hellopro_auth.oauth import Identity


def _cfg(**over):
    base = dict(
        account_public_url="http://localhost:8601", account_base_url="http://acct:8600",
        client_id="cid", client_secret="sec", redirect_uri="http://localhost:3551/auth/callback",
        jwt_secret="jwt", admin_emails={"alice@hp.fr"}, secure_cookie=False,
        session_ttl_seconds=3600, central_logout=False,
    )
    base.update(over)
    return AuthConfig(**base)


def test_start_login(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    out = flow.start_login()
    assert out.authorize_url.startswith("http://localhost:8601/authorize?")
    assert out.secure_cookie is False and out.verifier and out.state


def test_callback_missing():
    # get_auth_config is called first; patch to avoid env need
    import hellopro_auth.flow as f
    f.get_auth_config = _cfg  # type: ignore
    assert flow.complete_callback(code=None, state=None, state_cookie=None, verifier_cookie=None)["status"] == "error"


def test_callback_state_mismatch(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    r = flow.complete_callback(code="c", state="a", state_cookie="b", verifier_cookie="v")
    assert r == {"status": "error", "reason": "state_mismatch"}


def test_callback_denied(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    monkeypatch.setattr(flow, "exchange_code", lambda **k: {"access_token": "t"})
    monkeypatch.setattr(flow, "verify_and_extract", lambda *a: Identity(email="mallory@hp.fr"))
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "denied", "email": "mallory@hp.fr"}


def test_callback_ok(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    monkeypatch.setattr(flow, "exchange_code", lambda **k: {"access_token": "t"})
    monkeypatch.setattr(flow, "verify_and_extract", lambda *a: Identity(email="Alice@hp.fr", name="Alice"))
    monkeypatch.setattr(flow, "create_session_token", lambda *a: "session-jwt")
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "ok", "session_token": "session-jwt", "ttl_seconds": 3600, "secure_cookie": False}


def test_callback_exchange_fails(monkeypatch):
    monkeypatch.setattr(flow, "get_auth_config", _cfg)
    def boom(**k):
        raise RuntimeError("x")
    monkeypatch.setattr(flow, "exchange_code", boom)
    r = flow.complete_callback(code="c", state="a", state_cookie="a", verifier_cookie="v")
    assert r == {"status": "error", "reason": "exchange_failed"}
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: `hellopro_auth/flow.py`**
```python
"""Framework-free login orchestration (parity with libs/auth/node flow.ts)."""
from __future__ import annotations

from dataclasses import dataclass

from .config import get_auth_config
from .oauth import build_authorize_url, exchange_code, gen_pkce, random_state, verify_and_extract
from .session import SessionClaims, create_session_token


@dataclass(frozen=True)
class LoginStart:
    authorize_url: str
    verifier: str
    state: str
    secure_cookie: bool


def start_login() -> LoginStart:
    cfg = get_auth_config()
    pkce = gen_pkce()
    state = random_state()
    url = build_authorize_url(
        public_url=cfg.account_public_url, client_id=cfg.client_id,
        redirect_uri=cfg.redirect_uri, challenge=pkce.challenge, state=state,
    )
    return LoginStart(authorize_url=url, verifier=pkce.verifier, state=state,
                      secure_cookie=cfg.secure_cookie)


def complete_callback(*, code: str | None, state: str | None,
                      state_cookie: str | None, verifier_cookie: str | None) -> dict:
    cfg = get_auth_config()

    if not code or not state:
        return {"status": "error", "reason": "missing_code_or_state"}
    if not state_cookie or state_cookie != state:
        return {"status": "error", "reason": "state_mismatch"}
    if not verifier_cookie:
        return {"status": "error", "reason": "missing_verifier"}

    try:
        tokens = exchange_code(
            base_url=cfg.account_base_url, client_id=cfg.client_id, client_secret=cfg.client_secret,
            code=code, redirect_uri=cfg.redirect_uri, verifier=verifier_cookie,
        )
    except Exception:
        return {"status": "error", "reason": "exchange_failed"}

    try:
        identity = verify_and_extract(tokens["access_token"], cfg.jwt_secret)
    except Exception:
        return {"status": "error", "reason": "token_invalid"}

    if identity.email.lower() not in cfg.admin_emails:
        return {"status": "denied", "email": identity.email}

    token = create_session_token(
        SessionClaims(email=identity.email, name=identity.name), cfg.session_ttl_seconds
    )
    return {"status": "ok", "session_token": token,
            "ttl_seconds": cfg.session_ttl_seconds, "secure_cookie": cfg.secure_cookie}
```

- [ ] **Step 4: Run full suite → PASS.** Finalize `__init__.py` to also export `start_login, complete_callback, LoginStart`.

- [ ] **Step 5: Commit**
```bash
git add libs/auth/python
git commit -m "feat(libs/auth): hellopro-auth flow orchestration + finalize package"
```

---

## Self-Review

**Spec coverage:** D1 structure → A0/B0 dirs. D2 both → Phase A + B. D3 node consumption → A2 (context/file:/transpilePackages). D4 core-only → A0 moves core; routes/middleware stay (A1 repoints only). D5 redis first consumer → A1/A2. D6 api-gateway untouched → no task touches it (stated in B header). D7 python reuses common_utils.sso → B0 config imports it. D8 naming → A0 (`@hellopro/auth`), B0 (`hellopro-auth`/`hellopro_auth`). §7 testing → tests in every task. §9 risks → A2 verify steps.
No gaps.

**Placeholder scan:** No TBD/TODO; every code step has full code. The compose block in A2 Step 2 shows the full env list (not "unchanged ...") for the load-bearing part.

**Type/name consistency:** node public API in `index.ts` (A0) matches the exports the migration imports (A1). Python: `AuthConfig` fields consistent across config/flow tests; `Identity`, `SessionClaims`, `LoginStart` consistent; `complete_callback` result dict keys (`status`/`reason`/`email`/`session_token`/`ttl_seconds`/`secure_cookie`) consistent between flow.py and test_flow.py; env keys match the node lib + spec.

---

## Execution Notes
- **Phase A is the shippable proof; Phase B is independent** — can run in either order, but A validates the consumption pattern.
- **Node tests** run inside `libs/auth/node` after its own `pnpm install` (this repo checkout has no service-level node_modules). Authoritative node build = the VM (Task A2).
- **Python tests** need `pip install -e libs/common-utils libs/auth/python` + `pytest` + `PyJWT` + `httpx`.
- **A2 is the one step not locally verifiable** — the repo-root-context Docker build must be confirmed on the VM (pnpm resolves the `file:` dep; `next build` passes; standalone traces `@hellopro/auth`).
- TDD gate: python tests are written before impl in each B task; node tests already exist (moved).
