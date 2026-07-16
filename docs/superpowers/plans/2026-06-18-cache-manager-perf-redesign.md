# Cache-Manager Perf Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `redis-client-frontend` from eagerly loading the entire shared Redis keyspace on page open / Refresh; make it a paginated, SCAN-based, consent-gated key browser that never disrupts the fleet's shared Redis.

**Architecture:** Page open renders a shell with **zero** Redis contact. A consent `ConfirmDialog` ("Scan keys") initiates a single paginated SCAN. Each page reads `TTL`/`TYPE`/`MEMORY USAGE` per key — **never `GET`** (the value was never displayed). Search maps to a server-side `MATCH` glob; "Load more" advances the SCAN cursor. Total Keys = `DBSIZE` (O(1)); Total Size is dropped. Scan-state transitions live in a pure, unit-tested module; the three UI components are thin over it.

**Tech Stack:** Next.js 16 (App Router, Server Components, server actions), `redis@^4.6.15` (SCAN/TYPE/TTL/MEMORY USAGE/DBSIZE), Radix AlertDialog, vitest@^2.1.8 (node env).

**Spec:** `docs/superpowers/specs/2026-06-18-cache-manager-perf-redesign-design.md`

**Verified facts (from code + Context7):**
- `client.scan(cursor, { MATCH, COUNT })` returns `{ cursor: number, keys: string[] }`; `cursor === 0` means iteration complete (the existing `getAllKeys` loop at `redis-cache-repository.ts:64-68` already relies on this — cursor is a number).
- `redis@4` exposes `client.type(key)`, `client.ttl(key)`, `client.memoryUsage(key)` (returns `number | null`), `client.dbSize()`.
- `SCAN COUNT` is a hint — a page may return more/fewer than COUNT keys; rely on `nextCursor !== 0` for "more", never on batch length.
- Search maps to a Redis **glob** `*term*` (not regex); `*` `?` `[` in the term are glob metacharacters (documented in the filter placeholder).
- Local `node_modules` may be empty (VM-only builds). The vitest tests below (Tasks 1–3) mock `redis` / the repository, so they need only `vitest` — run them wherever `pnpm install` has run. Task 4 verify (`pnpm build` + `pnpm lint`) is the VM gate.

---

### Task 1: Domain type + pure scan-state logic

**Goal:** Replace the value-carrying `CacheEntry` with a lean `KeyMeta` and add a pure, unit-tested scan-state module (append/replace transitions + glob builder) that the client brain will consume.

**Files:**
- Modify (full rewrite): `apps-microservices/redis-client-frontend/lib/domain/cache-entry.ts`
- Create: `apps-microservices/redis-client-frontend/lib/application/scan-state.ts`
- Test: `apps-microservices/redis-client-frontend/lib/application/scan-state.test.ts`

**Acceptance Criteria:**
- [ ] `KeyMeta = { key, type, ttl?, size }` exported from `cache-entry.ts`; `CacheEntry`/`CacheMetadata` removed.
- [ ] `initialState` has `scanned: false`, empty entries, `total: null`.
- [ ] `applyScanResult(state, result, reset=true)` replaces entries and adopts `result.total`; `reset=false` appends and keeps prior `total`.
- [ ] An `error` result sets `error` + `scanned: true` and preserves existing entries.
- [ ] `toMatchGlob("")` → `"*"`; `toMatchGlob(" foo ")` → `"*foo*"`.

**Verify:** `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/application/scan-state.test.ts` → all pass.

**Steps:**

- [ ] **Step 1: Rewrite the domain type**

`lib/domain/cache-entry.ts` (full file):

```ts
// Domain: metadata for one Redis key shown in the browser.
// No `value` — the key browser never displays values (a value inspector is deferred).
export interface KeyMeta {
  key: string
  type: string // Redis TYPE: string | hash | set | zset | list | stream | none | unknown
  ttl?: number // seconds; undefined = no expiry
  size: number // bytes (MEMORY USAGE); 0 if unavailable
}
```

- [ ] **Step 2: Write the failing test**

