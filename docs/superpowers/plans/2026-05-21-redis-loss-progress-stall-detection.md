# Redis Loss & Progress Stall Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect Node-side Redis loss (60s) and crawl progress stalls (10min) inside the crawler, fail the crawl deterministically with exit codes 5/6, and propagate a `failure_cause` field through the failure webhook to Marketplace BO.

**Architecture:** Two new monitor classes (`RedisHealthMonitor`, `ProgressMonitor`) inside the Node crawler, both injected via `main.ts` startup. Existing Redis clients (heartbeat in `main.ts`, `DedupManager`) report success/error to the central health monitor. On threshold breach, monitors invoke the existing `gracefulShutdown` helper with a new exit code. Python orchestrator extends its exit-code dispatch to map codes 5/6 to failed status with descriptive cause. PHP webhook receiver passively persists `failure_cause` via the existing telemetry whitelist.

**Tech Stack:** TypeScript (Node 22), `node --import tsx --test` (built-in node:test runner), Python 3.10 (pytest), Pydantic Settings, docker-compose, PHP 7.4.

**Spec:** `docs/superpowers/specs/2026-05-21-redis-loss-progress-stall-detection-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.ts` | CREATE | Central success/error tracker, polling evaluator, idempotent fire |
| `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.test.ts` | CREATE | Unit tests w/ injected clock |
| `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.ts` | CREATE | Crawlee statistics sampler, idempotent fire |
| `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.test.ts` | CREATE | Unit tests w/ injected clock + readFn |
| `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts` | MODIFY | Accept optional `monitor`, report per-op success/error |
| `apps-microservices/crawler-service/crawler/src/main.ts` | MODIFY | Instantiate monitors, fail-fast on Redis connect failure, wrap heartbeat publish, stop monitors in gracefulShutdown |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` | MODIFY | Exit codes 5/6 branches in `_send_failure_webhook` + `_monitor_process` persist `failure_cause` |
| `apps-microservices/crawler-service/app/core/config.py` | MODIFY | Add informational threshold defaults |
| `apps-microservices/crawler-service/tests/test_exit_code_dispatch.py` | CREATE | Python tests for codes 5/6 + failure_cause persistence |
| `apps-microservices/crawler-service/CLAUDE.md` | MODIFY | Exit-code table rows + new section |
| `docker-compose.yml` | MODIFY | Env passthroughs for thresholds |
| `Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` | MODIFY | Add `failure_cause` to telemetry payload whitelist |

---

## Task 0: Implement `RedisHealthMonitor` (Node, TDD)

**Goal:** A standalone class that tracks Redis client health and fires a callback after sustained loss.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.ts`
- Create: `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.test.ts`

**Acceptance Criteria:**
- [ ] `attach`, `onSuccess`, `onError`, `start`, `stop`, `evaluate`, `snapshot` methods present
- [ ] Injected `clock` arg enables time-travel in unit tests (no real timers)
- [ ] Idempotent `fire` — onLost called once even on multiple ticks past threshold
- [ ] Global path: fire when no client reported success for `lossThresholdMs` AND any client errored in last 30s
- [ ] Per-client escalation: fire when single client has ≥30 consecutive errors AND no success for ≥60s
- [ ] All tests pass: `npm test -- src/class/RedisHealthMonitor.test.ts`

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test -- src/class/RedisHealthMonitor.test.ts` → all assertions pass.

**Steps:**

- [ ] **Step 1: Write failing unit tests first**

Create `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.test.ts`:

```typescript
import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { RedisHealthMonitor } from './RedisHealthMonitor.js';

