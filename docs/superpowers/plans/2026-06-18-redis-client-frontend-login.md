# redis-client-frontend account-service SSO Login — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the paste-`ADMIN_TOKEN` login with OAuth 2.1 + PKCE SSO against account-service, using a Next.js BFF pattern (own 8h session cookie, email allow-list).

**Architecture:** Pure, unit-tested auth library (`lib/auth/*`) holds all logic — config, PKCE/OAuth primitives, session JWT, and a framework-free orchestration layer (`flow.ts`). Thin App Router route handlers (`app/auth/*`) translate the orchestration's results into `NextResponse` cookies/redirects. Edge middleware verifies the session cookie on every request. No logic lives in routes/middleware that isn't covered by a `lib/auth` test.

**Tech Stack:** Next.js 16 (App Router, route handlers, edge middleware), TypeScript, `jose` (JWT sign/verify, edge-compatible), Web Crypto (PKCE), Vitest (new test harness).

**Spec:** `docs/superpowers/specs/2026-06-18-redis-client-frontend-login-design.md`

**Working dir for all paths:** `apps-microservices/redis-client-frontend/` (paths below are relative to it unless noted). Package manager: **pnpm**. The `@/*` tsconfig alias maps to the service root.

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `package.json` | add `jose`, `vitest`, test scripts | 0 |
| `vitest.config.ts` | Vitest config + `@` alias | 0 |
| `lib/auth/config.ts` | read/validate env, resolve client creds, parse allow-list | 0 |
| `lib/auth/oauth.ts` | PKCE gen, authorize URL, token exchange, token verify | 1 |
| `lib/auth/session.ts` | sign/verify the `rcf_session` cookie JWT (edge-safe) | 2 |
| `lib/auth/flow.ts` | framework-free orchestration: `startLogin` / `completeCallback` | 3 |
| `app/auth/login/route.ts` | GET → start PKCE, set cookies, redirect to /authorize | 4 |
| `app/auth/callback/route.ts` | GET → run callback, set session, redirect | 4 |
| `app/auth/logout/route.ts` | GET → clear session (+ optional central logout) | 4 |
| `app/auth/denied/page.tsx` | "not authorized" page | 4 |
| `middleware.ts` | **rewrite** — verify session, gate all routes | 4 |
| `app/login/page.tsx` | **delete** (old paste-token page) | 4 |
| `app/page.tsx` | read session, pass `userEmail` to header | 5 |
| `components/cache-header.tsx` | show email + Sign out link | 5 |
| `docker-compose.yml` (repo root) | add `networks: [services-net]` + auth env | 6 |
| `.env.example` | document required env | 6 |
| `CLAUDE.md` (service) | document the new auth flow | 6 |

---

### Task 0: Tooling + auth config

**Goal:** Add `jose` + Vitest, and a tested config module that reads/validates env and resolves client credentials + the email allow-list.

**Files:**
- Modify: `package.json`
- Create: `vitest.config.ts`
- Create: `lib/auth/config.ts`
- Test: `lib/auth/config.test.ts`

**Acceptance Criteria:**
- [ ] `pnpm vitest run lib/auth/config.test.ts` passes.
- [ ] `resolveClientCredentials` prefers the `_REDIS_CLIENT_FRONTEND` suffixed vars over the plain ones.
- [ ] `parseAdminEmails` lowercases, trims, drops empties, returns a `Set`.

**Verify:** `pnpm vitest run lib/auth/config.test.ts` → all tests pass.

**Steps:**

- [ ] **Step 1: Add deps + scripts to `package.json`**

Add to `dependencies`: `"jose": "^5.9.6"`. Add to `devDependencies`: `"vitest": "^2.1.8"`. Add to `scripts`: `"test": "vitest run"`, `"test:watch": "vitest"`. Then run `pnpm install` to update `pnpm-lock.yaml`.

- [ ] **Step 2: Create `vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config"
import path from "node:path"

export default defineConfig({
  test: { environment: "node" },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
})
```

- [ ] **Step 3: Write the failing test `lib/auth/config.test.ts`**

```ts
import { describe, it, expect } from "vitest"
import { parseAdminEmails, resolveClientCredentials } from "./config"

describe("parseAdminEmails", () => {
  it("lowercases, trims, and drops empties", () => {
    const set = parseAdminEmails(" Alice@HP.fr , bob@hp.fr ,, ")
    expect(set.has("alice@hp.fr")).toBe(true)
    expect(set.has("bob@hp.fr")).toBe(true)
    expect(set.size).toBe(2)
  })
  it("returns empty set for undefined", () => {
    expect(parseAdminEmails(undefined).size).toBe(0)
  })
})

describe("resolveClientCredentials", () => {
  it("prefers the suffixed vars over plain", () => {
    const creds = resolveClientCredentials({
      ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND: "id-suffixed",
      ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND: "secret-suffixed",
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-suffixed", clientSecret: "secret-suffixed" })
  })
  it("falls back to plain vars", () => {
    const creds = resolveClientCredentials({
      ACCOUNT_CLIENT_ID: "id-plain",
      ACCOUNT_CLIENT_SECRET: "secret-plain",
    })
    expect(creds).toEqual({ clientId: "id-plain", clientSecret: "secret-plain" })
  })
  it("throws when neither is set", () => {
    expect(() => resolveClientCredentials({})).toThrow(/Missing ACCOUNT_CLIENT_ID/)
  })
})
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pnpm vitest run lib/auth/config.test.ts`
Expected: FAIL — `Cannot find module './config'`.