`lib/application/scan-state.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { initialState, applyScanResult, toMatchGlob } from "@/lib/application/scan-state"
import type { KeyMeta } from "@/lib/domain/cache-entry"

const a: KeyMeta = { key: "a", type: "string", ttl: 10, size: 100 }
const b: KeyMeta = { key: "b", type: "hash", size: 50 }

describe("scan-state", () => {
  it("initialState is unscanned and empty", () => {
    expect(initialState).toEqual({ entries: [], nextCursor: 0, total: null, scanned: false })
  })

  it("reset=true replaces entries and adopts total", () => {
    const s = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    expect(s).toEqual({ entries: [a], nextCursor: 5, total: 42, scanned: true, error: undefined })
  })

  it("reset=false appends and keeps prior total", () => {
    const first = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    const second = applyScanResult(first, { entries: [b], nextCursor: 0, total: 0 }, false)
    expect(second.entries).toEqual([a, b])
    expect(second.total).toBe(42)
    expect(second.nextCursor).toBe(0)
  })

  it("error result sets error + scanned and preserves entries", () => {
    const first = applyScanResult(initialState, { entries: [a], nextCursor: 5, total: 42 }, true)
    const errored = applyScanResult(first, { entries: [], nextCursor: 0, total: 0, error: "boom" }, false)
    expect(errored.error).toBe("boom")
    expect(errored.scanned).toBe(true)
    expect(errored.entries).toEqual([a])
  })

  it("toMatchGlob wraps non-empty terms and trims", () => {
    expect(toMatchGlob("")).toBe("*")
    expect(toMatchGlob("   ")).toBe("*")
    expect(toMatchGlob(" foo ")).toBe("*foo*")
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/application/scan-state.test.ts`
Expected: FAIL — cannot resolve `@/lib/application/scan-state`.

- [ ] **Step 4: Write the implementation**

`lib/application/scan-state.ts`:

```ts
// Pure, framework-free scan-state transitions for the cache browser.
// Kept out of the React component so the append/replace + total-sticky logic is unit-testable.
import type { KeyMeta } from "@/lib/domain/cache-entry"

export interface ScanResult {
  entries: KeyMeta[]
  nextCursor: number
  total: number
  error?: string
}

export interface BrowserState {
  entries: KeyMeta[]
  nextCursor: number
  total: number | null // null until the first successful page-1 scan
  scanned: boolean
  error?: string
}

export const initialState: BrowserState = {
  entries: [],
  nextCursor: 0,
  total: null,
  scanned: false,
}

// reset=true  → page 1: replace entries, adopt result.total.
// reset=false → append (Load more): keep entries + prior total.
export function applyScanResult(state: BrowserState, result: ScanResult, reset: boolean): BrowserState {
  if (result.error) {
    return { ...state, scanned: true, error: result.error }
  }
  return {
    entries: reset ? result.entries : [...state.entries, ...result.entries],
    nextCursor: result.nextCursor,
    total: reset ? result.total : state.total,
    scanned: true,
    error: undefined,
  }
}

// Search term → Redis glob. Empty → "*" (all keys). Wraps in * for substring match.
// NOTE: this is a Redis glob, not a regex; * ? [ in the term are glob metacharacters.
export function toMatchGlob(term: string): string {
  const t = term.trim()
  return t === "" ? "*" : `*${t}*`
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/application/scan-state.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/redis-client-frontend/lib/domain/cache-entry.ts \
        apps-microservices/redis-client-frontend/lib/application/scan-state.ts \
        apps-microservices/redis-client-frontend/lib/application/scan-state.test.ts
git commit -m "feat(redis-client-frontend): KeyMeta + pure scan-state logic"
```

---

### Task 2: Repository SCAN / metadata / DBSIZE

**Goal:** Add `scanKeys` (single SCAN step with MATCH), `getKeyMeta` (TYPE+TTL+MEMORY USAGE, **no GET**), and `dbSize`; remove the now-dead whole-keyspace + value methods.

**Files:**
- Modify: `apps-microservices/redis-client-frontend/lib/infrastructure/redis-cache-repository.ts`
- Test: `apps-microservices/redis-client-frontend/lib/infrastructure/redis-cache-repository.test.ts`

**Acceptance Criteria:**
- [ ] `scanKeys(cursor, match, count=100)` → `{ keys, nextCursor }`; calls `client.scan(cursor, { MATCH: match || "*", COUNT: count })`.
- [ ] `getKeyMeta(key)` → `KeyMeta` composed from `type`+`ttl`+`memoryUsage`; **never calls `client.get`**; `ttl<=0` → `undefined`; `memoryUsage` null → `size 0`; per-command failures degrade (never throw).
- [ ] `dbSize()` → `client.dbSize()`.
- [ ] `getAllKeys`, `getEntry`, `getSize`, `getTTL` removed; `deleteEntry`, `clearAll`, the singleton client unchanged.

**Verify:** `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/infrastructure/redis-cache-repository.test.ts` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