describe('RedisHealthMonitor', () => {
    let now = 0;
    const clock = () => now;
    let onLostCalls: string[] = [];
    const onLost = (r: string) => { onLostCalls.push(r); };

    beforeEach(() => {
        now = 1_000_000;
        onLostCalls = [];
    });

    it('does not fire below threshold even with errors', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        now += 30_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('fires after threshold + recent errors', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
        assert.match(onLostCalls[0], /No Redis op succeeded/);
    });

    it('does not fire when success arrives within window', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 50_000;
        m.onError('heartbeat', new Error('boom'));
        now += 5_000;
        m.onSuccess('heartbeat');
        now += 30_000;
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('idempotent — fires once across multiple ticks past threshold', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        m['evaluate']();
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
    });

    it('tolerates one broken client when another succeeds (global path)', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        now += 70_000;
        // dedup keeps reporting success right now
        m.onSuccess('dedup');
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('per-client escalation when one client hard-down + no success >60s', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        // dedup succeeds frequently so global path never fires
        for (let i = 0; i < 35; i++) {
            now += 2_000;
            m.onError('heartbeat', new Error('boom'));
            m.onSuccess('dedup');
        }
        // heartbeat last success was at attach time ~70s ago, errorCounter=35, dedup keeps global healthy
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
        assert.match(onLostCalls[0], /Client 'heartbeat' had \d+ consecutive errors/);
    });

    it('onSuccess resets error counter for that client', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        for (let i = 0; i < 10; i++) {
            m.onError('heartbeat', new Error('boom'));
        }
        assert.equal(m.snapshot().errorCounters.heartbeat, 10);
        m.onSuccess('heartbeat');
        assert.equal(m.snapshot().errorCounters.heartbeat, 0);
    });

    it('stop() prevents future fires', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.stop();
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        // evaluate would fire, but stop already cleared any interval — we still
        // assert that calling evaluate after stop manually still works (no crash).
        // For interval-based stop, that's covered by start() not being called.
        m['evaluate']();
        // Idempotency flag uncovers either path; once fired, won't re-fire
        const n = onLostCalls.length;
        m['evaluate']();
        assert.equal(onLostCalls.length, n);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/RedisHealthMonitor.test.ts`
Expected: FAIL with `Cannot find module './RedisHealthMonitor.js'`

- [ ] **Step 3: Write the implementation**

Create `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.ts`:

```typescript
type ClientName = 'heartbeat' | 'dedup' | string;

export class RedisHealthMonitor {
    private lastSuccessAt: Map<ClientName, number> = new Map();
    private lastErrorAt: Map<ClientName, number> = new Map();
    private errorCounters: Map<ClientName, number> = new Map();
    private pollHandle?: ReturnType<typeof setInterval>;
    private fired = false;

    constructor(
        private readonly lossThresholdMs: number,
        private readonly onLost: (reason: string) => void,
        private readonly clock: () => number = () => Date.now(),
    ) {}

    attach(name: ClientName): void {
        this.lastSuccessAt.set(name, this.clock());
        this.errorCounters.set(name, 0);
    }

    onSuccess(name: ClientName): void {
        this.lastSuccessAt.set(name, this.clock());
        this.errorCounters.set(name, 0);
    }

    onError(name: ClientName, _err: unknown): void {
        this.lastErrorAt.set(name, this.clock());
        this.errorCounters.set(name, (this.errorCounters.get(name) ?? 0) + 1);
    }

    start(): void {
        this.pollHandle = setInterval(() => this.evaluate(), 5000);
    }

    stop(): void {
        if (this.pollHandle) {
            clearInterval(this.pollHandle);
            this.pollHandle = undefined;
        }
    }

    private evaluate(): void {
        if (this.fired) return;
        const now = this.clock();
        const successValues = Array.from(this.lastSuccessAt.values());
        if (successValues.length === 0) return;
        const globalLastSuccess = Math.max(...successValues);
        const sinceSuccess = now - globalLastSuccess;
        const recentErrors = Array.from(this.lastErrorAt.values()).some(t => now - t < 30_000);
        if (sinceSuccess > this.lossThresholdMs && recentErrors) {
            this.fire(`No Redis op succeeded for ${Math.round(sinceSuccess/1000)}s across ${this.lastSuccessAt.size} client(s)`);
            return;
        }
        for (const [name, errCount] of this.errorCounters) {
            if (errCount < 30) continue;
            const lastSuccess = this.lastSuccessAt.get(name) ?? 0;
            if (now - lastSuccess > 60_000) {
                this.fire(`Client '${name}' had ${errCount} consecutive errors, no success for ${Math.round((now - lastSuccess)/1000)}s`);
                return;
            }
        }
    }

    private fire(reason: string): void {
        this.fired = true;
        this.stop();
        this.onLost(reason);
    }

    snapshot() {
        return {
            lastSuccessAt: Object.fromEntries(this.lastSuccessAt),
            lastErrorAt: Object.fromEntries(this.lastErrorAt),
            errorCounters: Object.fromEntries(this.errorCounters),
        };
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/RedisHealthMonitor.test.ts`
Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.ts apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.test.ts
git commit -m "feat(crawler): add RedisHealthMonitor with success/error tracking + escalation"
```

---

## Task 1: Implement `ProgressMonitor` (Node, TDD)

**Goal:** A class that samples `requestsFinished` at a fixed interval and fires when no progress is observed across the stall window.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.ts`
- Create: `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.test.ts`

**Acceptance Criteria:**
- [ ] `start`, `stop`, `tick` (private) methods present
- [ ] `readFinishedCount` injected for testability
- [ ] No false-fire before first window elapses
- [ ] Single fire on stall confirmed across full window
- [ ] No fire when delta observed
- [ ] Samples pruned to `stallThresholdMs + 60s` slack

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test -- src/class/ProgressMonitor.test.ts` → all assertions pass.

**Steps:**

- [ ] **Step 1: Write failing unit tests**

Create `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.test.ts`:

```typescript
import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { ProgressMonitor } from './ProgressMonitor.js';

describe('ProgressMonitor', () => {
    let now = 0;
    const clock = () => now;
    let onStalledCalls: string[] = [];
    const onStalled = (r: string) => { onStalledCalls.push(r); };
    let finished = 0;
    const readFinished = () => finished;

    beforeEach(() => {
        now = 1_000_000;
        onStalledCalls = [];
        finished = 0;
    });

    it('does not fire before stall window age reached', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 5; i++) {
            now += 30_000;
            m['tick']();
        }
        // ~150s elapsed, window=600s — should not fire
        assert.equal(onStalledCalls.length, 0);
    });

    it('fires once after full stall window with no progress', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 21; i++) {
            now += 30_000;
            m['tick']();
        }
        // 21 * 30s = 630s elapsed, oldest sample at ~600s ago — fire
        assert.equal(onStalledCalls.length, 1);
        assert.match(onStalledCalls[0], /No URL progress/);
    });

    it('does not fire when progress observed within window', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 21; i++) {
            now += 30_000;
            if (i === 10) finished += 1;
            m['tick']();
        }
        assert.equal(onStalledCalls.length, 0);
    });

    it('idempotent across multiple ticks past threshold', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 30; i++) {
            now += 30_000;
            m['tick']();
        }
        assert.equal(onStalledCalls.length, 1);
    });

    it('samples pruned to threshold + slack', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        // Force progress so it never fires
        for (let i = 0; i < 100; i++) {
            now += 30_000;
            finished += 1;
            m['tick']();
        }
        const internal = (m as any).samples as Array<{at: number; finished: number}>;
        // 100 ticks * 30s = 3000s, threshold+slack = 660s → ~22 samples retained
        assert.ok(internal.length <= 25, `expected <=25, got ${internal.length}`);
    });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/ProgressMonitor.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

Create `apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.ts`:

```typescript
type ProgressSample = { at: number; finished: number };

export class ProgressMonitor {
    private samples: ProgressSample[] = [];
    private pollHandle?: ReturnType<typeof setInterval>;
    private fired = false;

    constructor(
        private readonly readFinishedCount: () => number,
        private readonly stallThresholdMs: number,
        private readonly onStalled: (reason: string) => void,
        private readonly sampleIntervalMs: number = 30_000,
        private readonly clock: () => number = () => Date.now(),
    ) {}

    start(): void {
        this.pollHandle = setInterval(() => this.tick(), this.sampleIntervalMs);
    }

    stop(): void {
        if (this.pollHandle) {
            clearInterval(this.pollHandle);
            this.pollHandle = undefined;
        }
    }

    private tick(): void {
        if (this.fired) return;
        const finished = this.readFinishedCount();
        const now = this.clock();
        this.samples.push({ at: now, finished });
        const cutoff = now - (this.stallThresholdMs + 60_000);
        this.samples = this.samples.filter(s => s.at >= cutoff);

        const oldest = this.samples[0];
        if (!oldest) return;
        const windowAge = now - oldest.at;
        if (windowAge < this.stallThresholdMs) return;
        if (finished === oldest.finished) {
            this.fired = true;
            this.stop();
            this.onStalled(`No URL progress for ${Math.round(windowAge/1000)}s (stuck at ${finished} finished)`);
        }
    }
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/ProgressMonitor.test.ts`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.ts apps-microservices/crawler-service/crawler/src/class/ProgressMonitor.test.ts
git commit -m "feat(crawler): add ProgressMonitor for URL-progress stall detection"
```

---

## Task 2: Integrate `RedisHealthMonitor` into `DedupManager` (Node, TDD)

**Goal:** `DedupManager` reports each Redis operation success/error to an injected monitor without changing existing call-site behavior.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts`
- Create: `apps-microservices/crawler-service/crawler/src/class/DedupManager.monitor.test.ts`

**Acceptance Criteria:**
- [ ] Constructor accepts optional 4th arg `monitor?: RedisHealthMonitor`
- [ ] Every public method that touches Redis calls `monitor?.onSuccess('dedup')` on success and `monitor?.onError('dedup', err)` in catch
- [ ] `connect()` rethrows on failure (was: implicit throw, now explicit + reports onError)
- [ ] Existing return values preserved (no behavior change at call sites)
- [ ] New unit test verifies monitor receives success + error calls

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test -- src/class/DedupManager.monitor.test.ts` → tests pass + `npm run build` → no type errors.

**Steps:**

- [ ] **Step 1: Write failing test**

Create `apps-microservices/crawler-service/crawler/src/class/DedupManager.monitor.test.ts`:

```typescript
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { DedupManager } from './DedupManager.js';
import { RedisHealthMonitor } from './RedisHealthMonitor.js';

describe('DedupManager monitor wiring', () => {
    it('reports onError to monitor when Redis client emits error', () => {
        const onLostCalls: string[] = [];
        const monitor = new RedisHealthMonitor(60_000, (r) => onLostCalls.push(r), () => Date.now());
        monitor.attach('dedup');
        // Use a bad URL so the redis client will emit 'error' on connection attempts.
        const d = new DedupManager('redis://127.0.0.1:1', 'test-crawl', 60, monitor);
        // Listener registered — drive an error event manually.
        // Access internal client to trigger the registered 'error' listener path.
        (d as any).redis.emit('error', new Error('boom'));
        const snap = monitor.snapshot();
        assert.equal(snap.errorCounters.dedup, 1);
    });

    it('reports onSuccess after a successful op (mocked client)', async () => {
        const onLostCalls: string[] = [];
        const monitor = new RedisHealthMonitor(60_000, (r) => onLostCalls.push(r), () => Date.now());
        monitor.attach('dedup');
        const d = new DedupManager('redis://127.0.0.1:1', 'test-crawl', 60, monitor);
        // Swap internal client for a stub so we don't need a real Redis.
        (d as any).redis = {
            sAdd: async () => 1,
            expire: async () => true,
            isOpen: false,
            on: () => {},
        };
        const isNew = await d.addUrl('https://example.test/');
        assert.equal(isNew, true);
        const snap = monitor.snapshot();
        // sAdd + expire (in ensureTtl) → 2 successes for 'dedup'
        assert.ok(snap.errorCounters.dedup === 0);
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/DedupManager.monitor.test.ts`
Expected: FAIL — constructor signature mismatch or `monitor` undefined.

- [ ] **Step 3: Modify `DedupManager`**

Edit `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts`:

Replace the existing class with:

```typescript
import { createClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './RedisHealthMonitor.js';

export class DedupManager {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private blockedKey: string;

    constructor(redisUrl: string, crawlId: string, ttlSeconds: number = 7 * 24 * 3600,
                monitor?: RedisHealthMonitor) {
        this.redis = createClient({ url: redisUrl });
        this.monitor = monitor;
        this.redis.on('error', (err) => {
            console.error('Redis Dedup Error:', err);
            this.monitor?.onError('dedup', err);
        });
        this.key = `dedup:${crawlId}`;
        this.blockedKey = `blocked_log:${crawlId}`;
        this.ttl = ttlSeconds;
    }

    async connect() {
        try {
            await this.redis.connect();
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            throw e;
        }
    }

    async disconnect() {
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }

    private async ensureTtl() {
        if (this.ttlSet) return;
        this.ttlSet = true;
        try {
            await this.redis.expire(this.key, this.ttl);
            await this.redis.expire(this.blockedKey, this.ttl);
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.ttlSet = false;
            this.monitor?.onError('dedup', e);
            console.warn(`Failed to set TTL: ${e}`);
        }
    }

    async addUrl(url: string): Promise<boolean> {
        try {
            const isNew = await this.redis.sAdd(this.key, url);
            await this.ensureTtl();
            this.monitor?.onSuccess('dedup');
            return isNew === 1;
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Add Error: ${e}`);
            return true;
        }
    }

    async isKnown(url: string): Promise<boolean> {
        try {
            const result = await this.redis.sIsMember(this.key, url);
            this.monitor?.onSuccess('dedup');
            return result;
        } catch (e) {
            this.monitor?.onError('dedup', e);
            return false;
        }
    }

    async isKnownBatch(urls: string[]): Promise<Set<string>> {
        const knownSet = new Set<string>();
        if (urls.length === 0) return knownSet;
        try {
            const results = await this.redis.smIsMember(this.key, urls);
            for (let i = 0; i < urls.length; i++) {
                if (results[i]) knownSet.add(urls[i]);
            }
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Batch Check Error: ${e}`);
        }
        return knownSet;
    }

    async filterNewBlockedBatch(urls: string[]): Promise<string[]> {
        if (urls.length === 0) return [];
        const uniqueUrls = [...new Set(urls)];
        const newToLog: string[] = [];
        try {
            const results = await this.redis.smIsMember(this.blockedKey, uniqueUrls);
            const toAdd: string[] = [];
            for (let i = 0; i < uniqueUrls.length; i++) {
                if (!results[i]) {
                    newToLog.push(uniqueUrls[i]);
                    toAdd.push(uniqueUrls[i]);
                }
            }
            if (toAdd.length > 0) {
                await this.redis.sAdd(this.blockedKey, toAdd);
                await this.ensureTtl();
            }
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Blocked Log Batch Error: ${e}`);
            return uniqueUrls;
        }
        return newToLog;
    }

    async getCount(): Promise<number> {
        try {
            const c = await this.redis.sCard(this.key);
            this.monitor?.onSuccess('dedup');
            return c;
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Count Error: ${e}`);
            return 0;
        }
    }

    async getAllUrls(): Promise<string[]> {
        try {
            const r = await this.redis.sMembers(this.key);
            this.monitor?.onSuccess('dedup');
            return r;
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Get All Error: ${e}`);
            return [];
        }
    }

    async *getAllUrlsIterator(): AsyncGenerator<string> {
        try {
            let cursor = 0;
            do {
                const result = await this.redis.sScan(this.key, cursor, { COUNT: 200 });
                cursor = result.cursor;
                for (const member of result.members) yield member;
            } while (cursor !== 0);
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Scan Error: ${e}`);
        }
    }

    async loadFromList(urls: string[]) {
        if (!urls.length) return;
        const chunkSize = 1000;
        for (let i = 0; i < urls.length; i += chunkSize) {
            const chunk = urls.slice(i, i + chunkSize);
            if (chunk.length > 0) {
                try {
                    await this.redis.sAdd(this.key, chunk);
                    this.monitor?.onSuccess('dedup');
                } catch (e) {
                    this.monitor?.onError('dedup', e);
                    throw e;
                }
            }
        }
        await this.ensureTtl();
        console.log(`Loaded ${urls.length} URLs into deduplication set.`);
    }

    async loadFromIterator(urlIterator: AsyncGenerator<string>): Promise<number> {
        const chunkSize = 1000;
        let buffer: string[] = [];
        let totalCount = 0;
        for await (const url of urlIterator) {
            buffer.push(url);
            totalCount++;
            if (buffer.length >= chunkSize) {
                try {
                    await this.redis.sAdd(this.key, buffer);
                    this.monitor?.onSuccess('dedup');
                } catch (e) {
                    this.monitor?.onError('dedup', e);
                    throw e;
                }
                buffer = [];
            }
        }
        if (buffer.length > 0) {
            try {
                await this.redis.sAdd(this.key, buffer);
                this.monitor?.onSuccess('dedup');
            } catch (e) {
                this.monitor?.onError('dedup', e);
                throw e;
            }
        }
        await this.ensureTtl();
        console.log(`Loaded ${totalCount} URLs into deduplication set (streaming).`);
        return totalCount;
    }

    async cleanup() {
        try {
            await this.redis.del(this.key);
            await this.redis.del(this.blockedKey);
            await this.disconnect();
            this.monitor?.onSuccess('dedup');
            console.log(`Cleaned up deduplication set for ${this.key}`);
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Cleanup Error: ${e}`);
        }
    }
}
```

- [ ] **Step 4: Run tests + build**

Run: `cd apps-microservices/crawler-service/crawler && npm test -- src/class/DedupManager.monitor.test.ts && npm run build`
Expected: tests pass, no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/DedupManager.ts apps-microservices/crawler-service/crawler/src/class/DedupManager.monitor.test.ts
git commit -m "feat(crawler): wire DedupManager Redis ops to RedisHealthMonitor"
```

