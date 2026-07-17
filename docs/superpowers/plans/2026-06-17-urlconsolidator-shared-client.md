# UrlConsolidator Shared Redis Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `UrlConsolidator` off its own idle-reaped Redis client onto the heartbeat-warmed injected shared client (mirroring the StatsManager fix), so an update-mode crawl can no longer make a wrong `isInDataset` decision after the server reaps an idle socket.

**Architecture:** `UrlConsolidator`'s constructor accepts `RedisClientType | string`. A string keeps the legacy create-and-own behavior (tests/back-compat); an injected `RedisClientType` sets `ownsClient=false`, making `connect()`/`disconnect()` no-ops so the owner (main.ts) manages the shared socket lifecycle. `cleanup()`/`fullCleanup()` bodies are unchanged — they still `del` their namespaced keys and call `disconnect()`, which now no-ops on the injected path. The production callsite (`main.ts:688`, update-mode only) passes `sharedRedis`. This removes the last per-crawl separate Redis connection.

**Tech Stack:** Node.js 22 / TypeScript, Crawlee 3, `redis` (node-redis) `^4.6.10`. Tests: `node:test` via `npm test` (`node --import tsx --test src/**/*.test.ts`). Build: `tsc` via `npm run build`.

**Spec:** `docs/superpowers/specs/2026-06-17-urlconsolidator-shared-client-design.md`

**Working dir for all commands:** `apps-microservices/crawler-service/crawler`

**Commits:** The coordinator (main thread) runs final verification and ALL commits — implementers do NOT commit (Windows cp1252 + concurrent-session `COMMIT_EDITMSG` race control). Bilingual EN+FR via `.git/<NAME>_MSG.txt` + `git -c commit.encoding=utf-8 commit -F`, explicit `git add` (never `-A`).

**graphify:** consumer clone — do NOT stage `graphify-out/*`.

---

### Task 1: UrlConsolidator accepts an injected shared client

**Goal:** `UrlConsolidator` accepts `RedisClientType | string`; injected path makes `connect`/`disconnect` no-ops via an `ownsClient` guard; full test coverage in a new test file.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/UrlConsolidator.ts` (field + constructor + connect/disconnect; cleanup/fullCleanup unchanged)
- Create: `apps-microservices/crawler-service/crawler/src/class/UrlConsolidator.test.ts`

**Acceptance Criteria:**
- [ ] Constructor accepts `RedisClientType | string`; string → `ownsClient=true` + create client + attach `'error'` listener; injected → `ownsClient=false`, no listener.
- [ ] `connect()`/`disconnect()` return early when `!ownsClient` (the guard is mandatory — without it `cleanup()` would close the shared client).
- [ ] `cleanup()`/`fullCleanup()`/`isInDataset`/`consolidate`/`ensureTtl`/`loadRequestQueueUrls` bodies unchanged.
- [ ] New tests pass: injected no-op lifecycle; `cleanup` dels rq+ru and KEEPS dataset, no disconnect; `fullCleanup` dels all three, no disconnect; `isInDataset`→`sIsMember` delegation; error-path (rejecting `sIsMember` → `isInDataset` returns `false`); legacy construct-without-connect.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npm test` → tsc 0 errors; all `*.test.ts` pass (baseline 157 + the new UrlConsolidator suite).

**Steps:**

- [ ] **Step 1: Create the failing test** — write `src/class/UrlConsolidator.test.ts` with EXACTLY:

```typescript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RedisClientType } from 'redis';
import { UrlConsolidator } from './UrlConsolidator.js';

interface FakeRedisCalls {
    connect: number;
    disconnect: number;
    del: string[];
    sIsMember: Array<[string, string]>;
}

function makeFakeClient(
    overrides: Record<string, unknown> = {},
): { client: RedisClientType; calls: FakeRedisCalls } {
    const calls: FakeRedisCalls = { connect: 0, disconnect: 0, del: [], sIsMember: [] };
    const base = {
        isOpen: true,
        on: (_event: string, _fn: (...a: unknown[]) => void) => {},
        connect: async () => { calls.connect++; },
        disconnect: async () => { calls.disconnect++; },
        del: async (key: string) => { calls.del.push(key); return 1; },
        sIsMember: async (key: string, member: string) => {
            calls.sIsMember.push([key, member]);
            return true;
        },
        sAdd: async () => 1,
        sScan: async () => ({ cursor: 0, members: [] as string[] }),
        expire: async () => true,
    };
    const client = { ...base, ...overrides } as unknown as RedisClientType;
    return { client, calls };
}

test('injected client: connect/disconnect are no-ops (owner manages lifecycle)', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-1', 'prev-1', 'example.com');
    await uc.connect();
    await uc.disconnect();
    assert.equal(calls.connect, 0, 'connect() must not connect an injected client');
    assert.equal(calls.disconnect, 0, 'disconnect() must not disconnect an injected client');
});

test('injected client: cleanup dels rq+ru, KEEPS datasetKey, does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-2', 'prev-2', 'example.com');
    await uc.cleanup();
    assert.equal(calls.del.length, 2, 'cleanup() dels exactly two keys');
    assert.ok(calls.del.includes('update_rq:job-2'), 'cleanup() dels the request-queue key');
    assert.ok(calls.del.includes('update_ru:job-2'), 'cleanup() dels the request-url key');
    assert.ok(!calls.del.includes('update_dataset:job-2'), 'cleanup() must KEEP the dataset key (UpdateChecker needs it)');
    assert.equal(calls.disconnect, 0, 'cleanup() must not disconnect the shared client');
});

test('injected client: fullCleanup dels all three keys, does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-3', 'prev-3', 'example.com');
    await uc.fullCleanup();
    assert.equal(calls.del.length, 3, 'fullCleanup() dels three keys');
    assert.ok(calls.del.includes('update_dataset:job-3'), 'fullCleanup() dels the dataset key');
    assert.ok(calls.del.includes('update_rq:job-3'), 'fullCleanup() dels the request-queue key');
    assert.ok(calls.del.includes('update_ru:job-3'), 'fullCleanup() dels the request-url key');
    assert.equal(calls.disconnect, 0, 'fullCleanup() must not disconnect the shared client');
});

test('injected client: isInDataset delegates to sIsMember and returns its boolean', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-4', 'prev-4', 'example.com');
    const r = await uc.isInDataset('https://example.com/a');
    assert.equal(r, true);
    assert.deepEqual(calls.sIsMember, [['update_dataset:job-4', 'https://example.com/a']]);
});

test('error path: a rejecting sIsMember is swallowed and isInDataset returns false', async () => {
    const { client } = makeFakeClient({
        sIsMember: async () => {
            throw new Error('SocketClosedUnexpectedlyError: Socket closed unexpectedly');
        },
    });
    const uc = new UrlConsolidator(client, 'job-5', 'prev-5', 'example.com');
    const r = await uc.isInDataset('https://example.com/b');
    assert.equal(r, false, 'isInDataset must return false (not throw) when the socket is dead');
});

test('legacy URL path: constructs without throwing and without connecting', () => {
    // createClient is lazy — the constructor must not open a socket.
    const uc = new UrlConsolidator('redis://localhost:6379', 'job-6', 'prev-6', 'example.com');
    assert.equal(typeof uc.isInDataset, 'function');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc FAILS — `new UrlConsolidator(client, …)` rejects a `RedisClientType` (current first param is `redisUrl: string`).

- [ ] **Step 3a: Add the `ownsClient` field** — in `src/class/UrlConsolidator.ts`, replace:

```typescript
    private ttl: number;
    private ttlSet: boolean = false;

    private previousCrawlId: string;
```

with:

```typescript
    private ttl: number;
    private ttlSet: boolean = false;
    private ownsClient: boolean;

    private previousCrawlId: string;
```

- [ ] **Step 3b: Replace the constructor** — replace the entire constructor:

```typescript
    constructor(
        redisUrl: string,
        crawlId: string,
        previousCrawlId: string,
        domain: string,
        ttlSeconds: number = 7 * 24 * 3600
    ) {
        this.redis = createClient({ url: redisUrl });
        this.redis.on('error', (err: Error) => console.error('Redis UrlConsolidator Error:', err));
        this.datasetKey = `update_dataset:${crawlId}`;
        this.requestQueueKey = `update_rq:${crawlId}`;
        this.requestUrlKey = `update_ru:${crawlId}`;
        this.previousCrawlId = previousCrawlId;
        this.domain = domain;
        this.ttl = ttlSeconds;
    }
```

with:

```typescript
    constructor(
        clientOrUrl: RedisClientType | string,
        crawlId: string,
        previousCrawlId: string,
        domain: string,
        ttlSeconds: number = 7 * 24 * 3600
    ) {
        this.datasetKey = `update_dataset:${crawlId}`;
        this.requestQueueKey = `update_rq:${crawlId}`;
        this.requestUrlKey = `update_ru:${crawlId}`;
        this.previousCrawlId = previousCrawlId;
        this.domain = domain;
        this.ttl = ttlSeconds;

        if (typeof clientOrUrl === 'string') {
            // Backward-compatible URL form — UrlConsolidator creates + owns the client.
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err: Error) => console.error('Redis UrlConsolidator Error:', err));
        } else {
            // Injected shared client — owner manages connect/disconnect + the 'error' listener.
            this.redis = clientOrUrl;
            this.ownsClient = false;
        }
    }
```

- [ ] **Step 3c: Guard connect/disconnect** — replace:

```typescript
    async connect(): Promise<void> {
        if (!this.redis.isOpen) {
            await this.redis.connect();
        }
    }

    async disconnect(): Promise<void> {
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }
```

with:

```typescript
    async connect(): Promise<void> {
        if (!this.ownsClient) return;   // shared client connected by owner
        if (!this.redis.isOpen) {
            await this.redis.connect();
        }
    }

    async disconnect(): Promise<void> {
        if (!this.ownsClient) return;   // shared client closed by owner
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }
```

Do NOT change `cleanup()`, `fullCleanup()`, `isInDataset`, `consolidate`, `ensureTtl`, or `loadRequestQueueUrls` — they already call `this.disconnect()` (now a no-op on the injected path) and `del` their own namespaced keys. `RedisClientType` is already imported on line 1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service/crawler && npm run build && npm test`
Expected: tsc 0 errors; all `*.test.ts` pass — the 6 new UrlConsolidator assertions + the existing 157.