`lib/infrastructure/redis-cache-repository.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest"

const fake = {
  isOpen: true,
  connect: vi.fn().mockResolvedValue(undefined),
  on: vi.fn(),
  scan: vi.fn(),
  type: vi.fn(),
  ttl: vi.fn(),
  memoryUsage: vi.fn(),
  get: vi.fn(),
  dbSize: vi.fn(),
}

vi.mock("redis", () => ({ createClient: () => fake }))

// Static import — vitest hoists vi.mock above imports, so this receives the mock.
// (Do NOT use top-level `await import`: it triggers TS1378 under tsconfig target ES6,
// and `next build` runs with ignoreBuildErrors:false over **/*.ts.)
import { RedisCacheRepository } from "@/lib/infrastructure/redis-cache-repository"

const repo = new RedisCacheRepository()

beforeEach(() => {
  process.env.REDIS_HOST = "h"
  process.env.REDIS_PORT = "1"
  process.env.REDIS_SECRET = "s"
  vi.clearAllMocks()
  fake.isOpen = true
})

describe("RedisCacheRepository", () => {
  it("scanKeys returns {keys,nextCursor} and passes MATCH/COUNT", async () => {
    fake.scan.mockResolvedValue({ cursor: 12, keys: ["a", "b"] })
    const r = await repo.scanKeys(0, "foo*", 50)
    expect(r).toEqual({ keys: ["a", "b"], nextCursor: 12 })
    expect(fake.scan).toHaveBeenCalledWith(0, { MATCH: "foo*", COUNT: 50 })
  })

  it("scanKeys defaults empty match to * and COUNT 100", async () => {
    fake.scan.mockResolvedValue({ cursor: 0, keys: [] })
    await repo.scanKeys(0, "")
    expect(fake.scan).toHaveBeenCalledWith(0, { MATCH: "*", COUNT: 100 })
  })

  it("getKeyMeta composes type/ttl/size without GET", async () => {
    fake.type.mockResolvedValue("hash")
    fake.ttl.mockResolvedValue(300)
    fake.memoryUsage.mockResolvedValue(2048)
    const m = await repo.getKeyMeta("k")
    expect(m).toEqual({ key: "k", type: "hash", ttl: 300, size: 2048 })
    expect(fake.get).not.toHaveBeenCalled()
  })

  it("getKeyMeta maps ttl<=0 to undefined and null memory to 0", async () => {
    fake.type.mockResolvedValue("string")
    fake.ttl.mockResolvedValue(-1)
    fake.memoryUsage.mockResolvedValue(null)
    const m = await repo.getKeyMeta("k")
    expect(m.ttl).toBeUndefined()
    expect(m.size).toBe(0)
  })

  it("getKeyMeta degrades on per-command failure", async () => {
    fake.type.mockRejectedValue(new Error("x"))
    fake.ttl.mockRejectedValue(new Error("x"))
    fake.memoryUsage.mockRejectedValue(new Error("x"))
    const m = await repo.getKeyMeta("k")
    expect(m).toEqual({ key: "k", type: "unknown", ttl: undefined, size: 0 })
  })

  it("dbSize returns the count", async () => {
    fake.dbSize.mockResolvedValue(42)
    expect(await repo.dbSize()).toBe(42)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/infrastructure/redis-cache-repository.test.ts`
Expected: FAIL — `repo.scanKeys is not a function`.

- [ ] **Step 3: Edit the repository**

In `lib/infrastructure/redis-cache-repository.ts`, add the `KeyMeta` import at the top (after the `redis` import):

```ts
import { createClient, type RedisClientType } from "redis"
import type { KeyMeta } from "@/lib/domain/cache-entry"
```

Replace the four read methods (`getAllKeys`, `getEntry`, `getSize`, `getTTL`) — i.e. everything from `// C2: use SCAN ...` down through the end of `getTTL` — with these three. Keep `deleteEntry` and `clearAll` exactly as they are:

```ts
  // Single SCAN step (page). cursor 0 starts iteration; returned nextCursor 0 = complete.
  async scanKeys(cursor: number, match: string, count = 100): Promise<{ keys: string[]; nextCursor: number }> {
    const client = await this.getClient()
    const result = await client.scan(cursor, { MATCH: match || "*", COUNT: count })
    return { keys: result.keys, nextCursor: result.cursor }
  }

  // Per-key metadata WITHOUT reading the value (no GET). Each command degrades independently.
  async getKeyMeta(key: string): Promise<KeyMeta> {
    const client = await this.getClient()
    const [type, ttl, size] = await Promise.all([
      client.type(key).catch(() => "unknown"),
      client.ttl(key).catch(() => -1),
      client.memoryUsage(key).catch(() => 0),
    ])
    return {
      key,
      type: type || "unknown",
      ttl: ttl && ttl > 0 ? ttl : undefined,
      size: size || 0,
    }
  }

  async dbSize(): Promise<number> {
    const client = await this.getClient()
    return client.dbSize()
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run lib/infrastructure/redis-cache-repository.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/redis-client-frontend/lib/infrastructure/redis-cache-repository.ts \
        apps-microservices/redis-client-frontend/lib/infrastructure/redis-cache-repository.test.ts
git commit -m "feat(redis-client-frontend): SCAN-page/getKeyMeta/dbSize repo methods"
```

---

### Task 3: `listCacheKeys` server action + cleanup

**Goal:** Add the `listCacheKeys` server action (paginated, `dbSize` only on page 1, input-validated) reusing the `ScanResult` shape; remove the dead `refreshCacheData` action, the `getCachedData` use case, and the now-pointless `revalidatePath` calls.

**Files:**
- Modify: `apps-microservices/redis-client-frontend/app/actions/cache-actions.ts`
- Delete: `apps-microservices/redis-client-frontend/lib/application/get-cached-data.ts`
- Test: `apps-microservices/redis-client-frontend/app/actions/cache-actions.test.ts`

**Acceptance Criteria:**
- [ ] `listCacheKeys({cursor, match})` → `ScanResult`; calls `scanKeys` then `getKeyMeta` per key; `dbSize` **only** when `cursor === 0` (`total: 0` otherwise).
- [ ] Non-finite / negative `cursor` coerced to `0`; `match` longer than 512 chars coerced to `"*"`; `match` passed through to `scanKeys`.
- [ ] Error path returns `{ entries: [], nextCursor: 0, total: 0, error }`.
- [ ] `invalidateCacheEntry` + `clearAllCache` kept (message contract unchanged); `revalidatePath` import + calls removed; `refreshCacheData` removed; `get-cached-data.ts` deleted.

**Verify:** `cd apps-microservices/redis-client-frontend && pnpm exec vitest run app/actions/cache-actions.test.ts` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

`app/actions/cache-actions.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from "vitest"

vi.mock("@/lib/infrastructure/redis-cache-repository", () => ({
  cacheRepository: {
    scanKeys: vi.fn(),
    getKeyMeta: vi.fn(),
    dbSize: vi.fn(),
    deleteEntry: vi.fn(),
    clearAll: vi.fn(),
  },
}))

// Static imports — vitest hoists vi.mock above imports (avoids TS1378 under target ES6).
import { listCacheKeys, invalidateCacheEntry } from "@/app/actions/cache-actions"
import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"

beforeEach(() => vi.clearAllMocks())

describe("listCacheKeys", () => {
  it("page 1 fetches meta + dbSize", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: ["a"], nextCursor: 5 })
    vi.mocked(cacheRepository.getKeyMeta).mockResolvedValue({ key: "a", type: "string", size: 10 })
    vi.mocked(cacheRepository.dbSize).mockResolvedValue(10)
    const r = await listCacheKeys({ cursor: 0, match: "x*" })
    expect(r).toEqual({ entries: [{ key: "a", type: "string", size: 10 }], nextCursor: 5, total: 10 })
    expect(cacheRepository.scanKeys).toHaveBeenCalledWith(0, "x*")
    expect(cacheRepository.dbSize).toHaveBeenCalledOnce()
  })

  it("later pages skip dbSize (total 0)", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: [], nextCursor: 0 })
    const r = await listCacheKeys({ cursor: 5, match: "" })
    expect(r.total).toBe(0)
    expect(cacheRepository.dbSize).not.toHaveBeenCalled()
  })

  it("coerces a negative/NaN cursor to 0", async () => {
    vi.mocked(cacheRepository.scanKeys).mockResolvedValue({ keys: [], nextCursor: 0 })
    vi.mocked(cacheRepository.dbSize).mockResolvedValue(0)
    await listCacheKeys({ cursor: -3 })
    expect(cacheRepository.scanKeys).toHaveBeenCalledWith(0, "*")
    expect(cacheRepository.dbSize).toHaveBeenCalledOnce()
  })

  it("returns error shape when the repo throws", async () => {
    vi.mocked(cacheRepository.scanKeys).mockRejectedValue(new Error("down"))
    const r = await listCacheKeys({ cursor: 0 })
    expect(r).toEqual({ entries: [], nextCursor: 0, total: 0, error: "Failed to list cache keys" })
  })
})

describe("invalidateCacheEntry", () => {
  it("rejects an invalid key without touching Redis", async () => {
    const r = await invalidateCacheEntry("")
    expect(r.success).toBe(false)
    expect(cacheRepository.deleteEntry).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run app/actions/cache-actions.test.ts`