- [ ] **Step 5: Implement `lib/auth/config.ts`**

```ts
// Auth configuration: read + validate environment at call time (not import time,
// so tests can vary process.env per case).

type Env = Record<string, string | undefined>

export function parseAdminEmails(raw: string | undefined): Set<string> {
  if (!raw) return new Set()
  return new Set(
    raw
      .split(",")
      .map((e) => e.trim().toLowerCase())
      .filter((e) => e.length > 0),
  )
}

export function resolveClientCredentials(env: Env = process.env): {
  clientId: string
  clientSecret: string
} {
  const clientId =
    env.ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND || env.ACCOUNT_CLIENT_ID
  const clientSecret =
    env.ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND || env.ACCOUNT_CLIENT_SECRET
  if (!clientId || !clientSecret) {
    throw new Error(
      "[redis-client] Missing ACCOUNT_CLIENT_ID(_REDIS_CLIENT_FRONTEND) / ACCOUNT_CLIENT_SECRET(_REDIS_CLIENT_FRONTEND)",
    )
  }
  return { clientId, clientSecret }
}

function req(name: string, env: Env): string {
  const v = env[name]
  if (!v) throw new Error(`[redis-client] Missing required env var: ${name}`)
  return v
}

export interface AuthConfig {
  accountPublicUrl: string
  accountBaseUrl: string
  clientId: string
  clientSecret: string
  redirectUri: string
  jwtSecret: string
  adminEmails: Set<string>
  secureCookie: boolean
  sessionTtlSeconds: number
  centralLogout: boolean
}

export function getAuthConfig(env: Env = process.env): AuthConfig {
  const { clientId, clientSecret } = resolveClientCredentials(env)
  return {
    accountPublicUrl: req("ACCOUNT_PUBLIC_URL", env).replace(/\/+$/, ""),
    accountBaseUrl: req("ACCOUNT_BASE_URL", env).replace(/\/+$/, ""),
    clientId,
    clientSecret,
    redirectUri: req("ACCOUNT_REDIRECT_URI", env),
    jwtSecret: req("JWT_SECRET", env),
    adminEmails: parseAdminEmails(env.ADMIN_EMAILS),
    secureCookie: (env.SECURE_COOKIE || "false").toLowerCase() === "true",
    sessionTtlSeconds: Number(env.SESSION_TTL || "28800"),
    centralLogout: (env.SSO_CENTRAL_LOGOUT || "false").toLowerCase() === "true",
  }
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm vitest run lib/auth/config.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/redis-client-frontend/package.json \
        apps-microservices/redis-client-frontend/pnpm-lock.yaml \
        apps-microservices/redis-client-frontend/vitest.config.ts \
        apps-microservices/redis-client-frontend/lib/auth/config.ts \
        apps-microservices/redis-client-frontend/lib/auth/config.test.ts
git commit -m "feat(redis-client-frontend): add jose+vitest and auth config module"
```

---

### Task 1: OAuth/PKCE primitives

**Goal:** PKCE generation, the URL-encoded authorize URL, the token exchange, and the access-token signature verification — all pure functions.

**Files:**
- Create: `lib/auth/oauth.ts`
- Test: `lib/auth/oauth.test.ts`

**Acceptance Criteria:**
- [ ] `challenge` equals base64url(SHA-256(verifier)).
- [ ] `buildAuthorizeUrl` URL-encodes every param and includes `code_challenge_method=S256`.
- [ ] `verifyAndExtract` accepts a valid HS256 token (returns `{email}` from `sub`) and rejects a tampered/expired one.
- [ ] `exchangeCode` sends HTTP Basic auth + the correct form body.

**Verify:** `pnpm vitest run lib/auth/oauth.test.ts` → all tests pass.

**Steps:**

- [ ] **Step 1: Write the failing test `lib/auth/oauth.test.ts`**