---

## Task 3: Wire heartbeat block in `main.ts` to monitor + fail-fast on connect failure

**Goal:** Replace the swallowed `console.error` + silent skip with monitor reporting and a hard `process.exit(5)` on initial Redis connect failure.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (lines ~379-494 heartbeat block)

**Acceptance Criteria:**
- [ ] `redisClient.on('error', ...)` calls `redisMonitor.onError('heartbeat', err)`
- [ ] Initial `redisClient.connect()` failure → `process.exit(5)` (no longer swallowed)
- [ ] Each `redisClient.publish(...)` reports success or error to monitor
- [ ] No behavior change on happy path (heartbeat still publishes every 2s)
- [ ] `npm run build` succeeds with no type errors

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build` → no errors. Manual code review confirms the changes.

**Steps:**

- [ ] **Step 1: Read current heartbeat block**

Read `apps-microservices/crawler-service/crawler/src/main.ts` lines 379-495 to ground the edit. Confirm:
- L379-382: `redisClient` declaration + error handler
- L384-491: `try { await redisClient.connect(); ... setInterval(... publish ...) } catch { console.error }`

- [ ] **Step 2: Add RedisHealthMonitor import + instance at top of file (after existing imports)**

Edit `main.ts`: add import (immediately after the `DedupManager` import line, currently L29):

```typescript
import { RedisHealthMonitor } from "./class/RedisHealthMonitor.js";
import { ProgressMonitor } from "./class/ProgressMonitor.js";
```

Then before line 379 (the heartbeat block start), declare the monitor (use the same `redisUrl` variable declared on line 380; hoist `redisUrl` ONE line earlier so the monitor block can reference it):

```typescript
// --- Redis Health + Progress Monitors ---
const redisUrl = process.env.REDIS_URL || 'redis://redis:6379';
const redisLossThresholdMs = Number(process.env.REDIS_LOSS_THRESHOLD_MS ?? 60_000);
const redisMonitor = new RedisHealthMonitor(
    redisLossThresholdMs,
    (reason) => {
        console.error(`[fatal] redis_lost: ${reason}`);
        console.error(JSON.stringify({ event: 'redis_lost', reason, snapshot: redisMonitor.snapshot() }));
        // gracefulShutdown is declared later in the file; safe to forward-reference
        // via the top-level `gracefulShutdown` const because we only call it at fire-time.
        void gracefulShutdown('REDIS_LOST', 5);
    },
);
redisMonitor.attach('heartbeat');
redisMonitor.attach('dedup');
redisMonitor.start();
```

Note: `gracefulShutdown` is declared on L897 as a `const`. The callback closes over it — at fire-time it will be defined. Confirm via the build.

- [ ] **Step 3: Replace the heartbeat block (the existing `const redisUrl = ...` on the original L380 is now removed since we hoisted it)**

Replace lines that were 380-494 with:

```typescript
// --- Heartbeat Mechanism ---
const redisClient = createClient({ url: redisUrl });
redisClient.on('error', (err) => {
    console.error('Redis Heartbeat Error:', err);
    redisMonitor.onError('heartbeat', err);
});