Expected: FAIL — `listCacheKeys` is not exported.

- [ ] **Step 3: Rewrite the actions file**

`app/actions/cache-actions.ts` (full file):

```ts
// Server actions for cache operations
"use server"

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import type { ScanResult } from "@/lib/application/scan-state"

// S1: validate Redis key format before operations
function isValidKey(key: string): boolean {
  return typeof key === "string" && key.length > 0 && key.length <= 512
}

// Paginated key browse. dbSize (Total Keys) is fetched only on the first page (cursor 0).
export async function listCacheKeys(
  { cursor = 0, match = "" }: { cursor?: number; match?: string } = {},
): Promise<ScanResult> {
  const safeCursor = Number.isFinite(cursor) && cursor > 0 ? Math.floor(cursor) : 0
  const safeMatch = typeof match === "string" && match.length <= 512 ? match : "*"
  try {
    const { keys, nextCursor } = await cacheRepository.scanKeys(safeCursor, safeMatch)
    const entries = await Promise.all(keys.map((k) => cacheRepository.getKeyMeta(k)))
    const total = safeCursor === 0 ? await cacheRepository.dbSize() : 0
    return { entries, nextCursor, total }
  } catch (error) {
    console.error("[redis-client] Error listing keys:", error)
    return { entries: [], nextCursor: 0, total: 0, error: "Failed to list cache keys" }
  }
}

export async function invalidateCacheEntry(key: string) {
  if (!isValidKey(key)) {
    return { success: false, message: "Invalid key format" }
  }

  try {
    const success = await cacheRepository.deleteEntry(key)
    return { success, message: success ? "Entry deleted" : "Failed to delete" }
  } catch (error) {
    console.error("[redis-client] Error invalidating entry:", error)
    return { success: false, message: "Error deleting entry" }
  }
}

export async function clearAllCache() {
  try {
    const success = await cacheRepository.clearAll()
    return { success, message: success ? "Cache cleared" : "Failed to clear" }
  } catch (error) {
    console.error("[redis-client] Error clearing cache:", error)
    return { success: false, message: "Error clearing cache" }
  }
}
```

- [ ] **Step 4: Delete the dead use case**

```bash
git rm apps-microservices/redis-client-frontend/lib/application/get-cached-data.ts
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd apps-microservices/redis-client-frontend && pnpm exec vitest run app/actions/cache-actions.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/redis-client-frontend/app/actions/cache-actions.ts \
        apps-microservices/redis-client-frontend/app/actions/cache-actions.test.ts \
        apps-microservices/redis-client-frontend/lib/application/get-cached-data.ts
git commit -m "feat(redis-client-frontend): listCacheKeys action; drop eager getCachedData"
```

---

### Task 4: Front-end rewrite (browser + table + header + page)

**Goal:** Wire the consent-gated, paginated browser UI: a new `CacheBrowser` client "brain" owns scan state; `page.tsx` renders it with no data; `cache-table` gains a pre-scan gate + Type column + server-side search + Load-more; `cache-header` shows Total Keys/Last Refreshed and gates Refresh behind a confirm (Total Size card removed).

**Files:**
- Create: `apps-microservices/redis-client-frontend/components/cache-browser.tsx`
- Modify (full rewrite): `apps-microservices/redis-client-frontend/components/cache-table.tsx`
- Modify (full rewrite): `apps-microservices/redis-client-frontend/components/cache-header.tsx`
- Modify (full rewrite): `apps-microservices/redis-client-frontend/app/page.tsx`
- Modify: `apps-microservices/redis-client-frontend/CLAUDE.md` (Conventions note)