```ts
import { describe, it, expect, vi, afterEach } from "vitest"
import { SignJWT } from "jose"
import {
  generatePkce,
  randomState,
  buildAuthorizeUrl,
  exchangeCode,
  verifyAndExtract,
} from "./oauth"

const b64url = (buf: ArrayBuffer) =>
  Buffer.from(new Uint8Array(buf)).toString("base64")
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")

afterEach(() => vi.restoreAllMocks())

describe("generatePkce", () => {
  it("produces challenge = b64url(sha256(verifier))", async () => {
    const { verifier, challenge } = await generatePkce()
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
    expect(challenge).toBe(b64url(digest))
    expect(verifier).not.toContain("=")
  })
})

describe("randomState", () => {
  it("is url-safe and non-empty", () => {
    expect(randomState()).toMatch(/^[A-Za-z0-9_-]+$/)
  })
})

describe("buildAuthorizeUrl", () => {
  it("encodes params and sets S256", () => {
    const url = buildAuthorizeUrl({
      publicUrl: "http://localhost:8601",
      clientId: "cid",
      redirectUri: "http://localhost:3551/auth/callback",
      challenge: "chal",
      state: "st",
    })
    const u = new URL(url)
    expect(u.origin + u.pathname).toBe("http://localhost:8601/authorize")
    expect(u.searchParams.get("response_type")).toBe("code")
    expect(u.searchParams.get("redirect_uri")).toBe("http://localhost:3551/auth/callback")
    expect(u.searchParams.get("code_challenge_method")).toBe("S256")
    expect(url).toContain("redirect_uri=http%3A%2F%2Flocalhost%3A3551%2Fauth%2Fcallback")
  })
})

describe("exchangeCode", () => {
  it("posts Basic auth + form body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "tok" }),
    })
    vi.stubGlobal("fetch", fetchMock)
    const res = await exchangeCode({
      baseUrl: "http://acct:8600",
      clientId: "cid",
      clientSecret: "sec",
      code: "code123",
      redirectUri: "http://localhost:3551/auth/callback",
      verifier: "ver",
    })
    expect(res.access_token).toBe("tok")
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("http://acct:8600/token")
    expect(init.headers.Authorization).toBe("Basic " + Buffer.from("cid:sec").toString("base64"))
    expect(init.body).toContain("grant_type=authorization_code")
    expect(init.body).toContain("code_verifier=ver")
  })
  it("throws on non-200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }))
    await expect(
      exchangeCode({ baseUrl: "b", clientId: "c", clientSecret: "s", code: "x", redirectUri: "r", verifier: "v" }),
    ).rejects.toThrow(/401/)
  })
})

describe("verifyAndExtract", () => {
  const secret = "test-secret"
  const key = new TextEncoder().encode(secret)

  it("extracts email from sub on a valid token", async () => {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("alice@hp.fr")
      .setExpirationTime("5m")
      .sign(key)
    const id = await verifyAndExtract(token, secret)
    expect(id.email).toBe("alice@hp.fr")
  })

  it("rejects a token signed with the wrong secret", async () => {
    const token = await new SignJWT({})
      .setProtectedHeader({ alg: "HS256" })
      .setSubject("alice@hp.fr")
      .setExpirationTime("5m")
      .sign(new TextEncoder().encode("wrong-secret"))
    await expect(verifyAndExtract(token, secret)).rejects.toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run lib/auth/oauth.test.ts`
Expected: FAIL — `Cannot find module './oauth'`.

- [ ] **Step 3: Implement `lib/auth/oauth.ts`**

```ts
import { jwtVerify } from "jose"

function b64url(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  return Buffer.from(bytes)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "")
}

export interface Pkce {
  verifier: string
  challenge: string
}

export async function generatePkce(): Promise<Pkce> {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(32)))
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
  return { verifier, challenge: b64url(digest) }
}

export function randomState(): string {
  return b64url(crypto.getRandomValues(new Uint8Array(16)))
}

export function buildAuthorizeUrl(opts: {
  publicUrl: string
  clientId: string
  redirectUri: string
  challenge: string
  state: string
}): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: opts.clientId,
    redirect_uri: opts.redirectUri,
    code_challenge: opts.challenge,
    code_challenge_method: "S256",
    state: opts.state,
  })
  return `${opts.publicUrl}/authorize?${params.toString()}`
}

export interface TokenResponse {
  access_token: string
  refresh_token?: string
  token_type?: string
  expires_in?: number
}

export async function exchangeCode(opts: {
  baseUrl: string
  clientId: string
  clientSecret: string
  code: string
  redirectUri: string
  verifier: string
}): Promise<TokenResponse> {
  const basic = Buffer.from(`${opts.clientId}:${opts.clientSecret}`).toString("base64")
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: opts.code,
    redirect_uri: opts.redirectUri,
    code_verifier: opts.verifier,
  })
  const r = await fetch(`${opts.baseUrl}/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${basic}`,
    },
    body: body.toString(),
  })
  if (!r.ok) {
    throw new Error(`[redis-client] token exchange failed: ${r.status}`)
  }
  return (await r.json()) as TokenResponse
}

export interface Identity {
  email: string
  name?: string
}

export async function verifyAndExtract(accessToken: string, jwtSecret: string): Promise<Identity> {
  const key = new TextEncoder().encode(jwtSecret)
  // aud is intentionally NOT verified (account-service sets aud=client_id).
  const { payload } = await jwtVerify(accessToken, key, { algorithms: ["HS256"] })
  const email = (payload.sub as string | undefined) || (payload.email as string | undefined)
  if (!email) throw new Error("[redis-client] token missing sub/email claim")
  return { email, name: payload.name as string | undefined }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run lib/auth/oauth.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/redis-client-frontend/lib/auth/oauth.ts \
        apps-microservices/redis-client-frontend/lib/auth/oauth.test.ts
git commit -m "feat(redis-client-frontend): add OAuth2 PKCE primitives + token verify"
```

---

### Task 2: Session cookie module

**Goal:** Sign/verify the `rcf_session` JWT with a dedicated `SESSION_SECRET`. Edge-safe (jose only, no Node APIs) so middleware can import it.