try {
    await redisClient.connect();
    redisMonitor.onSuccess('heartbeat');
    console.log('Connected to Redis for Heartbeat');

    const hostname = os.hostname();
    const numCpus = os.cpus().length;
    const totalMem = os.totalmem();
    let lastCpuUsage = process.cpuUsage();
    let lastTime = Date.now();
    let lastContainerCpuUsec = await getContainerCpuUsec();
    let lastContainerCpuTime = Date.now();

    setInterval(async () => {
        try {
            let cpuPercent: number;
            const currentContainerCpuUsec = await getContainerCpuUsec();
            const currentTime = Date.now();
            if (currentContainerCpuUsec !== null && lastContainerCpuUsec !== null) {
                const deltaCpuUsec = currentContainerCpuUsec - lastContainerCpuUsec;
                const deltaWallUsec = (currentTime - lastContainerCpuTime) * 1000;
                cpuPercent = (deltaCpuUsec / deltaWallUsec) / numCpus;
                lastContainerCpuUsec = currentContainerCpuUsec;
                lastContainerCpuTime = currentTime;
            } else {
                const currentCpuUsage = process.cpuUsage(lastCpuUsage);
                const elapsedTime = (currentTime - lastTime) * 1000;
                cpuPercent = ((currentCpuUsage.user + currentCpuUsage.system) / elapsedTime) / numCpus;
                lastCpuUsage = process.cpuUsage();
                lastTime = currentTime;
            }
            const containerRam = await getContainerMemoryUsage();
            const topProcesses = await getTopProcesses();
            const heartbeat = {
                type: 'heartbeat',
                replicaId: hostname,
                jobId: id,
                domain: domain,
                cpu: Math.min(Math.max(cpuPercent, 0), 1),
                ram: containerRam,
                totalRam: totalMem,
                topProcesses: topProcesses,
                timestamp: Date.now(),
                status: 'running'
            };
            await redisClient.publish('crawler:heartbeat', JSON.stringify(heartbeat));
            redisMonitor.onSuccess('heartbeat');
        } catch (e) {
            redisMonitor.onError('heartbeat', e);
            console.error('Failed to send heartbeat:', e);
        }
    }, 2000);
} catch (err) {
    console.error('Failed to connect to Redis for Heartbeat:', err);
    redisMonitor.onError('heartbeat', err);
    // FAIL-FAST: do not run a crawl with broken Redis from start.
    process.exit(5);
}
// ---------------------------
```

Note: keep `getContainerCpuUsec`, `getContainerMemoryUsage`, `getTopProcesses`, `id`, `domain` references unchanged — they remain in scope.

- [ ] **Step 4: Build to verify type correctness**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: no errors. (TypeScript will complain if `gracefulShutdown` is not yet declared at usage site; the `void` + closure-at-call-time means it's only checked for existence. If TS still complains, declare `let gracefulShutdown: (reason: string, exitCode?: number) => Promise<void>;` near the top and assign at the existing declaration site.)

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler): wire heartbeat client to RedisHealthMonitor + fail-fast on connect"
```