**Acceptance Criteria:**
- [ ] Opening `/` performs **no** Redis call — the table shows a "Scan keys" gate behind `ConfirmDialog`; only after confirm is `listCacheKeys` invoked.
- [ ] Table columns: **Key / Type / Size / Expires / Actions**; Copy + Delete per row; Delete re-scans page 1 via `onDeleted`.
- [ ] Search box → debounced (300ms) `onSearch` → server-side MATCH scan from cursor 0; "Load more" appears iff `nextCursor !== 0` and appends the next page.
- [ ] Header shows **Total Keys** (`total ?? "—"`) and **Last Refreshed**; **no Total Size card**; Refresh is behind a `ConfirmDialog` (disabled until first scan); Clear All unchanged (own confirm, disabled when `!totalKeys`).
- [ ] `pnpm lint` and `pnpm build` succeed.

**Verify:** `cd apps-microservices/redis-client-frontend && pnpm lint && pnpm build` → no errors (run on the VM if local `node_modules` is absent).

**Steps:**

- [ ] **Step 1: Create the client brain**

`components/cache-browser.tsx`:

```tsx
// Client "brain": owns scan state and orchestrates header + table.
// page.tsx stays a Server Component (session only); all Redis contact is user-initiated here.
"use client"

import { useState, useCallback } from "react"
import { CacheHeader } from "@/components/cache-header"
import { CacheTable } from "@/components/cache-table"
import { listCacheKeys } from "@/app/actions/cache-actions"
import { initialState, applyScanResult, toMatchGlob, type BrowserState } from "@/lib/application/scan-state"
import { useToast } from "@/hooks/use-toast"

interface CacheBrowserProps {
  userEmail?: string
}

export function CacheBrowser({ userEmail }: CacheBrowserProps) {
  const [state, setState] = useState<BrowserState>(initialState)
  const [match, setMatch] = useState("*")
  const [loading, setLoading] = useState(false)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const { toast } = useToast()

  const runScan = useCallback(
    async (cursor: number, glob: string, reset: boolean) => {
      setLoading(true)
      try {
        const result = await listCacheKeys({ cursor, match: glob })
        setState((prev) => applyScanResult(prev, result, reset))
        if (reset) setLastRefreshed(new Date())
        if (result.error) {
          toast({ title: "Error", description: result.error, variant: "destructive" })
        }
      } finally {
        setLoading(false)
      }
    },
    [toast],
  )

  const handleScan = useCallback(() => {
    setMatch("*")
    void runScan(0, "*", true)
  }, [runScan])

  const handleRefresh = useCallback(() => {
    void runScan(0, match, true)
  }, [runScan, match])

  const handleLoadMore = useCallback(() => {
    void runScan(state.nextCursor, match, false)
  }, [runScan, state.nextCursor, match])

  const handleSearch = useCallback(
    (term: string) => {
      const glob = toMatchGlob(term)
      setMatch(glob)
      void runScan(0, glob, true)
    },
    [runScan],
  )

  const handleChanged = useCallback(() => {
    void runScan(0, match, true)
  }, [runScan, match])

  return (
    <div className="space-y-8">
      <CacheHeader
        totalKeys={state.total}
        lastRefreshed={lastRefreshed}
        loading={loading}
        scanned={state.scanned}
        onRefresh={handleRefresh}
        onCleared={handleChanged}
        userEmail={userEmail}
      />
      <CacheTable
        entries={state.entries}
        nextCursor={state.nextCursor}
        scanned={state.scanned}
        loading={loading}
        onScan={handleScan}
        onLoadMore={handleLoadMore}
        onSearch={handleSearch}
        onDeleted={handleChanged}
      />
    </div>
  )
}
```

- [ ] **Step 2: Rewrite the table**

`components/cache-table.tsx` (full file):

