# Redis Loss & Progress Stall Detection — Design

**Status:** Draft
**Date:** 2026-05-21
**Author:** Rindra ANDRIANJANAKA
**Scope:** `apps-microservices/crawler-service` (Node crawler + Python orchestrator), Marketplace BO PHP webhook receiver

## 1. Problem

For an active crawl, repeated Node-side Redis connection failures were logged to stderr:

```
[stderr] Redis Heartbeat Error: Error: connect ECONNREFUSED 10.0.1.220:6379
[stderr] Redis Dedup Error: Error: connect ECONNREFUSED 10.0.1.220:6379
```

These errors were silently swallowed:

- `crawler/src/main.ts:382` registers `redisClient.on('error', err => console.error(...))` only — no escalation, no exit.
- `crawler/src/class/DedupManager.ts:13` does the same.
- Heartbeat `setInterval` (`main.ts:449-491`) wraps each publish in try/catch; on failure logs "Failed to send heartbeat" and continues forever.
- Initial `redisClient.connect()` failure (`main.ts:492-494`) is also caught and swallowed — the crawler runs without any heartbeat interval at all.

The Node process remained alive but stuck (no URL progress), while the Python orchestrator's stale-detection heartbeat was still being refreshed because the Python monitor loop writes `last_heartbeat=now()` based on Python's view of process liveness (PID alive), not crawl progress. Reconciliation therefore never fired, and the crawl stayed marked as `running` indefinitely.

### Root cause

Python's `last_heartbeat` is a **process-liveness proxy**, not a **crawl-progress proxy**. Node-side Redis loss is invisible to the orchestrator's staleness check (`STALE_JOB_THRESHOLD_LOCAL=180s` + `RECONCILIATION_INTERVAL_SECONDS=300s`).

The Pub/Sub channel `crawler:heartbeat` exists, but its payload contains only CPU/RAM/topProcesses (`main.ts:475-486`) — no URL counters — and it is consumed only by `crawler-monitor-backend` (Go) for observability, never by the orchestrator.

## 2. Goals

- Detect sustained Node-side Redis loss within ~60s and terminate the crawl deterministically.
- Detect generic crawl progress stalls (any cause: Redis loss, browser hang, infinite loop, deadlock) within ~10min as a safety net.
- Communicate failure cause to the Marketplace BO via the existing failure-webhook contract with a new `failure_cause` field.
- Preserve existing capacity-counter invariants, webhook idempotency (request_id UUID), and OOM relaunch semantics.

## 3. Non-goals