---

## Task 4: Pass monitor to `DedupManager` + add `ProgressMonitor` + stop monitors in `gracefulShutdown`

**Goal:** Complete the wiring so all health signals flow into the monitors and `gracefulShutdown` cleanly stops them.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (around L552 DedupManager instantiation + L897 gracefulShutdown + after Crawlee instance ready)

**Acceptance Criteria:**
- [ ] `new DedupManager(redisUrl, id, undefined, redisMonitor)` passes the monitor
- [ ] `await context.dedupManager.connect()` failure path exits with code 5
- [ ] `ProgressMonitor` instantiated after `context.crawlerInstance` is set (find the line where `crawler` is assigned to context; instantiate immediately after) and `start()` called
- [ ] `gracefulShutdown` enter calls `redisMonitor.stop()` and `progressMonitor.stop()` (handles undefined safely if progressMonitor never initialized)
- [ ] Build succeeds

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npm test` → all tests pass + build clean.

**Steps:**

- [ ] **Step 1: Modify DedupManager instantiation (L552)**

Find:
```typescript
context.dedupManager = new DedupManager(redisUrl, id);
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");

await context.dedupManager.connect();
```

Replace with:
```typescript
context.dedupManager = new DedupManager(redisUrl, id, undefined, redisMonitor);
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");

try {
    await context.dedupManager.connect();
} catch (err) {
    console.error('Failed to connect to Redis for Dedup:', err);
    redisMonitor.onError('dedup', err);
    process.exit(5);
}
```

- [ ] **Step 2: Add ProgressMonitor wiring**

After Crawlee instance creation (search for `context.crawlerInstance =`, the assignment line — likely inside `startCrawler` call site or just before). Add right after the assignment:

```typescript
// --- Progress Monitor ---
const progressStallThresholdMs = Number(process.env.PROGRESS_STALL_THRESHOLD_MS ?? 600_000);
const progressMonitor = new ProgressMonitor(
    () => (context.crawlerInstance as any)?.stats?.state?.requestsFinished ?? 0,
    progressStallThresholdMs,
    (reason) => {
        console.error(`[fatal] progress_stalled: ${reason}`);
        console.error(JSON.stringify({ event: 'progress_stalled', reason }));
        void gracefulShutdown('PROGRESS_STALL', 6);
    },
    30_000,
);
progressMonitor.start();
```

If `context.crawlerInstance` is assigned inside `startCrawler` (in `functions.ts`), instead instantiate immediately before `await startCrawler(...)` (around L1294 per session memory) and pass `progressMonitor` into the function only if a clean injection point exists; otherwise leave `progressMonitor.start()` at the call site after `startCrawler` returns the instance reference. Inspect at edit time to choose the right insertion point. The minimal viable approach: instantiate just before `await startCrawler(...)`, start polling immediately — `readFinishedCount` will simply return 0 until Crawlee initializes, which is fine because the stall window (10min) absorbs the startup slack.

- [ ] **Step 3: Hoist `progressMonitor` reference for gracefulShutdown**

If declared inside a block, hoist:
```typescript
let progressMonitor: ProgressMonitor | undefined;
// ... later
progressMonitor = new ProgressMonitor(...);
progressMonitor.start();
```

- [ ] **Step 4: Modify `gracefulShutdown` (around L897)**

At the very start of `gracefulShutdown` (right after `isShuttingDown = true;` set, before the timing finalize), insert:

```typescript
    // Stop health monitors first so they cannot fire mid-shutdown.
    try { redisMonitor?.stop(); } catch (e) { /* ignore */ }
    try { progressMonitor?.stop(); } catch (e) { /* ignore */ }
```

- [ ] **Step 5: Build + test**

Run: `cd apps-microservices/crawler-service/crawler && npm run build && npm test`
Expected: build clean, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler): wire ProgressMonitor + DedupManager fail-fast + gracefulShutdown teardown"
```

---

## Task 5: Python — extend `_send_failure_webhook` for exit codes 5 + 6

**Goal:** Failure webhook payload includes a `failure_cause` field and a descriptive message for codes 5/6.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around L818-845)

**Acceptance Criteria:**
- [ ] `_send_failure_webhook` branches on `exit_code == 5` → `"Connexion Redis perdue (crawl bloqué)"` + `failure_cause="redis_lost"`
- [ ] `_send_failure_webhook` branches on `exit_code == 6` → `"Crawl bloqué — aucune progression URL"` + `failure_cause="progress_stalled"`
- [ ] Payload dictionary gains `failure_cause` key when applicable
- [ ] Existing branches (0, 2, 3, 4, -1, 137, <0) unchanged
- [ ] No regression to existing tests

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py -x -q` → existing tests still pass.

**Steps:**

- [ ] **Step 1: Read current `_send_failure_webhook`**

Open `app/core/crawler_manager.py`, locate `_send_failure_webhook` starting at L818. The exit_code switch is at L825-836. Confirm the function signature accepts `exit_code: int` and persists a webhook payload dict (`{"crawl_id": ..., "domain": ..., "exit_code": ..., "message_erreur_crawling": ...}`).

- [ ] **Step 2: Modify the exit_code switch**

Replace the existing branch chain:

```python
        if exit_code == -1:
            error_message = "Out Of Memory"
        elif exit_code == 3:
            error_message = "Out Of Memory"
        elif exit_code == 4:
            error_message = "Données insuffisantes (mode update)"
        elif exit_code in (137, -9):
            error_message = "Processus tué (OOM système)"
        elif exit_code is not None and exit_code < 0:
            error_message = f"Processus terminé par signal {abs(exit_code)}"
        elif exit_code not in (0, 2, 3, 4, -1, 137):
            error_message = f"Erreur inattendue (code de sortie: {exit_code})"