```tsx
// UI Component: paginated, consent-gated key browser.
"use client"

import { useState, useEffect, useRef } from "react"
import type { KeyMeta } from "@/lib/domain/cache-entry"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Trash2, Copy, Search } from "lucide-react"
import { invalidateCacheEntry } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"
import { ConfirmDialog } from "./confirm-dialog"
import { formatBytes } from "@/lib/utils"

interface CacheTableProps {
  entries: KeyMeta[]
  nextCursor: number
  scanned: boolean
  loading: boolean
  onScan: () => void
  onLoadMore: () => void
  onSearch: (term: string) => void
  onDeleted: () => void
}

export function CacheTable({
  entries,
  nextCursor,
  scanned,
  loading,
  onScan,
  onLoadMore,
  onSearch,
  onDeleted,
}: CacheTableProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  const { toast } = useToast()
  const firstRender = useRef(true)

  // Debounce search → server-side MATCH. Skip the mount pass so opening the page never scans.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    const id = setTimeout(() => onSearch(searchTerm), 300)
    return () => clearTimeout(id)
  }, [searchTerm, onSearch])

  const handleDelete = async (key: string) => {
    setDeletingKey(key)
    try {
      const result = await invalidateCacheEntry(key)
      if (result.success) {
        toast({ title: "Success", description: `Cache entry "${key}" deleted` })
        onDeleted()
      } else {
        toast({ title: "Error", description: result.message, variant: "destructive" })
      }
    } finally {
      setDeletingKey(null)
    }
  }

  const handleCopy = (key: string) => {
    navigator.clipboard.writeText(key)
    toast({ title: "Copied", description: "Key copied to clipboard" })
  }

  const formatTTL = (ttl?: number) => {
    if (!ttl) return "No expiry"
    if (ttl < 60) return `${ttl}s`
    if (ttl < 3600) return `${Math.floor(ttl / 60)}m`
    if (ttl < 86400) return `${Math.floor(ttl / 3600)}h`
    return `${Math.floor(ttl / 86400)}d`
  }

  // Pre-scan gate — page open makes zero Redis contact until the user consents.
  if (!scanned) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
        <div className="text-muted-foreground">
          <p className="text-lg font-medium">Cache not scanned</p>
          <p className="text-sm max-w-md">
            Scanning queries the shared production Redis (paginated SCAN plus per-key TTL/type/size — no
            key values are read), which may still add latency for other services on the same instance.
          </p>
        </div>
        <ConfirmDialog
          title="Scan the shared Redis?"
          description="This queries the shared production Redis (paginated SCAN + per-key TTL/type/size). It may add latency for other services using the same instance. Continue?"
          onConfirm={onScan}
          isLoading={loading}
        >
          <Button>
            <Search className="w-4 h-4 mr-2" />
            Scan keys
          </Button>
        </ConfirmDialog>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Filter keys (server-side glob, matches *term*)..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1"
        />
        <span className="text-sm text-muted-foreground whitespace-nowrap">{entries.length} loaded</span>
      </div>

      {entries.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">No keys match this filter</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Key</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.key}>
                  <TableCell className="font-mono text-sm max-w-xs truncate">{entry.key}</TableCell>
                  <TableCell className="text-sm">{entry.type}</TableCell>
                  <TableCell>{formatBytes(entry.size)}</TableCell>
                  <TableCell>{formatTTL(entry.ttl)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => handleCopy(entry.key)} title="Copy key">
                        <Copy className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(entry.key)}
                        disabled={deletingKey === entry.key}
                        className="text-destructive hover:text-destructive"
                        title="Delete entry"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {nextCursor !== 0 && (
        <div className="flex justify-center">
          <Button variant="outline" onClick={onLoadMore} disabled={loading}>
            {loading ? "Loading..." : "Load more"}
          </Button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Rewrite the header**

`components/cache-header.tsx` (full file):

```tsx
// UI Component: dashboard header with stats and actions.
"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { RefreshCw, Trash2 } from "lucide-react"
import { clearAllCache } from "@/app/actions/cache-actions"
import { useToast } from "@/hooks/use-toast"
import { ConfirmDialog } from "./confirm-dialog"

interface CacheHeaderProps {
  totalKeys: number | null
  lastRefreshed: Date | null
  loading: boolean
  scanned: boolean
  onRefresh: () => void
  onCleared: () => void
  userEmail?: string
}