**Files:**
- Create: `lib/auth/session.ts`
- Test: `lib/auth/session.test.ts`

**Acceptance Criteria:**
- [ ] sign → read round-trips `{email, name}`.
- [ ] expired token → `readSession` returns `null`.
- [ ] tampered/garbage token → `null` (no throw).
- [ ] `SESSION_COOKIE === "rcf_session"`.

**Verify:** `pnpm vitest run lib/auth/session.test.ts` → all tests pass.

**Steps:**

- [ ] **Step 1: Write the failing test `lib/auth/session.test.ts`**

```ts
import { describe, it, expect, beforeEach } from "vitest"
import { createSessionToken, readSession, SESSION_COOKIE } from "./session"

beforeEach(() => {
  process.env.SESSION_SECRET = "unit-test-session-secret"
})

describe("session", () => {
  it("exposes the cookie name", () => {
    expect(SESSION_COOKIE).toBe("rcf_session")
  })

  it("round-trips claims", async () => {
    const tok = await createSessionToken({ email: "alice@hp.fr", name: "Alice" }, 3600)
    const claims = await readSession(tok)
    expect(claims).toEqual({ email: "alice@hp.fr", name: "Alice" })
  })

  it("returns null for an expired token", async () => {
    const tok = await createSessionToken({ email: "alice@hp.fr" }, -1)
    expect(await readSession(tok)).toBeNull()
  })

  it("returns null for garbage", async () => {
    expect(await readSession("not-a-jwt")).toBeNull()
    expect(await readSession(undefined)).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run lib/auth/session.test.ts`
Expected: FAIL — `Cannot find module './session'`.

- [ ] **Step 3: Implement `lib/auth/session.ts`**

```ts
import { SignJWT, jwtVerify } from "jose"

export const SESSION_COOKIE = "rcf_session"

function sessionKey(): Uint8Array {
  const secret = process.env.SESSION_SECRET
  if (!secret) throw new Error("[redis-client] Missing SESSION_SECRET")
  return new TextEncoder().encode(secret)
}

export interface SessionClaims {
  email: string
  name?: string
}

export async function createSessionToken(claims: SessionClaims, ttlSeconds: number): Promise<string> {
  const builder = new SignJWT({ name: claims.name })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(claims.email)
    .setIssuedAt()
    .setExpirationTime(Math.floor(Date.now() / 1000) + ttlSeconds)
  return builder.sign(sessionKey())
}

export async function readSession(token: string | undefined): Promise<SessionClaims | null> {
  if (!token) return null
  try {
    const { payload } = await jwtVerify(token, sessionKey(), { algorithms: ["HS256"] })
    const email = payload.sub
    if (!email) return null
    return { email: email as string, name: payload.name as string | undefined }
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run lib/auth/session.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/redis-client-frontend/lib/auth/session.ts \
        apps-microservices/redis-client-frontend/lib/auth/session.test.ts
git commit -m "feat(redis-client-frontend): add signed session cookie module"
```

---

### Task 3: Auth flow orchestration

**Goal:** Framework-free `startLogin()` and `completeCallback()` that compose config + oauth + session and return plain result objects (no `NextResponse`). This is where the allow-list and all branching live, so it is fully unit-tested.

**Files:**
- Create: `lib/auth/flow.ts`
- Test: `lib/auth/flow.test.ts`

**Acceptance Criteria:**
- [ ] `startLogin` returns `{authorizeUrl, verifier, state, secureCookie}` from config + PKCE.
- [ ] `completeCallback` returns `error` on missing code/state, state mismatch, or missing verifier.
- [ ] `completeCallback` returns `denied` when the email is not in the allow-list.
- [ ] `completeCallback` returns `ok` with a session token when the email is allowed.

**Verify:** `pnpm vitest run lib/auth/flow.test.ts` → all tests pass.

**Steps:**