```

With (preserving exact existing text where present, adding 5 + 6):

```python
        failure_cause: Optional[str] = None
        if exit_code == -1:
            error_message = "Out Of Memory"
            failure_cause = "oom_max_restarts"
        elif exit_code == 3:
            error_message = "Out Of Memory"
            failure_cause = "oom_relaunch"
        elif exit_code == 4:
            error_message = "Données insuffisantes (mode update)"
            failure_cause = "update_mode_no_data"
        elif exit_code == 5:
            error_message = "Connexion Redis perdue (crawl bloqué)"
            failure_cause = "redis_lost"
        elif exit_code == 6:
            error_message = "Crawl bloqué — aucune progression URL"
            failure_cause = "progress_stalled"
        elif exit_code in (137, -9):
            error_message = "Processus tué (OOM système)"
            failure_cause = "killed_oom_system"
        elif exit_code is not None and exit_code < 0:
            error_message = f"Processus terminé par signal {abs(exit_code)}"
            failure_cause = "signal_killed"
        elif exit_code not in (0, 2, 3, 4, 5, 6, -1, 137):
            error_message = f"Erreur inattendue (code de sortie: {exit_code})"
            failure_cause = "unknown"
```

(Preserve original literal French strings byte-for-byte; only the bottom predicate list adds 5, 6.)

Add to the payload assembly:

```python
        payload = {
            "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
            ...
            "message_erreur_crawling": error_message,
        }
        if failure_cause:
            payload["failure_cause"] = failure_cause
```

(Adapt to the actual variable name in source — e.g. if it's spread inline in a call, add `"failure_cause": failure_cause` to the kwargs and ensure the call site handles `None`.)

Ensure `Optional` is imported at top of file (`from typing import Optional`) — already imported per existing code.

- [ ] **Step 3: Run existing tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_crawler_manager.py -x -q`
Expected: all existing tests pass (no regression).

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "feat(crawler-service): map exit codes 5/6 + failure_cause in failure webhook"
```

---

## Task 6: Python — persist `failure_cause` in `_monitor_process` job_data writes

**Goal:** When `_monitor_process` writes the terminal job_data after subprocess exit, include `failure_cause` so it's queryable and ends up in BO `crawl_events`.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (around L979-1058)

**Acceptance Criteria:**
- [ ] Exit codes 5 + 6 produce `job_info["failure_cause"]` keys in Redis-persisted state
- [ ] Exit code 0/2 → no `failure_cause` key (success)
- [ ] Existing code 3 (OOM_RELAUNCH) gets `failure_cause="oom_relaunch"` (consistency)
- [ ] Existing code 4 gets `failure_cause="update_mode_no_data"`

**Verify:** Run new pytest in Task 7 → all dispatch cases pass.

**Steps:**

- [ ] **Step 1: Read `_monitor_process` exit handling (~L979 onward)**

Identify the section where `exit_code = process.returncode` is read, and the subsequent branches that write `job_info["status"]` / call `_send_failure_webhook`. Confirm the structure.

- [ ] **Step 2: Insert `failure_cause` derivation immediately after `exit_code = process.returncode`**

Add helper inline:

```python
            exit_code = process.returncode

            # Derive failure_cause for downstream observability.
            failure_cause = None
            if exit_code == 3:
                failure_cause = "oom_relaunch"
            elif exit_code == 4:
                failure_cause = "update_mode_no_data"
            elif exit_code == 5:
                failure_cause = "redis_lost"
            elif exit_code == 6:
                failure_cause = "progress_stalled"
            elif exit_code in (137, -9):
                failure_cause = "killed_oom_system"
            elif exit_code is not None and exit_code < 0:
                failure_cause = "signal_killed"
            elif exit_code not in (0, 2, 3, 4, 5, 6, -1, 137):
                failure_cause = "unknown"
```

- [ ] **Step 3: Wherever `job_info` is updated to a terminal failed status (in the same function), add the field**

Find lines that set `final_status = "failed"` near the bottom of the exit-handling block. Where job_info is updated, add:

```python
                if failure_cause:
                    job_info["failure_cause"] = failure_cause
```

(Insert before the `await self._set_json(...)` or equivalent persist call.)

- [ ] **Step 4: Pass `failure_cause` to `_send_failure_webhook` callsite**

Wherever `_send_failure_webhook(url, crawl_id, domain, exit_code, ...)` is called inside `_monitor_process`, ensure the signature/payload uses the cause derived above. If `_send_failure_webhook` already derives its own (Task 5), this step is a no-op. Confirm consistency: both should compute the same cause for the same exit_code.

- [ ] **Step 5: Run regression tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/ -x -q -k "monitor_process or callback_payload or crawler_manager"`
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "feat(crawler-service): persist failure_cause in job_data on terminal exit"
```

---

## Task 7: Python — new tests for exit-code dispatch (5/6 + failure_cause)

**Goal:** Lock down the new exit-code behavior with explicit tests.

**Files:**
- Create: `apps-microservices/crawler-service/tests/test_exit_code_dispatch.py`

**Acceptance Criteria:**
- [ ] Test verifies exit code 5 produces `failure_cause="redis_lost"` in job_data
- [ ] Test verifies exit code 6 produces `failure_cause="progress_stalled"` in job_data
- [ ] Test verifies exit code 5 with already-terminal status does NOT overwrite
- [ ] Test verifies failure webhook payload includes `failure_cause` for 5/6
- [ ] All new tests pass

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_exit_code_dispatch.py -x -v` → all pass.

**Steps:**

- [ ] **Step 1: Locate the fixture pattern used by `test_crawler_manager.py`**

Read the top ~50 lines of `tests/test_crawler_manager.py` to identify how `CrawlerManager` is instantiated under test (mocked Redis, mocked subprocess, etc.). Reuse fixtures.

- [ ] **Step 2: Write the new test file**

Create `tests/test_exit_code_dispatch.py`:

```python
"""
Tests for exit-code dispatch (codes 5 = REDIS_LOST, 6 = PROGRESS_STALL).

Spec: docs/superpowers/specs/2026-05-21-redis-loss-progress-stall-detection-design.md
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def manager():
    # Reuse the existing fixture pattern; if test_crawler_manager.py
    # provides one, import it instead. Inline minimal example:
    m = CrawlerManager.__new__(CrawlerManager)
    m._set_json = AsyncMock()
    m._get_json = AsyncMock(return_value={
        "status": "running", "domain": "example.com", "crawl_id": "1",
        "callback_url": "http://hellopro.fr/script/chatgpt/script_process_detect_fiche_produit.php",
    })
    m._send_webhook_once = AsyncMock()
    m._decrement_counter = AsyncMock()
    m.local_processes = {}
    return m


@pytest.mark.asyncio
async def test_exit_code_5_sets_redis_lost_cause(manager):
    """Exit code 5 must produce failure_cause='redis_lost' in persisted job_data."""
    mock_process = MagicMock()
    mock_process.returncode = 5
    mock_process.wait = AsyncMock(return_value=5)
    with patch.object(manager, '_send_failure_webhook', new=AsyncMock()) as mock_wh:
        await manager._monitor_process("1", mock_process)
        # Assert job_data persisted with failure_cause
        persisted = manager._set_json.call_args_list[-1].args[1]
        assert persisted.get("status") == "failed"
        assert persisted.get("failure_cause") == "redis_lost"
        # Webhook called with exit_code=5
        assert mock_wh.await_args.kwargs.get("exit_code") == 5 or 5 in mock_wh.await_args.args


@pytest.mark.asyncio
async def test_exit_code_6_sets_progress_stalled_cause(manager):
    """Exit code 6 must produce failure_cause='progress_stalled' in persisted job_data."""
    mock_process = MagicMock()
    mock_process.returncode = 6
    mock_process.wait = AsyncMock(return_value=6)
    with patch.object(manager, '_send_failure_webhook', new=AsyncMock()):
        await manager._monitor_process("1", mock_process)
        persisted = manager._set_json.call_args_list[-1].args[1]
        assert persisted.get("status") == "failed"
        assert persisted.get("failure_cause") == "progress_stalled"


@pytest.mark.asyncio
async def test_exit_code_5_does_not_overwrite_terminal_status(manager):
    """If job is already terminal (e.g. stopped manually), exit 5 must not clobber."""
    manager._get_json = AsyncMock(return_value={
        "status": "stopped", "domain": "example.com", "crawl_id": "1",
    })
    mock_process = MagicMock()
    mock_process.returncode = 5
    mock_process.wait = AsyncMock(return_value=5)
    with patch.object(manager, '_send_failure_webhook', new=AsyncMock()):
        await manager._monitor_process("1", mock_process)
        # Status should remain 'stopped'
        if manager._set_json.call_args_list:
            persisted = manager._set_json.call_args_list[-1].args[1]
            assert persisted.get("status") == "stopped"


@pytest.mark.asyncio
async def test_failure_webhook_payload_contains_cause():
    """_send_failure_webhook output payload must include failure_cause for codes 5/6."""
    from app.core.crawler_manager import CrawlerManager
    m = CrawlerManager.__new__(CrawlerManager)
    captured = {}

    async def fake_send(url, payload):
        captured["url"] = url
        captured["payload"] = payload

    m._send_webhook_once = AsyncMock(side_effect=fake_send)
    m._get_or_create_failure_request_id = MagicMock(return_value="uuid-test")
    await m._send_failure_webhook(
        url="http://hellopro.fr/webhook",
        crawl_id="1", domain="example.com", exit_code=5,
        is_error=None, message_erreur_crawling=None,
    )
    assert captured["payload"].get("failure_cause") == "redis_lost"
    assert "Redis" in captured["payload"].get("message_erreur_crawling", "")
```

NOTE: Adapt fixture/import lines to actual module structure after Task 6 lands. If `pytest-asyncio` is not yet a dependency, check `requirements.txt` / `requirements-dev.txt` — pytest-asyncio is already present in the test suite (existing async tests confirm).

- [ ] **Step 3: Run the new tests**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_exit_code_dispatch.py -x -v`
Expected: 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/tests/test_exit_code_dispatch.py
git commit -m "test(crawler-service): exit code 5/6 dispatch + failure_cause assertions"
```

---

## Task 8: Config defaults + docker-compose env passthrough

**Goal:** Make thresholds visible/configurable across Python config + container env.

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/config.py`
- Modify: `docker-compose.yml` (crawler-service block ~L1336)

**Acceptance Criteria:**
- [ ] `Settings` class has `REDIS_LOSS_THRESHOLD_MS: int = 60_000` and `PROGRESS_STALL_THRESHOLD_MS: int = 600_000`
- [ ] docker-compose env block passes both to crawler container with same defaults
- [ ] Existing services unaffected

**Verify:** `cd apps-microservices/crawler-service && python -c "from app.core.config import settings; print(settings.REDIS_LOSS_THRESHOLD_MS, settings.PROGRESS_STALL_THRESHOLD_MS)"` → `60000 600000`
And: `docker compose config --no-interpolate | grep -E "REDIS_LOSS_THRESHOLD_MS|PROGRESS_STALL_THRESHOLD_MS"` → both env vars present.

**Steps:**

- [ ] **Step 1: Add Settings fields**

Edit `app/core/config.py`, inside the `Settings` class body (after `STALE_JOB_THRESHOLD_REMOTE`), add:

```python
    # Node-side monitor thresholds (informational; actual values passed via env to crawler subprocess)
    REDIS_LOSS_THRESHOLD_MS: int = 60_000
    PROGRESS_STALL_THRESHOLD_MS: int = 600_000
```

- [ ] **Step 2: Verify Python config loads**

Run: `cd apps-microservices/crawler-service && python -c "from app.core.config import settings; print(settings.REDIS_LOSS_THRESHOLD_MS, settings.PROGRESS_STALL_THRESHOLD_MS)"`
Expected: `60000 600000`

- [ ] **Step 3: Add docker-compose env passthroughs**

Edit `docker-compose.yml`. In the `crawler-service` block, inside `environment:` (after `DETECTION_LANGUE_API_URL`), add:

```yaml
      - REDIS_LOSS_THRESHOLD_MS=${REDIS_LOSS_THRESHOLD_MS:-60000}
      - PROGRESS_STALL_THRESHOLD_MS=${PROGRESS_STALL_THRESHOLD_MS:-600000}
```

- [ ] **Step 4: Validate compose syntax**

Run: `docker compose config --no-interpolate 2>&1 | grep -E "REDIS_LOSS_THRESHOLD_MS|PROGRESS_STALL_THRESHOLD_MS"`
Expected: both lines present.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/config.py docker-compose.yml
git commit -m "chore(crawler-service): env passthroughs for redis-loss and progress-stall thresholds"
```

---

## Task 9: PHP — whitelist `failure_cause` in webhook telemetry

**Goal:** Marketplace BO persists `failure_cause` from the webhook into `crawl_events`.

**Files:**
- Modify: `D:\DevHellopro\Marketplace\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_scrapping.php` (around L636-643)

**Acceptance Criteria:**
- [ ] `$payload_whitelist` array in `handle_crawler_webhook` (L636) includes `'failure_cause'`
- [ ] No other PHP behavior changes
- [ ] PHP syntax check passes