- [ ] **Step 5: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/crawler/src/class/UrlConsolidator.ts \
        apps-microservices/crawler-service/crawler/src/class/UrlConsolidator.test.ts
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

### Task 2: Wire the shared client into UrlConsolidator at the production callsite

**Goal:** `main.ts` (update-mode branch) passes `sharedRedis` to `UrlConsolidator`; remove the now-dead local `redisUrl` if `tsc` flags it unused.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (line 688; possibly remove line 687)

**Acceptance Criteria:**
- [ ] `main.ts:688` constructs `new UrlConsolidator(sharedRedis, id, previousCrawlId, domain)`.
- [ ] If `tsc` reports the local `const redisUrl` (line 687) as unused, it is removed; otherwise left as-is.
- [ ] `tsc` is clean. No other line changes.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build` → tsc 0 errors. (tdd-gate stem `main` satisfied by existing `src/tests/test_main.ts`.)

**Steps:**

- [ ] **Step 1: Change the constructor call** — in `src/main.ts`, replace:

```typescript
    const consolidator = new UrlConsolidator(redisUrl, id, previousCrawlId, domain);
```

with:

```typescript
    const consolidator = new UrlConsolidator(sharedRedis, id, previousCrawlId, domain);
```

`sharedRedis` is created and connected at `main.ts:371-375`, far above line 688. `await consolidator.connect();` on the next line is now a no-op on the injected path — leave it.

- [ ] **Step 2: Build; remove dead local if flagged**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

- If tsc reports `'redisUrl' is declared but its value is never read` (the local at line 687, `const redisUrl = process.env.REDIS_URL || 'redis://redis:6379';`), DELETE that one line, then rebuild. Keep the surrounding `// --- URL CONSOLIDATION (Epic 1) ---` comments.
- If tsc passes (the local is still referenced elsewhere in the update branch), leave line 687 unchanged.

Expected after handling: tsc 0 errors.

- [ ] **Step 3: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

### Task 3: Update crawler-service CLAUDE.md

**Goal:** Replace the "UrlConsolidator … deferred" caveat (added by the StatsManager work) now that it is fixed.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (the note in "Redis Connection Leak Prevention" → "### Node side", around line 384)

**Acceptance Criteria:**
- [ ] The parenthetical "(Remaining separate client: `UrlConsolidator` still opens its own Redis connection — deferred.)" is replaced with text stating UrlConsolidator now also consumes the injected shared client (update mode) and no separate per-crawl client remains, with a spec link.
- [ ] No other CLAUDE.md content changed.

**Verify:** `grep -n "no separate per-crawl" apps-microservices/crawler-service/CLAUDE.md` → returns the new line; `grep -n "UrlConsolidator still opens its own" apps-microservices/crawler-service/CLAUDE.md` → returns nothing.

**Steps:**

- [ ] **Step 1: Replace the caveat** — in `apps-microservices/crawler-service/CLAUDE.md`, replace:

```markdown
 (Remaining separate client: `UrlConsolidator` still opens its own Redis connection — deferred.)
```

with:

```markdown
 `UrlConsolidator` likewise consumes the injected shared client (update mode, `ownsClient=false`) — no separate per-crawl Redis client remains. See `docs/superpowers/specs/2026-06-17-urlconsolidator-shared-client-design.md`.
```

(The caveat is the trailing sentence of the StatsManager note; match the exact text including the em dash. If the whitespace differs, read the line and replace only that parenthetical.)

- [ ] **Step 2: Verify**

Run: `grep -n "no separate per-crawl" apps-microservices/crawler-service/CLAUDE.md` → one match. `grep -n "UrlConsolidator still opens its own" apps-microservices/crawler-service/CLAUDE.md` → no match.

- [ ] **Step 3: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/CLAUDE.md
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

## Self-Review

**Spec coverage:**
- §5.1 UrlConsolidator injected ctor + `ownsClient` guards → Task 1 ✓
- §5.2 main.ts:688 wiring + dead-`redisUrl` handling → Task 2 ✓
- §5.3 RedisHealthMonitor / context.ts no change → no task (correct) ✓
- §8 tests (injected no-op, cleanup keeps dataset, fullCleanup all-three, isInDataset delegation, error-path, legacy) → Task 1 Step 1 ✓
- §11 UC-T3 CLAUDE.md caveat replacement → Task 3 ✓

**Placeholder scan:** none — every code step shows complete file content or exact old→new strings.

**Type consistency:** ctor signature `(clientOrUrl: RedisClientType | string, crawlId, previousCrawlId, domain, ttlSeconds?)` matches across Task 1 code, Task 1 tests, and Task 2 callsite. Keys `update_dataset` / `update_rq` / `update_ru:{crawlId}` consistent. `ownsClient` private field used consistently. `isInDataset` returns boolean, fail-open `false` on error preserved.