- [ ] **Step 1: Write the failing test `lib/auth/flow.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach } from "vitest"
import * as oauth from "./oauth"
import * as session from "./session"
import * as config from "./config"
import { startLogin, completeCallback } from "./flow"

const baseCfg: config.AuthConfig = {
  accountPublicUrl: "http://localhost:8601",
  accountBaseUrl: "http://acct:8600",
  clientId: "cid",
  clientSecret: "sec",
  redirectUri: "http://localhost:3551/auth/callback",
  jwtSecret: "jwt",
  adminEmails: new Set(["alice@hp.fr"]),
  secureCookie: false,
  sessionTtlSeconds: 3600,
  centralLogout: false,
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(config, "getAuthConfig").mockReturnValue(baseCfg)
})

describe("startLogin", () => {
  it("builds the authorize url with a fresh pkce + state", async () => {
    vi.spyOn(oauth, "generatePkce").mockResolvedValue({ verifier: "ver", challenge: "chal" })
    vi.spyOn(oauth, "randomState").mockReturnValue("st")
    const out = await startLogin()
    expect(out.verifier).toBe("ver")
    expect(out.state).toBe("st")
    expect(out.secureCookie).toBe(false)
    expect(out.authorizeUrl).toContain("http://localhost:8601/authorize?")
    expect(out.authorizeUrl).toContain("code_challenge=chal")
  })
})

describe("completeCallback", () => {
  it("errors on missing code/state", async () => {
    expect((await completeCallback({})).status).toBe("error")
  })
  it("errors on state mismatch", async () => {
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "b", verifierCookie: "v" })
    expect(r).toEqual({ status: "error", reason: "state_mismatch" })
  })
  it("errors on missing verifier", async () => {
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a" })
    expect(r).toEqual({ status: "error", reason: "missing_verifier" })
  })
  it("denies a non-allow-listed email", async () => {
    vi.spyOn(oauth, "exchangeCode").mockResolvedValue({ access_token: "tok" })
    vi.spyOn(oauth, "verifyAndExtract").mockResolvedValue({ email: "mallory@hp.fr" })
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "denied", email: "mallory@hp.fr" })
  })
  it("returns ok + session token for an allowed email", async () => {
    vi.spyOn(oauth, "exchangeCode").mockResolvedValue({ access_token: "tok" })
    vi.spyOn(oauth, "verifyAndExtract").mockResolvedValue({ email: "Alice@hp.fr", name: "Alice" })
    vi.spyOn(session, "createSessionToken").mockResolvedValue("session-jwt")
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "ok", sessionToken: "session-jwt", ttlSeconds: 3600, secureCookie: false })
  })
  it("errors when token exchange throws", async () => {
    vi.spyOn(oauth, "exchangeCode").mockRejectedValue(new Error("boom"))
    const r = await completeCallback({ code: "c", state: "a", stateCookie: "a", verifierCookie: "v" })
    expect(r).toEqual({ status: "error", reason: "exchange_failed" })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run lib/auth/flow.test.ts`
Expected: FAIL — `Cannot find module './flow'`.

- [ ] **Step 3: Implement `lib/auth/flow.ts`**

```ts
import { getAuthConfig } from "./config"
import { generatePkce, randomState, buildAuthorizeUrl, exchangeCode, verifyAndExtract } from "./oauth"
import { createSessionToken } from "./session"

export interface LoginStart {
  authorizeUrl: string
  verifier: string
  state: string
  secureCookie: boolean
}

export async function startLogin(): Promise<LoginStart> {
  const cfg = getAuthConfig()
  const { verifier, challenge } = await generatePkce()
  const state = randomState()
  const authorizeUrl = buildAuthorizeUrl({
    publicUrl: cfg.accountPublicUrl,
    clientId: cfg.clientId,
    redirectUri: cfg.redirectUri,
    challenge,
    state,
  })
  return { authorizeUrl, verifier, state, secureCookie: cfg.secureCookie }
}

export type CallbackResult =
  | { status: "ok"; sessionToken: string; ttlSeconds: number; secureCookie: boolean }
  | { status: "denied"; email: string }
  | { status: "error"; reason: string }

export async function completeCallback(input: {
  code?: string | null
  state?: string | null
  stateCookie?: string
  verifierCookie?: string
}): Promise<CallbackResult> {
  const cfg = getAuthConfig()

  if (!input.code || !input.state) return { status: "error", reason: "missing_code_or_state" }
  if (!input.stateCookie || input.stateCookie !== input.state) {
    return { status: "error", reason: "state_mismatch" }
  }
  if (!input.verifierCookie) return { status: "error", reason: "missing_verifier" }

  let tokens
  try {
    tokens = await exchangeCode({
      baseUrl: cfg.accountBaseUrl,
      clientId: cfg.clientId,
      clientSecret: cfg.clientSecret,
      code: input.code,
      redirectUri: cfg.redirectUri,
      verifier: input.verifierCookie,
    })
  } catch {
    return { status: "error", reason: "exchange_failed" }
  }

  let identity
  try {
    identity = await verifyAndExtract(tokens.access_token, cfg.jwtSecret)
  } catch {
    return { status: "error", reason: "token_invalid" }
  }

  if (!cfg.adminEmails.has(identity.email.toLowerCase())) {
    return { status: "denied", email: identity.email }
  }

  const sessionToken = await createSessionToken(
    { email: identity.email, name: identity.name },
    cfg.sessionTtlSeconds,
  )
  return { status: "ok", sessionToken, ttlSeconds: cfg.sessionTtlSeconds, secureCookie: cfg.secureCookie }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run lib/auth/flow.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/redis-client-frontend/lib/auth/flow.ts \
        apps-microservices/redis-client-frontend/lib/auth/flow.test.ts
git commit -m "feat(redis-client-frontend): add SSO auth flow orchestration"
```

---

### Task 4: Route handlers, denied page, middleware rewrite, remove old login

**Goal:** Wire the tested flow into App Router routes + edge middleware; delete the old paste-token login.

> **TDD note:** All branching logic is already covered by `flow.test.ts` / `session.test.ts`. These routes are pure wiring (translate result objects → `NextResponse`). If the repo's `tdd-gate.sh` hook blocks an edit to a `route.ts`/`middleware.ts` because no colocated test exists, that's expected for wiring files — re-run after confirming the logic tests pass, or add a one-line smoke test. Verification for this task is `pnpm build` + `pnpm lint` + the manual E2E in Task 6.