**Verify:** `php -l D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` → "No syntax errors detected".

**Steps:**

- [ ] **Step 1: Locate the whitelist**

Open `fonctions_scrapping.php`, locate `$payload_whitelist = [` (around L636). Current content:

```php
$payload_whitelist = [
    'id', 'id_domaine', 'crawl_id', 'exit_code',
    'isFinished', 'isError',
    'stored_files_count', 'success',
    'storagePath', 'request_id', 'message_erreur_crawling',
    'allUrlCrawled',
    'origine',
];
```

- [ ] **Step 2: Add `'failure_cause'`**

Replace with:

```php
$payload_whitelist = [
    'id', 'id_domaine', 'crawl_id', 'exit_code',
    'isFinished', 'isError',
    'stored_files_count', 'success',
    'storagePath', 'request_id', 'message_erreur_crawling',
    'allUrlCrawled',
    'origine',
    'failure_cause',
];
```

- [ ] **Step 3: Syntax check**

Run: `php -l D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php`
Expected: `No syntax errors detected`.

- [ ] **Step 4: Commit (in Marketplace repo)**

```bash
cd D:/DevHellopro/Marketplace
git add BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php
git commit -m "feat(scrapping): whitelist failure_cause in crawler webhook telemetry"
```

(Note: cross-repo change. The PHP commit goes in the Marketplace repo, all other commits in RAG-HP-PUB.)

---

## Task 10: CLAUDE.md updates + manual smoke-test playbook

**Goal:** Documentation reflects the new exit codes, env vars, and operational behavior.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] Exit-code table extended with rows 5 + 6
- [ ] New section "## Redis Loss / Progress Stall Detection" present with purpose, env vars, thresholds, troubleshooting, smoke-test playbook
- [ ] Spec link present at end of section

**Verify:** Manual review — `grep -E "REDIS_LOST|PROGRESS_STALL" apps-microservices/crawler-service/CLAUDE.md` returns the new rows + section header.

**Steps:**

- [ ] **Step 1: Extend exit-code table**

Locate the "Exit Codes (Node.js → Python)" table in `CLAUDE.md` (already present). Add two rows between code 4 and "Other":

```markdown
| 5 | Redis connection lost (Node-side sustained loss) | Status: `failed`, failure webhook with `failure_cause=redis_lost` |
| 6 | Progress stall (no URL progress for threshold) | Status: `failed`, failure webhook with `failure_cause=progress_stalled` |
```

- [ ] **Step 2: Add new section**

Append a new top-level section (after the "Exit Codes" section, before "Capacity Counter Invariants"):

```markdown
## Redis Loss / Progress Stall Detection

The Node crawler runs two monitors that detect failure modes invisible to Python's existing stale detection:

| Monitor | Trigger | Exit code | Threshold env var |
|---------|---------|-----------|--------------------|
| `RedisHealthMonitor` | Sustained Redis loss across all clients (heartbeat + dedup) | 5 | `REDIS_LOSS_THRESHOLD_MS` (default 60000) |
| `ProgressMonitor` | No `requestsFinished` delta across stall window | 6 | `PROGRESS_STALL_THRESHOLD_MS` (default 600000) |

Both monitors call `gracefulShutdown(reason, exitCode)` on fire. Python `_monitor_process` maps the exit codes to `status=failed` and persists `failure_cause` in `job_data` + the failure webhook payload.

**Failure-cause field values:** `redis_lost`, `progress_stalled`, `oom_relaunch`, `oom_max_restarts`, `update_mode_no_data`, `killed_oom_system`, `signal_killed`, `unknown`.

**Why this exists (root cause):** Python's `last_heartbeat` is a process-liveness proxy (PID alive ⇒ heartbeat fresh), not a crawl-progress proxy. Node-side Redis failures were silently swallowed at `main.ts:382` and `DedupManager.ts:13` — the heartbeat publish kept failing forever while reconciliation never fired. These monitors close that gap.

**Troubleshooting false positives:**
- `progress_stalled` on a legitimately slow domain → raise `PROGRESS_STALL_THRESHOLD_MS` per-deployment via env.
- `redis_lost` during a Redis maintenance window → preferred behavior; restart the crawl after maintenance.

**Smoke-test playbook:**
1. Trigger a crawl on a test domain.
2. After 30s: `docker pause <redis-container>` (or block port 6379 outbound from the crawler container).
3. Watch `crawler-service` logs — expect `event: redis_lost` JSON line within ~60s.
4. Process exits 5; verify Marketplace BO `crawl_events` row has `failure_cause=redis_lost`.
5. `docker unpause <redis-container>` and trigger a fresh crawl — verify normal completion.

Spec: `docs/superpowers/specs/2026-05-21-redis-loss-progress-stall-detection-design.md`.
```

- [ ] **Step 3: Verify edits**

Run: `grep -E "REDIS_LOST|PROGRESS_STALL|failure_cause" apps-microservices/crawler-service/CLAUDE.md | head -10`
Expected: multiple matches showing the new rows + section.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document exit codes 5/6 + Redis/progress monitors"
```

---

## Self-Review (post-write checklist)

**Spec coverage:**
- §1 Problem → Task 3 (fix swallowed connect failure)
- §5 Architecture → Tasks 0-4 (Node classes + wiring), Tasks 5-7 (Python dispatch + tests)
- §6 Components → Tasks 0, 1, 2 (each class), Task 4 (integration)
- §7 Data Flow → Tasks 3-4 (Node wiring), Task 5-6 (Python dispatch), Task 9 (PHP)
- §8 Edge cases → covered in unit tests (Tasks 0-1, 7)
- §9 Failure-cause observability → Tasks 5, 6, 9
- §10 Configuration → Task 8
- §11 Testing → Tasks 0, 1, 2, 7 + smoke-test playbook in Task 10
- §12 Rollout → Task 10 (CLAUDE.md doc)
- §13 CLAUDE.md updates → Task 10

**Placeholder scan:** No TBD/TODO. Every "Steps" block has actual code. The one ambiguity is the exact insertion point for `ProgressMonitor` in Task 4 step 2 — flagged inline ("inspect at edit time"). Acceptable because the insertion point depends on the live source structure around `startCrawler`; the steps give the minimal viable approach.

**Type consistency:** `RedisHealthMonitor`, `ProgressMonitor` class names consistent. `onLost`, `onStalled` callback names consistent. `failure_cause` field name consistent across Python + PHP + docs. `redisMonitor` / `progressMonitor` variable names consistent in `main.ts` edits.

**Cross-repo note:** Tasks 0-8, 10 commit to RAG-HP-PUB. Task 9 commits to Marketplace. Reviewer should expect two commit streams.
