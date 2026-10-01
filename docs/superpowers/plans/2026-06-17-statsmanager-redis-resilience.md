# StatsManager Redis Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate silent stat loss by migrating `StatsManager` off its own idle-reaped Redis client onto the heartbeat-warmed injected shared client, mirroring `DedupManager`'s `ownsClient` pattern.

**Architecture:** `StatsManager` becomes a client *consumer* (like `DedupManager`/`PushedSet`/`checkedSet`) instead of a client *owner*. Its constructor accepts `RedisClientType | string`: a string keeps the legacy create-and-own behavior (tests/back-compat); an injected `RedisClientType` sets `ownsClient=false`, making `connect()`/`disconnect()` no-ops and leaving the socket lifecycle to the owner. The production callsite (`main.ts:545`) passes `sharedRedis`. Per-crawl Redis connection count drops 2 → 1; the idle reaper (`CONFIG timeout 300`) can no longer close a live StatsManager socket because the shared client is kept warm by the 2 s heartbeat.

**Tech Stack:** Node.js 22 / TypeScript, Crawlee 3, `redis` (node-redis) `^4.6.10`. Tests: `node:test` via `npm test` (`node --import tsx --test src/**/*.test.ts`). Build: `tsc` via `npm run build`.

**Spec:** `docs/superpowers/specs/2026-06-17-statsmanager-redis-resilience-design.md`

**Working dir for all commands:** `apps-microservices/crawler-service/crawler`

**Commits:** The coordinator (main thread) runs the final verification and ALL commits — implementers do NOT commit (Windows cp1252 + concurrent-session `COMMIT_EDITMSG` race control). Commit messages are bilingual EN+FR via a private `.git/<NAME>_MSG.txt` + `git -c commit.encoding=utf-8 commit -F`, staging explicit files (never `-A`). The per-task "Commit" steps below show the intended file set only.

**graphify:** consumer clone — do NOT stage `graphify-out/*`.

---

### Task 1: StatsManager accepts an injected shared client

**Goal:** `StatsManager` accepts `RedisClientType | string`; injected path makes `connect`/`disconnect` no-ops and `cleanup` skip disconnect, with full test coverage.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/StatsManager.ts`
- Test: `apps-microservices/crawler-service/crawler/src/class/StatsManager.test.ts`

**Acceptance Criteria:**
- [ ] Constructor accepts `RedisClientType | string`; string → `ownsClient=true` + create client + attach `'error'` listener; injected → `ownsClient=false`, no listener.
- [ ] `connect()`/`disconnect()` are no-ops when `!ownsClient`.
- [ ] `cleanup()` always `del`s the key; only disconnects when `ownsClient`.
- [ ] `increment`/`getValue`/`checkThreshold`/`saveStateToDisk`/`loadStateFromDisk`/`ensureTtl` behavior is byte-for-byte unchanged.
- [ ] New tests pass: injected no-op lifecycle, cleanup del-not-disconnect, increment→hIncrBy delegation, getValue→hGet, error-path (reject→0) for both increment and getValue, legacy construct-without-connect.
- [ ] Existing method-surface + Ch.A counter-name tests stay green.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npm test` → tsc 0 errors; all `*.test.ts` pass (StatsManager.test.ts new assertions green).

**Steps:**

- [ ] **Step 1: Write the failing tests** — replace the entire contents of `src/class/StatsManager.test.ts` with:

```typescript
// Co-located with StatsManager.ts to satisfy the project's TDD-gate hook.
//
// The original file asserted compile-time class shape only (StatsManager hard-
// coded `createClient`, so a real Redis-backed test needed a DI seam). After the
// 2026-06-17 resilience migration StatsManager accepts an injected RedisClientType
// directly, so the injected path is now unit-testable with a plain fake object —
// no seam required. The legacy URL path's connect/disconnect lifecycle still needs
// a live Redis and is left to staging smoke tests (see spec §8); the injected
// no-op tests below are the active regression guard for the ownsClient branch.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RedisClientType } from 'redis';
import { StatsManager } from './StatsManager.js';

test('StatsManager class is exported with expected method surface', () => {
    assert.equal(typeof StatsManager, 'function', 'StatsManager must be a class constructor');
    const proto = StatsManager.prototype as unknown as Record<string, unknown>;
    const expectedMethods = [
        'connect',
        'disconnect',
        'increment',
        'getValue',
        'checkThreshold',
        'saveStateToDisk',
        'loadStateFromDisk',
        'cleanup',
    ];
    for (const method of expectedMethods) {
        assert.equal(
            typeof proto[method],
            'function',
            `StatsManager must expose ${method}()`,
        );
    }
});

test('Ch.A Epic 1 deperdition counter names — compile-time check', () => {
    const CH_A_E1_COUNTERS: readonly string[] = [
        'filtered_qm',
        'filtered_hash',
        'filtered_ext',
        'filtered_nonfr',
        'filtered_duplicate',
        'dropped_cb',
        'timeout_individual',
        'success_extracted',
    ];
    assert.equal(CH_A_E1_COUNTERS.length, 8);
    assert.ok(CH_A_E1_COUNTERS.every((c) => typeof c === 'string' && c.length > 0));
});

// --- Injected shared-client behavior (2026-06-17 resilience migration) ---

interface FakeRedisCalls {
    connect: number;
    disconnect: number;
    del: string[];
    hIncrBy: Array<[string, string, number]>;
    hGet: Array<[string, string]>;
}

function makeFakeClient(
    overrides: Record<string, unknown> = {},
): { client: RedisClientType; calls: FakeRedisCalls } {
    const calls: FakeRedisCalls = { connect: 0, disconnect: 0, del: [], hIncrBy: [], hGet: [] };
    const base = {
        isOpen: true,
        on: (_event: string, _fn: (...a: unknown[]) => void) => {},
        connect: async () => { calls.connect++; },
        disconnect: async () => { calls.disconnect++; },
        del: async (key: string) => { calls.del.push(key); return 1; },
        hIncrBy: async (key: string, field: string, by: number) => {
            calls.hIncrBy.push([key, field, by]);
            return by;
        },
        hGet: async (key: string, field: string) => {
            calls.hGet.push([key, field]);
            return '7';
        },
        hGetAll: async () => ({}),
        hSet: async () => 1,
        expire: async () => true,
    };
    const client = { ...base, ...overrides } as unknown as RedisClientType;
    return { client, calls };
}

test('injected client: connect/disconnect are no-ops (owner manages lifecycle)', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-1', '.');
    await sm.connect();
    await sm.disconnect();
    assert.equal(calls.connect, 0, 'connect() must not connect an injected client');
    assert.equal(calls.disconnect, 0, 'disconnect() must not disconnect an injected client');
});

test('injected client: cleanup deletes the key but does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-2', '.');
    await sm.cleanup();
    assert.deepEqual(calls.del, ['stats:job-2'], 'cleanup() must del the stats key');
    assert.equal(calls.disconnect, 0, 'cleanup() must not disconnect the shared client');
});

test('injected client: increment delegates to hIncrBy and returns its value', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-3', '.');
    const v = await sm.increment('errors', 2);
    assert.equal(v, 2);
    assert.deepEqual(calls.hIncrBy, [['stats:job-3', 'errors', 2]]);
});

test('injected client: getValue delegates to hGet and parses the result', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-4', '.');
    const v = await sm.getValue('errors');
    assert.equal(v, 7);
    assert.deepEqual(calls.hGet, [['stats:job-4', 'errors']]);
});

test('error path: a rejecting hIncrBy is swallowed and increment returns 0', async () => {
    const { client } = makeFakeClient({
        hIncrBy: async () => {
            throw new Error('SocketClosedUnexpectedlyError: Socket closed unexpectedly');
        },
    });
    const sm = new StatsManager(client, 'job-5', '.');
    const v = await sm.increment('errors', 1);
    assert.equal(v, 0, 'increment must return 0 (not throw) when the socket is dead');
});

test('error path: a rejecting hGet is swallowed and getValue returns 0', async () => {
    const { client } = makeFakeClient({
        hGet: async () => {
            throw new Error('SocketClosedUnexpectedlyError');
        },
    });
    const sm = new StatsManager(client, 'job-6', '.');
    const v = await sm.getValue('errors');
    assert.equal(v, 0, 'getValue must return 0 (not throw) when the socket is dead');
});

test('legacy URL path: constructs without throwing and without connecting', () => {
    // createClient is lazy — the constructor must not open a socket.
    const sm = new StatsManager('redis://localhost:6379', 'job-7', '.');
    assert.equal(typeof sm.increment, 'function');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc FAILS — `new StatsManager(client, …)` rejects a `RedisClientType` (current ctor's first param is `redisUrl: string`).

- [ ] **Step 3: Apply the implementation** — replace the entire contents of `src/class/StatsManager.ts` with:

```typescript
import { createClient, RedisClientType } from 'redis';
import fs from 'fs/promises';
import path from 'path';