**Files:**
- Create: `app/auth/login/route.ts`
- Create: `app/auth/callback/route.ts`
- Create: `app/auth/logout/route.ts`
- Create: `app/auth/denied/page.tsx`
- Modify: `middleware.ts` (full rewrite)
- Delete: `app/login/page.tsx`

**Acceptance Criteria:**
- [ ] `pnpm build` succeeds (TypeScript errors are enforced — `ignoreBuildErrors:false`).
- [ ] `pnpm lint` passes.
- [ ] `middleware.ts` matcher excludes `/auth/*`, `_next/*`, favicons.
- [ ] `app/login/page.tsx` no longer exists; no `ADMIN_TOKEN` references remain in the repo (`git grep ADMIN_TOKEN apps-microservices/redis-client-frontend` is empty except docs).

**Verify:** `pnpm build && pnpm lint` → success; `git grep -n ADMIN_TOKEN apps-microservices/redis-client-frontend -- ':!*.md'` → no matches.

**Steps:**

- [ ] **Step 1: Create `app/auth/login/route.ts`**

```ts
import { NextResponse } from "next/server"
import { startLogin } from "@/lib/auth/flow"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET() {
  const { authorizeUrl, verifier, state, secureCookie } = await startLogin()
  const res = NextResponse.redirect(authorizeUrl)
  const opts = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: secureCookie,
    path: "/",
    maxAge: 600,
  }
  res.cookies.set("oauth_verifier", verifier, opts)
  res.cookies.set("oauth_state", state, opts)
  return res
}
```

- [ ] **Step 2: Create `app/auth/callback/route.ts`**

```ts
import { NextResponse, type NextRequest } from "next/server"
import { completeCallback } from "@/lib/auth/flow"
import { SESSION_COOKIE } from "@/lib/auth/session"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

function clearPkce(res: NextResponse): NextResponse {
  res.cookies.delete("oauth_verifier")
  res.cookies.delete("oauth_state")
  return res
}

export async function GET(request: NextRequest) {
  const result = await completeCallback({
    code: request.nextUrl.searchParams.get("code"),
    state: request.nextUrl.searchParams.get("state"),
    stateCookie: request.cookies.get("oauth_state")?.value,
    verifierCookie: request.cookies.get("oauth_verifier")?.value,
  })

  if (result.status === "ok") {
    const res = NextResponse.redirect(new URL("/", request.url))
    res.cookies.set(SESSION_COOKIE, result.sessionToken, {
      httpOnly: true,
      sameSite: "lax",
      secure: result.secureCookie,
      path: "/",
      maxAge: result.ttlSeconds,
    })
    return clearPkce(res)
  }

  if (result.status === "denied") {
    const url = new URL("/auth/denied", request.url)
    url.searchParams.set("email", result.email)
    return clearPkce(NextResponse.redirect(url))
  }

  const url = new URL("/auth/login", request.url)
  url.searchParams.set("error", result.reason)
  return clearPkce(NextResponse.redirect(url))
}
```

- [ ] **Step 3: Create `app/auth/logout/route.ts`**

```ts
import { NextResponse, type NextRequest } from "next/server"
import { getAuthConfig } from "@/lib/auth/config"
import { SESSION_COOKIE } from "@/lib/auth/session"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const cfg = getAuthConfig()
  const loginUrl = new URL("/auth/login", request.url).toString()
  const target = cfg.centralLogout
    ? `${cfg.accountPublicUrl}/logout?post_logout_redirect_uri=${encodeURIComponent(loginUrl)}`
    : loginUrl
  const res = NextResponse.redirect(target)
  res.cookies.delete(SESSION_COOKIE)
  return res
}
```

- [ ] **Step 4: Create `app/auth/denied/page.tsx`**

```tsx
export const dynamic = "force-dynamic"

export default async function DeniedPage({
  searchParams,
}: {
  searchParams: Promise<{ email?: string }>
}) {
  const { email } = await searchParams
  return (
    <main className="min-h-screen bg-background flex items-center justify-center">
      <div className="w-full max-w-md space-y-4 p-8 text-center">
        <h1 className="text-2xl font-bold">Access denied</h1>
        <p className="text-muted-foreground">
          {email ? `The account ${email} is not authorized` : "Your account is not authorized"} to use the
          Redis Cache Manager.
        </p>
        <p className="text-sm text-muted-foreground">Contact an administrator to request access.</p>
        <a href="/auth/logout" className="text-sm underline">
          Sign out
        </a>
      </div>
    </main>
  )
}
```

- [ ] **Step 5: Rewrite `middleware.ts`**

```ts
// Auth middleware — gates all routes on the signed rcf_session cookie (account-service SSO).
import { NextResponse, type NextRequest } from "next/server"
import { readSession, SESSION_COOKIE } from "@/lib/auth/session"

export async function middleware(request: NextRequest) {
  const session = await readSession(request.cookies.get(SESSION_COOKIE)?.value)
  if (session) {
    return NextResponse.next()
  }

  // Server actions (POST to same origin) get a 401 instead of a redirect.
  if (request.method === "POST") {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  const loginUrl = new URL("/auth/login", request.url)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  // Protect everything except static assets and the /auth/* routes (login, callback, logout, denied).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon-.*|apple-icon|auth).*)"],
}
```

- [ ] **Step 6: Delete the old login page**