- Python orchestrator Redis loss (separate failure mode — orchestrator can't read Redis to act on anything; existing reconciliation + leader election handles its half).
- Detecting partial Redis instance degradation (slow latency, partial key namespace eviction) — out of scope, would require richer metrics.
- Auto-relaunch on Redis loss (rejected during brainstorm — fail-and-webhook chosen for deterministic BO behavior).
- Notifying BO via a side-channel when both orchestrator and Redis are unreachable.

## 4. Approach

**Selected approach (Option A in brainstorm):** Central `RedisHealthMonitor` + `ProgressMonitor` supervisor running inside the Node crawler. Both monitors detect their respective failure mode and invoke the existing `gracefulShutdown` helper with a new exit code. The Python orchestrator extends its exit-code dispatch to map the new codes to failure status + descriptive webhook message.

Alternatives rejected:
- **Inline tracking** in each Redis client class — duplication, drift risk when new Redis clients are added.
- **Python-side detection only** (subscribe to pub/sub heartbeat) — pub/sub messages are not persisted; false positives on Python restart; would also require adding URL counters to the heartbeat payload (which is half of approach A anyway).

## 5. Architecture

```
crawler/src/
├── class/
│   ├── RedisHealthMonitor.ts          NEW  central success/error tracker
│   ├── ProgressMonitor.ts             NEW  Crawlee statistics sampler
│   └── DedupManager.ts                MOD  emits health events to monitor
├── main.ts                            MOD  instantiate monitors, wire shutdown,
│                                            fix swallowed startup-failure path
apps-microservices/crawler-service/app/core/
├── crawler_manager.py                 MOD  exit codes 5 + 6 dispatch
└── config.py                          MOD  informational threshold defaults
docker-compose.yml                     MOD  env passthroughs
apps-microservices/crawler-service/CLAUDE.md  MOD  exit-code table + new section
Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php
                                       MOD  add failure_cause to webhook payload whitelist
```

## 6. Components

### 6.1 `RedisHealthMonitor`

Central tracker for the health of every Redis client used by the crawler.

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
        if (this.pollHandle) clearInterval(this.pollHandle);
    }

    private evaluate(): void {
        if (this.fired) return;
        const now = this.clock();
        const globalLastSuccess = Math.max(...Array.from(this.lastSuccessAt.values()), 0);
        const sinceSuccess = now - globalLastSuccess;
        const recentErrors = Array.from(this.lastErrorAt.values()).some(t => now - t < 30_000);
        if (sinceSuccess > this.lossThresholdMs && recentErrors) {
            this.fire(`No Redis op succeeded for ${Math.round(sinceSuccess/1000)}s across ${this.lastSuccessAt.size} client(s)`);
            return;
        }
        // Per-client escalation: if one specific client is hard-down even
        // while another succeeds, escalate after 30 consecutive errors + 60s
        // without success on that client.
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

### 6.2 `ProgressMonitor`

Samples Crawlee statistics at a fixed interval, fires if no `requestsFinished` delta is observed across the stall window.

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
        if (this.pollHandle) clearInterval(this.pollHandle);
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

### 6.3 `DedupManager` modification

Constructor accepts an optional `monitor: RedisHealthMonitor`. Every public Redis operation reports success or error to the monitor without changing existing call-site behavior (Crawlee continues to receive the same safe-default returns):

```typescript
constructor(redisUrl: string, crawlId: string, ttlSeconds: number = 7 * 24 * 3600,
            monitor?: RedisHealthMonitor) {
    this.redis = createClient({ url: redisUrl });
    this.monitor = monitor;
    this.redis.on('error', (err) => {
        console.error('Redis Dedup Error:', err);
        this.monitor?.onError('dedup', err);
    });
    ...
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
```

Pattern applied to all public methods (`isKnown`, `isKnownBatch`, `filterNewBlockedBatch`, `getCount`, `getAllUrlsIterator`, `loadFromIterator`, `cleanup`). `connect()` reports `onError` and **rethrows** so the caller can fail fast at startup.

### 6.4 `main.ts` wiring

```typescript
// ... after env/CLI parsing, before Crawlee setup
const redisMonitor = new RedisHealthMonitor(
    Number(process.env.REDIS_LOSS_THRESHOLD_MS ?? 60_000),
    (reason) => {
        console.error(`[fatal] redis_lost: ${reason}`);
        console.error(JSON.stringify({ event: 'redis_lost', reason, snapshot: redisMonitor.snapshot() }));
        gracefulShutdown('REDIS_LOST', 5);
    },
);
redisMonitor.attach('heartbeat');
redisMonitor.attach('dedup');
redisMonitor.start();

// Heartbeat client — replace the existing top-level swallow
const redisClient = createClient({ url: redisUrl });
redisClient.on('error', err => {
    console.error('Redis Heartbeat Error:', err);
    redisMonitor.onError('heartbeat', err);
});
try {
    await redisClient.connect();
    redisMonitor.onSuccess('heartbeat');
    // existing setInterval — wrap each publish:
    //   try { await redisClient.publish(...); redisMonitor.onSuccess('heartbeat'); }
    //   catch (e) { redisMonitor.onError('heartbeat', e); }
} catch (err) {
    console.error('Failed to connect to Redis for Heartbeat:', err);
    process.exit(5); // CHANGED — was silently swallowed
}

// DedupManager
const dedup = new DedupManager(redisUrl, crawlId, undefined, redisMonitor);
try {
    await dedup.connect();
    redisMonitor.onSuccess('dedup');
} catch (err) {
    console.error('Failed to connect to Redis for Dedup:', err);
    process.exit(5);
}

// ProgressMonitor — after Crawlee instance available
const progressMonitor = new ProgressMonitor(
    () => crawler.statistics.state.requestsFinished,
    Number(process.env.PROGRESS_STALL_THRESHOLD_MS ?? 600_000),
    (reason) => {
        console.error(`[fatal] progress_stalled: ${reason}`);
        console.error(JSON.stringify({ event: 'progress_stalled', reason }));
        gracefulShutdown('PROGRESS_STALL', 6);
    },
);
progressMonitor.start();

// In gracefulShutdown enter (existing function), add:
//   redisMonitor.stop();
//   progressMonitor.stop();
// to prevent further fires during in-flight shutdown.
```

## 7. Data Flow

### Happy path

```
Crawlee fetch → DedupManager.sAdd → Redis OK → monitor.onSuccess('dedup')
              → heartbeat publish OK → monitor.onSuccess('heartbeat')
              → ProgressMonitor reads statistics.requestsFinished, growing → no fire
Process exit code 0/2 → Python: status=finished → success webhook
```

### Redis loss path

```
T+0s    Node: Redis client emits 'error' (ECONNREFUSED) → monitor.onError('heartbeat')
T+0s    Crawlee URL fetch → DedupManager.sAdd throws → catch returns true (Crawlee continues)
                          → monitor.onError('dedup')
T+5s    Monitor poll: sinceSuccess=5s < 60s → no fire
T+30s   ... still no Redis. sinceSuccess=30s < 60s → no fire
T+60s   Monitor poll: sinceSuccess=60s + recentErrors=true → fire
        → onLost(reason) → gracefulShutdown('REDIS_LOST', 5)
        → process.exit(5)

Python _monitor_process: exit code 5
       → status='failed'
       → message_erreur_crawling = "Redis connection lost: <reason>"
       → failure_cause = 'redis_lost'
       → failure webhook (idempotent via request_id UUID)
       → capacity counter decremented
```

### Progress stall path

```
T+0s    ProgressMonitor samples finished=N
T+30s   sample N (no change)
...
T+600s  oldest sample at T+0 with finished=N, current finished=N → fire
        → onStalled(reason) → gracefulShutdown('PROGRESS_STALL', 6)
        → process.exit(6)

Python: exit 6 → status='failed', failure_cause='progress_stalled',
        message="Crawl stalled — no URL progress for 10min"
```

### Exit-code table (updated)

| Code | Meaning                 | Python status     | Webhook              |
|------|-------------------------|-------------------|----------------------|
| 0    | Success                 | finished          | success              |
| 2    | Partial success         | finished          | success              |
| 3    | OOM relaunch            | restarting_oom    | (none until terminal)|
| 4    | Update mode no data     | failed            | failure (descriptive)|
| **5**| **Redis connection lost** | **failed**      | **failure (cause: redis_lost)** |
| **6**| **Progress stall**       | **failed**      | **failure (cause: progress_stalled)** |
| other| Failure                 | failed            | failure              |

## 8. Edge cases

| Case | Behavior |
|------|----------|
| Transient blip < threshold | `onSuccess` refreshes `lastSuccessAt`, no fire. Self-healing. |
| Partial loss — one client OK, another broken | Global path tolerates (max-success). Per-client escalation fires after 30 consec errors + 60s no success on that client. |
| Empty samples / cold start | ProgressMonitor early-returns until window age ≥ threshold. No startup false-positive. |
| Legitimate slow page | 10min default tolerates single slow page. Tunable via env per-deployment. |
| Crawl finishes during stall window | Normal exit (0/2) wins via idempotency. Monitors stop on shutdown enter. |
| OOM relaunch | OOM path stops both monitors via `gracefulShutdown` enter. Relaunched child starts fresh. |
| Python orchestrator Redis loss | Out of scope — existing reconciliation + leader election handles. |
| `gracefulShutdown` itself hangs | 30s safety timer set on shutdown enter → hard `process.exit(code)` fallback. |
| Test isolation | All timing args injectable via constructor (`clock`, intervals). No module-level singletons. |

## 9. Failure-cause observability

Failure webhook payload (sent from Python orchestrator to `script_process_detect_fiche_produit.php`) adds a new optional field:

```
failure_cause = redis_lost | progress_stalled | oom_max_restarts | update_mode_no_data | other
```

PHP-side `handle_crawler_webhook` (`fonctions_scrapping.php:622`) already whitelists telemetry keys at `enregistrer_crawl_event` (l.636-643). Add `failure_cause` to that whitelist — no other PHP changes required. The field flows into `crawl_events` for ops triage.

## 10. Configuration

### Node env vars

| Var | Default | Description |
|-----|---------|-------------|
| `REDIS_LOSS_THRESHOLD_MS` | `60000` | Sustained Redis-loss duration before fire. |
| `PROGRESS_STALL_THRESHOLD_MS` | `600000` | No-URL-progress duration before fire. |
| `PROGRESS_SAMPLE_INTERVAL_MS` | `30000` | (optional) sample interval — exposed for slow-page deployments. |

### Python `config.py`

Informational defaults only — Node owns the actual thresholds:

```python
REDIS_LOSS_THRESHOLD_MS: int = 60_000
PROGRESS_STALL_THRESHOLD_MS: int = 600_000
```

### `docker-compose.yml` — crawler-service block

```yaml
environment:
  ...
  - REDIS_LOSS_THRESHOLD_MS=${REDIS_LOSS_THRESHOLD_MS:-60000}
  - PROGRESS_STALL_THRESHOLD_MS=${PROGRESS_STALL_THRESHOLD_MS:-600000}
```

## 11. Testing

### Node.js unit tests (`crawler/tests/`)

**`RedisHealthMonitor.test.ts`** — injected clock, no real timers.

| Test | Expected |
|------|----------|
| `onSuccess refreshes lastSuccessAt` | counters reset |
| `does not fire below threshold` | no `onLost` call |
| `fires after threshold + recent errors` | `onLost` called once |
| `does not fire when success arrives` | window reset |
| `idempotent — fires once even on multiple ticks` | 1× call |
| `tolerant to single broken client (global path)` | no fire when other client healthy |
| `per-client escalation` | fires on isolated client failure |
| `stop() clears interval` | no fire after stop |

**`ProgressMonitor.test.ts`**

| Test | Expected |
|------|----------|
| `does not fire before window age` | no fire |
| `fires after stall threshold with no progress` | 1× call |
| `does not fire when progress occurs` | no fire |
| `samples pruned to window+slack` | bounded length |
| `idempotent` | 1× call |

### Node.js integration test — `redis-loss.integration.test.ts`

Spin up local Redis (testcontainers), start crawler against fake target, kill Redis mid-crawl, assert exit code 5 within `REDIS_LOSS_THRESHOLD_MS + 10s`. Skip when `RUN_INTEGRATION` unset.

### Python tests — `apps-microservices/crawler-service/tests/test_exit_code_dispatch.py`

| Test | Expected |
|------|----------|
| `exit 5 → status failed + redis_lost cause` | job_data shows cause |
| `exit 6 → status failed + progress_stalled cause` | job_data shows cause |
| `exit 5 + already terminal → no overwrite` | invariant preserved |
| `failure webhook UUID persisted` | reusable |
| `capacity counter decremented` | running_count -1 |

### PHP test (Marketplace BO)

| Test | Expected |
|------|----------|
| `failure_cause persisted to crawl_events` | row contains cause |
| `idempotency holds with new field` | duplicate request_id blocked |

### Manual smoke test (post-deploy)

1. Trigger crawl on test domain.
2. After 30s, block port 6379 outbound from crawler container.
3. Observe `event: redis_lost` log within ~60s.
4. Verify process exits 5, BO `crawl_events` shows `failure_cause=redis_lost`.
5. Restore Redis, trigger new crawl, verify normal completion.

### Negative case — false-positive guard

Crawl a known-slow domain with default 10min threshold — must complete without fire. If false fires, raise `PROGRESS_STALL_THRESHOLD_MS` per-deployment.

## 12. Rollout

1. Node + Python changes ship together (same image build). Backward compatible: BO doesn't require `failure_cause` to function.
2. Default thresholds chosen conservative (60s / 10min) — minimal false-positive risk.
3. Watch first 48h of production logs for any `event: progress_stalled` events on legitimate slow domains. If observed, raise `PROGRESS_STALL_THRESHOLD_MS` env in compose.

## 13. CLAUDE.md updates

`apps-microservices/crawler-service/CLAUDE.md`:

- Extend "Exit Codes" table — rows 5 + 6.
- New section "Redis Loss / Progress Stall Detection" — purpose, thresholds, env vars, troubleshooting (false-positive playbook).
- Note: `_monitor_process` exit-code branches now include `redis_lost` and `progress_stalled` failure causes.

## 14. Open questions

None at spec time. All design decisions resolved in brainstorm.

## 15. References

- `apps-microservices/crawler-service/crawler/src/main.ts:379-494` — current heartbeat block (to be modified).
- `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts` — current dedup client (to be modified).
- `apps-microservices/crawler-service/app/core/crawler_manager.py:_monitor_process` — exit-code dispatch.
- `apps-microservices/crawler-service/CLAUDE.md` § Exit Codes, § Failure Webhook Idempotency, § Capacity Counter Invariants — existing invariants preserved.
- `docs/superpowers/specs/2026-04-18-webhook-idempotency-design.md` — `request_id` UUID idempotency contract (unchanged).
- Marketplace `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php:622` — `handle_crawler_webhook` receiver (one-line whitelist addition).