export class StatsManager {
    private redis: RedisClientType;
    private key: string;
    private statsFile: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private ownsClient: boolean;

    /**
     * Accepts either a URL (legacy: creates + owns the client) or a pre-built
     * shared RedisClientType (injected: lifecycle managed by the owner).
     *
     * When a shared client is injected, the OWNER owns the 'error' listener and
     * the connect/disconnect lifecycle — StatsManager does NOT register a second
     * listener, and connect()/disconnect() are no-ops. Mirrors DedupManager.
     */
    constructor(
        clientOrUrl: RedisClientType | string,
        crawlId: string,
        storagePath: string,
        ttlSeconds: number = 7 * 24 * 3600,
    ) {
        this.key = `stats:${crawlId}`;
        this.statsFile = path.join(storagePath, 'update_stats.json');
        this.ttl = ttlSeconds;

        if (typeof clientOrUrl === 'string') {
            // Backward-compatible URL form — StatsManager creates + owns the client.
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err) => console.error('Redis Stats Error:', err));
        } else {
            // Injected shared client — StatsManager does NOT connect/disconnect it,
            // and does NOT register a second 'error' listener (owner attached one).
            this.redis = clientOrUrl;
            this.ownsClient = false;
        }
    }

    async connect() {
        if (!this.ownsClient) return;   // shared client connected by owner
        await this.redis.connect();
    }

    async disconnect() {
        if (!this.ownsClient) return;   // shared client closed by owner
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }

    private async ensureTtl() {
        if (this.ttlSet) return;
        this.ttlSet = true; // Set immediately to prevent concurrent calls
        try {
            await this.redis.expire(this.key, this.ttl);
        } catch (e) {
            this.ttlSet = false; // Reset on failure so it retries
            console.warn(`Failed to set TTL: ${e}`);
        }
    }

    async increment(metric: string, by: number = 1): Promise<number> {
        if (by === 0) return await this.getValue(metric);
        try {
            const val = await this.redis.hIncrBy(this.key, metric, by);
            await this.ensureTtl();
            return val;
        } catch (e) {
            console.error(`Stats Increment Error: ${e}`);
            return 0;
        }
    }

    async getValue(metric: string): Promise<number> {
        try {
            const valStr = await this.redis.hGet(this.key, metric);
            return valStr ? parseInt(valStr, 10) : 0;
        } catch (e) {
            console.error(`Stats GetValue Error: ${e}`);
            return 0;
        }
    }

    async checkThreshold(metric: string, limit: number): Promise<boolean> {
        if (!limit || limit <= 0) return false;

        try {
            const val = await this.getValue(metric);

            if (val >= limit) {
                console.warn(`THRESHOLD BREACHED: ${metric} (${val}) >= limit (${limit})`);
                return true;
            }
        } catch (e) {
            console.error(`Stats Check Error: ${e}`);
        }
        return false;
    }

    async saveStateToDisk() {
        try {
            const data = await this.redis.hGetAll(this.key);
            await fs.writeFile(this.statsFile, JSON.stringify(data, null, 2));
        } catch (e) {
            console.error(`Failed to save stats to disk: ${e}`);
        }
    }

    async loadStateFromDisk() {
        try {
            await fs.access(this.statsFile);
            const content = await fs.readFile(this.statsFile, 'utf-8');
            const data = JSON.parse(content);
            if (Object.keys(data).length > 0) {
                // Redis HSET accepts object in newer versions, or array
                for (const [k, v] of Object.entries(data)) {
                    await this.redis.hSet(this.key, k, v as string);
                }
                console.log(`Loaded existing stats: ${JSON.stringify(data)}`);
            }
        } catch (e) {
            console.warn(`Failed to load stats from disk (starting from zero): ${e}`);
        }
    }

    async cleanup() {
        try {
            await this.redis.del(this.key);
            await this.disconnect();    // no-op when !ownsClient
            console.log(`Cleaned up stats for ${this.key}`);
        } catch (e) {
            console.error(`Stats Cleanup Error: ${e}`);
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service/crawler && npm run build && npm test`
Expected: tsc 0 errors; all `*.test.ts` pass — the 7 new injected/error/legacy assertions + the 2 retained tests green.

- [ ] **Step 5: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/crawler/src/class/StatsManager.ts \
        apps-microservices/crawler-service/crawler/src/class/StatsManager.test.ts
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

### Task 2: Wire the shared client into StatsManager at the production callsite

**Goal:** `main.ts` passes `sharedRedis` to `StatsManager` and the stale "owns its own client" comment is corrected.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (line 545 + comment at 564-565)

**Acceptance Criteria:**
- [ ] `main.ts:545` constructs `new StatsManager(sharedRedis, id, storagePath || ".")`.
- [ ] The comment at `main.ts:564-565` no longer says StatsManager "owns its own client".
- [ ] `tsc` is clean. No other line changes.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build` → tsc 0 errors. (tdd-gate stem `main` satisfied by existing `src/tests/test_main.ts`.)

**Steps:**

- [ ] **Step 1: Change the constructor call** — in `src/main.ts`, replace:

```typescript
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");
```

with:

```typescript
context.statsManager = new StatsManager(sharedRedis, id, storagePath || ".");
```

`sharedRedis` is already created and connected at `main.ts:371-375`, well above line 545. `await context.statsManager.connect();` on the next line is now a no-op on the injected path — leave it as-is.

- [ ] **Step 2: Fix the stale comment** — in the dropData branch, replace the two comment lines:

```typescript
    // Shared client survives dedup.cleanup (ownsClient=false), so no reconnect
    // needed for dedupManager. StatsManager still owns its own client.
```

with:

```typescript
    // Shared client survives all manager cleanups (ownsClient=false on dedup,
    // pushed, checked AND now stats), so no reconnect is needed. The
    // statsManager.connect() below is a no-op on the injected path (kept for
    // symmetry with the legacy URL constructor).
```

- [ ] **Step 3: Verify build**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc 0 errors.

- [ ] **Step 4: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

### Task 3: Update crawler-service CLAUDE.md

**Goal:** Replace the now-false "StatsManager still opens its own Redis client" deferred-follow-up note with the migrated state.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (the note at line 384, in "Redis Connection Leak Prevention" → "Node side")

**Acceptance Criteria:**
- [ ] The "deferred follow-up" note is replaced with text stating StatsManager now uses the injected shared client (`ownsClient=false`), conn count is 1, legacy URL ctor retained, with a spec link.
- [ ] No other CLAUDE.md content changed.

**Verify:** `grep -n "injected shared client" apps-microservices/crawler-service/CLAUDE.md` → returns the new line; `grep -n "still opens its own Redis client" apps-microservices/crawler-service/CLAUDE.md` → returns nothing.

**Steps:**

- [ ] **Step 1: Replace the note** — in `apps-microservices/crawler-service/CLAUDE.md`, replace:

```markdown
Note: `StatsManager` still opens its own Redis client. Deferred follow-up — see spec § Deferred follow-ups.
```

with:

```markdown
`StatsManager` now consumes the injected shared client (`ownsClient=false`), eliminating the separate idle-reaped connection; per-crawl Redis connection count is **1**. The legacy URL constructor is retained for tests. See `docs/superpowers/specs/2026-06-17-statsmanager-redis-resilience-design.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -n "injected shared client" apps-microservices/crawler-service/CLAUDE.md`
Expected: one match (the new line). And `grep -n "still opens its own Redis client" …` → no match.

- [ ] **Step 3: Commit** (coordinator — see header)

```bash
git add apps-microservices/crawler-service/CLAUDE.md
# coordinator: git -c commit.encoding=utf-8 commit -F .git/<MSG>.txt
```

---

## Self-Review

**Spec coverage:**
- §5.1 StatsManager injected ctor + no-ops → Task 1 ✓
- §5.2 main.ts:545 wiring + :565 comment → Task 2 ✓
- §5.3 RedisHealthMonitor no change → no task (correct) ✓
- §8 tests (injected no-op, delegation, error-path, legacy) → Task 1 Step 1 ✓
- §11 T3 CLAUDE.md:384 replacement → Task 3 ✓

**Placeholder scan:** none — every code step shows complete file contents or exact old→new strings.

**Type consistency:** ctor signature `(clientOrUrl: RedisClientType | string, crawlId, storagePath, ttlSeconds?)` is identical in Task 1's code, Task 1's tests, and Task 2's callsite. `ownsClient` private field used consistently. Method names match the existing surface.