```bash
git rm apps-microservices/redis-client-frontend/app/login/page.tsx
```

- [ ] **Step 7: Verify build + lint + no ADMIN_TOKEN**

Run: `pnpm build && pnpm lint`
Expected: build + lint succeed.
Run: `git grep -n ADMIN_TOKEN apps-microservices/redis-client-frontend -- ':!*.md'`
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/redis-client-frontend/app/auth \
        apps-microservices/redis-client-frontend/middleware.ts
git rm apps-microservices/redis-client-frontend/app/login/page.tsx
git commit -m "feat(redis-client-frontend): SSO route handlers + session middleware, drop ADMIN_TOKEN login"
```

---

### Task 5: UI — show signed-in email + Sign out

**Goal:** Surface the logged-in user and a sign-out link in the header.

**Files:**
- Modify: `components/cache-header.tsx`
- Modify: `app/page.tsx`

**Acceptance Criteria:**
- [ ] `CacheHeader` accepts an optional `userEmail` prop and renders it + a "Sign out" link to `/auth/logout` when present.
- [ ] `app/page.tsx` reads the session and passes `userEmail`.
- [ ] `pnpm build && pnpm lint` succeed.

**Verify:** `pnpm build && pnpm lint` → success.

**Steps:**

- [ ] **Step 1: Add `userEmail` to `CacheHeaderProps` and render it (`components/cache-header.tsx`)**

Change the interface (around line 12-17) to add `userEmail`:

```tsx
interface CacheHeaderProps {
  totalKeys: number
  totalSize: number
  lastRefreshed: Date
  onRefresh?: () => void
  userEmail?: string
}

export function CacheHeader({ totalKeys, totalSize, lastRefreshed, onRefresh, userEmail }: CacheHeaderProps) {
```

Then replace the title block (the `<div>` containing the `<h1>Redis Cache Manager</h1>`, around lines 78-81) with a row that adds the user + sign-out on the right:

```tsx
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">Redis Cache Manager</h1>
          <p className="text-muted-foreground">Monitor and manage your cached data</p>
        </div>
        {userEmail && (
          <div className="text-right text-sm">
            <p className="text-muted-foreground">{userEmail}</p>
            <a href="/auth/logout" className="underline">
              Sign out
            </a>
          </div>
        )}
      </div>
```

- [ ] **Step 2: Pass the session email from `app/page.tsx`**

Replace the file with:

```tsx
import { getCachedData } from "@/lib/application/get-cached-data"
import { CacheHeader } from "@/components/cache-header"
import { CacheTable } from "@/components/cache-table"
import { cookies } from "next/headers"
import { readSession, SESSION_COOKIE } from "@/lib/auth/session"

export default async function Home() {
  const { entries, metadata, error } = await getCachedData()
  const cookieStore = await cookies()
  const session = await readSession(cookieStore.get(SESSION_COOKIE)?.value)

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {error && <div className="mb-6 p-4 bg-destructive/10 text-destructive rounded-lg">{error}</div>}

        <CacheHeader
          totalKeys={metadata.totalKeys}
          totalSize={metadata.totalSize}
          lastRefreshed={metadata.lastRefreshed}
          userEmail={session?.email}
        />

        <div className="mt-8">
          <CacheTable entries={entries} />
        </div>
      </div>
    </main>
  )
}
```

- [ ] **Step 3: Verify build + lint**

Run: `pnpm build && pnpm lint`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/redis-client-frontend/components/cache-header.tsx \
        apps-microservices/redis-client-frontend/app/page.tsx
git commit -m "feat(redis-client-frontend): show signed-in email and sign-out link"
```

---

### Task 6: Compose/network wiring, env docs, client registration, manual E2E

**Goal:** Make the service reachable to account-service and documented; provide the registration runbook + manual end-to-end check.

**Files:**
- Modify: `docker-compose.yml` (repo root, `redis-client-frontend` block ~L1425)
- Create: `apps-microservices/redis-client-frontend/.env.example`
- Modify: `apps-microservices/redis-client-frontend/CLAUDE.md`

**Acceptance Criteria:**
- [ ] `redis-client-frontend` joins `services-net` and has all auth env vars.
- [ ] `.env.example` lists every required var.
- [ ] CLAUDE.md documents the SSO flow + the removed ADMIN_TOKEN.
- [ ] Manual E2E (below) passes against a running stack.

**Verify:** `docker compose config redis-client-frontend` shows `services-net` + the env vars; manual E2E checklist passes.

**Steps:**

- [ ] **Step 1: Update the `redis-client-frontend` service in `docker-compose.yml`**

Replace the `environment:` list and append a `networks:` block (keep `profiles`, `build`, `ports`, `logging` as-is):

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
      - SESSION_SECRET=${REDIS_CLIENT_SESSION_SECRET}
      - ADMIN_EMAILS=${REDIS_CLIENT_ADMIN_EMAILS}
      - SECURE_COOKIE=${ACCOUNT_SECURE_COOKIE:-false}
      - SESSION_TTL=${REDIS_CLIENT_SESSION_TTL:-28800}
      - SSO_CENTRAL_LOGOUT=${REDIS_CLIENT_CENTRAL_LOGOUT:-false}
    networks:
      - services-net
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Redis (existing)
REDIS_HOST=
REDIS_PORT=
REDIS_SECRET=