export function CacheHeader({
  totalKeys,
  lastRefreshed,
  loading,
  scanned,
  onRefresh,
  onCleared,
  userEmail,
}: CacheHeaderProps) {
  const [isClearing, setIsClearing] = useState(false)
  const { toast } = useToast()

  const handleClearAll = async () => {
    setIsClearing(true)
    try {
      const result = await clearAllCache()
      if (result.success) {
        toast({ title: "Success", description: "Cache cleared successfully" })
        onCleared()
      } else {
        toast({ title: "Error", description: result.message, variant: "destructive" })
      }
    } finally {
      setIsClearing(false)
    }
  }

  const formatTime = (date: Date) =>
    new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date)

  return (
    <div className="space-y-4">
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

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Total Keys</p>
          <p className="text-2xl font-bold">{totalKeys ?? "—"}</p>
        </div>
        <div className="bg-card border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Last Refreshed</p>
          <p className="text-sm font-mono">{lastRefreshed ? formatTime(lastRefreshed) : "—"}</p>
        </div>
      </div>

      <div className="flex gap-2">
        {/* Refresh re-scans page 1; behind a consent dialog because it re-queries the shared Redis. */}
        <ConfirmDialog
          title="Scan the shared Redis?"
          description="Refresh re-queries the shared production Redis (paginated SCAN + per-key metadata). This may add latency for other services on the same instance. Continue?"
          onConfirm={onRefresh}
          isLoading={loading}
        >
          <Button variant="outline" disabled={!scanned || loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            {loading ? "Scanning..." : "Refresh"}
          </Button>
        </ConfirmDialog>

        <ConfirmDialog
          title="Clear All Cache?"
          description="This will delete all entries in Redis. This action cannot be undone."
          onConfirm={handleClearAll}
          isLoading={isClearing}
        >
          <Button variant="destructive" disabled={!totalKeys || isClearing}>
            <Trash2 className="w-4 h-4 mr-2" />
            Clear All
          </Button>
        </ConfirmDialog>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rewrite the page**

`app/page.tsx` (full file):

```tsx
import { CacheBrowser } from "@/components/cache-browser"
import { cookies } from "next/headers"
import { readSession, SESSION_COOKIE } from "@hellopro/auth"

export default async function Home() {
  const cookieStore = await cookies()
  const session = await readSession(cookieStore.get(SESSION_COOKIE)?.value)

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <CacheBrowser userEmail={session?.email} />
      </div>
    </main>
  )
}
```

- [ ] **Step 5: Update CLAUDE.md conventions**

In `apps-microservices/redis-client-frontend/CLAUDE.md`, under `## Conventions`, replace the bullet:

```
- Redis uses `SCAN` (not `KEYS *`) for non-blocking key enumeration
```

with:

```
- Redis uses paginated `SCAN` (not `KEYS *`); the browser is **consent-gated** — opening `/` makes zero Redis contact until the operator confirms a scan. Each page reads `TTL`/`TYPE`/`MEMORY USAGE` per key, never `GET` (values are not displayed). Total Keys = `DBSIZE`; there is no aggregate size (would require a full scan). If the shared Redis grows large enough that even paginated scans matter, point this UI at a read replica (`REDIS_HOST`).
```

- [ ] **Step 6: Verify build + lint**

Run: `cd apps-microservices/redis-client-frontend && pnpm lint && pnpm build`
Expected: lint clean; build succeeds (standalone output). If local `node_modules` is absent, run on the VM.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/redis-client-frontend/components/cache-browser.tsx \
        apps-microservices/redis-client-frontend/components/cache-table.tsx \
        apps-microservices/redis-client-frontend/components/cache-header.tsx \
        apps-microservices/redis-client-frontend/app/page.tsx \
        apps-microservices/redis-client-frontend/CLAUDE.md
git commit -m "feat(redis-client-frontend): consent-gated paginated key browser UI"
```

---

## Self-Review

**Spec coverage:**
- D1 paginated SCAN, no per-key GET, server MATCH → Tasks 2 (`scanKeys`/`getKeyMeta`), 3 (`listCacheKeys`), 4 (search).
- D2 note-only fleet-safety → Task 4 Step 5 CLAUDE.md replica note. (No infra built — correct.)
- D3 consent gate → Task 4 (table pre-scan gate + header Refresh confirm), asserted in AC.
- D4 Total Keys=DBSIZE, drop Total Size → Tasks 2 (`dbSize`), 4 (header two-card grid).
- D5 all key types + Type column → Task 2 (`getKeyMeta` type), Task 4 (Type column).
- §5 error handling → Task 2 (per-command degrade), Task 3 (error shape), Task 1 (error state).
- §6 testing → Tasks 1–3 vitest; §4 client asserted via build/lint (no jsdom installed → pure logic tested in Task 1 instead of rendering).
- §8 risks → SCAN cursor semantics confirmed against installed v4 (plan header); MATCH-glob documented (placeholder + toMatchGlob comment); COUNT-hint honored (`nextCursor !== 0`); state-lift isolated to `CacheBrowser` (session untouched in `page.tsx`); VM build = Task 4 verify.

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `KeyMeta` (Task 1) used by repo (2), action (3), table (4). `ScanResult` (Task 1) is the action return type (3) and `applyScanResult` input (1). `BrowserState` (Task 1) is `CacheBrowser` state (4). Method names `scanKeys`/`getKeyMeta`/`dbSize` consistent across Tasks 2→3. Prop names on `CacheHeader`/`CacheTable` match `CacheBrowser`'s call sites.

**Out of scope (unchanged):** value inspector; read-replica infra; `deleteEntry`/`clearAll`/singleton client; auth/session/middleware.