# account-service SSO (OAuth 2.1 + PKCE)
SERVICE_NAME=redis-client-frontend
ACCOUNT_BASE_URL=http://account-service-backend:8600   # server-to-server token exchange
ACCOUNT_PUBLIC_URL=http://localhost:8601               # browser-facing /authorize
ACCOUNT_REDIRECT_URI=http://localhost:3551/auth/callback  # MUST be registered on the client
ACCOUNT_CLIENT_ID_REDIS_CLIENT_FRONTEND=               # from account-service registration
ACCOUNT_CLIENT_SECRET_REDIS_CLIENT_FRONTEND=           # shown once at registration
JWT_SECRET=                                            # shared HS256 secret to verify account-service tokens
SESSION_SECRET=                                        # independent secret signing the rcf_session cookie
ADMIN_EMAILS=alice@hellopro.fr,bob@hellopro.fr         # allow-list (csv)
SECURE_COOKIE=false                                    # true in prod / behind HTTPS
SESSION_TTL=28800                                      # session lifetime seconds (8h)
SSO_CENTRAL_LOGOUT=false                               # true → also RP-logout at account-service
```

- [ ] **Step 3: Document in `CLAUDE.md`**

Replace the `## Environment Variables` table and the auth bullet in `## Conventions` to describe SSO: the `/auth/login` → account-service `/authorize` → `/auth/callback` flow, the `rcf_session` 8h cookie, the `ADMIN_EMAILS` allow-list, and that the old `ADMIN_TOKEN` paste-login has been removed. (Add the env vars from `.env.example` to the table.)

- [ ] **Step 4: Register the OAuth client in account-service (one-time, per environment)**

Via the Vue admin "Services" page, or the API:
```bash
curl -X POST "$ACCOUNT_BASE_URL/api/v1/admin/services" \
  -H "Authorization: Bearer <account-service-user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "redis-client-frontend",
    "redirect_uris": ["http://localhost:3551/auth/callback"],
    "description": "Redis cache manager admin UI"
  }'
```
Capture `client_id` + `client_secret` from the 201 response into the env vars. Add the prod callback URL to `redirect_uris` before prod deploy.

- [ ] **Step 5: Manual E2E (against the running stack: `docker compose --profile app up`)**

  1. Visit `http://localhost:3551/` unauthenticated → redirected to account-service login (8601).
  2. Log in with an email in `ADMIN_EMAILS` → land back on `/` with the cache table; header shows your email.
  3. Log in with an email NOT in `ADMIN_EMAILS` → `/auth/denied`.
  4. Click "Sign out" → session cleared, back to login.
  5. Delete a key / Clear All still work while authenticated; calling a server action after the cookie is cleared returns 401.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml \
        apps-microservices/redis-client-frontend/.env.example \
        apps-microservices/redis-client-frontend/CLAUDE.md
git commit -m "feat(redis-client-frontend): wire account-service SSO env + services-net network"
```

---

## Self-Review

**Spec coverage:**
- D1 native BFF → Tasks 1–4. D2 own 8h session → Task 2 (`SESSION_TTL` default 28800). D3 email allow-list → Tasks 0 (`parseAdminEmails`) + 3 (`completeCallback` denied branch). D4 remove old login → Task 4 Step 6. D5 logout + optional central → Task 4 Step 3. D6 verify token sig → Task 1 `verifyAndExtract`; separate `SESSION_SECRET` → Task 2. §5.1 network → Task 6 Step 1. §5.2 client registration → Task 6 Step 4. §6 error handling → Task 3 result branches + Task 4 callback mapping. §8 testing → Tasks 0–3 test files + Task 6 manual E2E.
- No gaps found.

**Placeholder scan:** No TBD/TODO; every code step has complete code. (Task 6 Step 3 CLAUDE.md edit is descriptive prose, acceptable for a docs edit — the content to write is fully specified by `.env.example`.)

**Type consistency:** `AuthConfig` shape used in `config.ts`, `flow.ts`, and `flow.test.ts` matches. `SessionClaims {email, name?}` consistent across `session.ts` and consumers. `CallbackResult` union consumed by the callback route matches `flow.ts`. `SESSION_COOKIE` constant single-sourced from `session.ts`. `verifyAndExtract(token, jwtSecret)` signature consistent between definition (Task 1) and call (Task 3).

---

## Execution Notes

- **Edge runtime:** `middleware.ts` imports only `lib/auth/session.ts` (jose + `process.env.SESSION_SECRET`) — edge-safe. `process.env.SESSION_SECRET` is available at runtime in the standalone Node server. Route handlers pin `runtime = "nodejs"` (they use `Buffer` + `fetch`).
- **Lockfile:** Task 0 changes `package.json`; run `pnpm install` so `pnpm-lock.yaml` updates (the Dockerfile runs `pnpm install`, so the lockfile must be committed in sync).
- **TDD gate:** logic is fully tested in `lib/auth/*.test.ts`; route/middleware/page files are wiring verified by `pnpm build`/`pnpm lint` + manual E2E.
