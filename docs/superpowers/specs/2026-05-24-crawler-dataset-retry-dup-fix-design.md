# Crawler Dataset Retry-Dup Fix — Design Spec

**Date:** 2026-05-24
**Service:** `apps-microservices/crawler-service/crawler/`
**Bug class:** silent data loss + retry-induced duplicate dataset rows on `requestHandler` timeout.
**Triggering incident:** crawl 6649 (`bp-tech.fr`) — exit code 2 ("success"), `requestsFinished: 1`, **0 URLs extracted**, no failure webhook fired.

---

## 1. Problem statement

Two coupled defects in the crawler handler combine to produce a silent failure mode:

1. **Dedup-poisoning on timeout.** `routes.ts:380` writes the URL to the `dedup:{crawlId}` Redis SET on FIRST handler entry, **before** rendering, detection, and link extraction. If `requestHandlerTimeoutSecs` (default 120s) fires mid-handler, Crawlee reclaims the request for retry — but the retry hits `dedup.addUrl()` → `isNew=false` → `isDoublon=true` → `routes.ts:387 if (!isDoublon)` short-circuits the entire extraction block. `enqueueLinks` never runs. The seed page yields zero discovered URLs and Crawlee exits cleanly via `isFinishedFunction() === true` (empty queue) with exit code 2.

2. **Dataset duplication on retry.** Once the dedup poisoning is fixed (so retry actually replays the handler), a NEW class of bug becomes the dominant risk: `routerDefaultHandler` at `functions.ts:1639-1643` calls `Dataset.pushData(row)` then `requestQueue.markRequestHandled(request)`. If a timeout fires **between** `pushData` and `markRequestHandled`, the row is written, Crawlee never ack'd the request, and the retry will call `pushData` again — duplicate row.

The user's explicit constraint: **no duplicate dataset rows under any retry scenario.** Any fix that addresses defect 1 alone re-exposes defect 2.

### 1.1 Why this stayed hidden

- Crawler exits with code 2 ("partial success") which Python `_classify_exit_code` maps to `status=finished` with success webhook. Marketplace BO sees a normal crawl.
- Stats counter `requestsFinished: 1` masks the fact that link extraction never completed.
- The retry success on the second pass (`Doublon url : ...`) IS Crawlee-success — `isFinishedFunction()` returns true, no error thrown.
- No metric or log line surfaces the pattern. Operator must inspect log manually.

### 1.2 Severity classification

- Probability per crawl: highest on Camoufox + Apify proxy + slow site + memory pressure (all true for crawl 6649: 0.38GB usable / 6GB limit, 94% page cache eviction).
- Blast radius: every crawl that hits a 120s handler timeout. No counter exists today to estimate frequency.
- Detection: post-hoc only — operator compares `requestsTotal: 1` with `requestsRetries > 0` in stats JSON.

---

## 2. Design overview

**Two coupled fixes, one spec:**

- **Option A — retry-aware doublon bypass** (fixes defect 1).
- **Option F — Redis-backed `PushedSet` guarding `pushData` callsites + UpdateChecker writes** (fixes defect 2).

Combined: **F+A under Strict-data scope** (per user choice on guard granularity).

### 2.1 Why not the alternatives

Considered and rejected during brainstorm (see "Trade-off analysis" in conversation log):

- **Move SADD to handler success-end:** still re-runs `pushData` on retry → duplicate. Fails user constraint.
- **Rollback dedup on failure (Option C):** retry replays handler → `pushData` replays → duplicate. Fails user constraint.
- **Two-phase pending/completed dedup (Option D):** still doesn't gate `pushData`; only fixes dedup semantics. Fails user constraint.
- **Reorder handler so pushData last (Option G):** best-effort only. Doesn't help if timeout fires AT pushData.
- **Resumable handler with per-step Redis flags (Option H):** heavy. Many flags. Cleanup pressure.
- **Idempotent pushData via in-process Set (Option E):** loses state on OOM-relaunch → cross-restart can dup.
- **Full-isolation guard (Q1 option c):** touches statsManager and decision-engine APIs. Risks breaking dashboards that rely on current non-idempotent counter semantics.
- **userData flag instead of Redis (Q2 option b):** Crawlee userData persistence under OOM-relaunch is unverified. Wrong assumption silently re-enables duplicates.

---

## 3. Architecture

### 3.1 New component: `PushedSet`

`apps-microservices/crawler-service/crawler/src/class/PushedSet.ts`

```ts
import { createClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './RedisHealthMonitor.js';

export class PushedSet {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttlSeconds: number;
    private ttlSetAt: number = 0;

    constructor(
        redisClient: RedisClientType,
        crawlId: string,
        opts?: { ttlSeconds?: number; monitor?: RedisHealthMonitor }
    ) {
        this.redis = redisClient;
        this.key = `pushed:${crawlId}`;
        this.ttlSeconds = opts?.ttlSeconds ?? 86400;  // 24h default, mirrors DedupManager
        this.monitor = opts?.monitor;
    }

    /**
     * Atomically claim the URL slot for a single dataset write.
     * Returns true if this caller wins the claim (must proceed with pushData).
     * Returns false if another attempt has already claimed (must skip pushData).
     * Fail-open: returns true on Redis error (mirrors DedupManager.addUrl posture).
     */
    async tryClaim(url: string): Promise<boolean> {
        try {
            const isNew = await this.redis.sAdd(this.key, url);
            await this.ensureTtl();
            this.monitor?.onSuccess('pushed');
            return isNew === 1;
        } catch (e) {
            this.monitor?.onError('pushed', e);
            console.error(`PushedSet tryClaim error: ${e}`);
            return true;  // fail-open
        }
    }

    /**
     * Remove URL from claim set. Used only on explicit rollback paths.
     * Not called by default — claim-before-write semantics treat a failed
     * pushData as accepted residual data loss for that URL.
     */
    async release(url: string): Promise<void> {
        try {
            await this.redis.sRem(this.key, url);
            this.monitor?.onSuccess('pushed');
        } catch (e) {
            this.monitor?.onError('pushed', e);
        }
    }

    private async ensureTtl(): Promise<void> {
        const now = Date.now();
        if (now - this.ttlSetAt < this.ttlSeconds * 1000 / 2) return;
        try {
            await this.redis.expire(this.key, this.ttlSeconds);
            this.ttlSetAt = now;
        } catch (e) {
            console.warn(`PushedSet TTL set failed: ${e}`);
        }
    }
}
```

### 3.2 Wiring

`apps-microservices/crawler-service/crawler/src/context.ts` adds:
```ts
pushedSet: undefined as PushedSet | undefined,
```

`apps-microservices/crawler-service/crawler/src/main.ts` (alongside DedupManager construction):
```ts
context.pushedSet = new PushedSet(sharedRedisClient, String(id), { monitor });
```

Pass `pushedSet` to `UpdateChecker` constructor — UpdateChecker becomes one of the consumers.

### 3.3 Guarded callsites (4 total)

| File:line | Callsite | Pre-guard | Post-guard |
|---|---|---|---|
| `functions.ts:1639-1643` | `routerDefaultHandler` main dataset push | `if (!await pushedSet.tryClaim(url)) { await requestQueue.markRequestHandled(request); return; }` | unchanged |
| `routes.ts:917` | `nfrDataset.pushData` non-French | `if (!await pushedSet.tryClaim(url)) return;` | unchanged |
| `routes.ts:446` | `errorDataset.pushData` challenge fail | `if (!await pushedSet.tryClaim(url)) return;` | unchanged |
| `UpdateChecker.checkUrl` | top of method, before any state mutation | `if (context.pushedSet && !await context.pushedSet.tryClaim(originalUrl)) return { url: originalUrl, action: 'ignored', reason: 'already_pushed' };` | unchanged |

**Critical invariant:** `markRequestHandled` MUST fire on the skip-pushData path for the main `routerDefaultHandler` callsite. Otherwise Crawlee retries indefinitely. The other 3 callsites don't own request lifecycle (Crawlee acks happen elsewhere in route flow).

### 3.4 Companion fix — retry-aware doublon bypass

`routes.ts:387` becomes:
```ts
if (!isDoublon || request.retryCount > 0) {
    // proceed with full extraction logic
}
```

Effect: retry attempts always re-run the handler. Dedup-poisoning bug is bypassed for retries. Combined with `PushedSet`, dataset duplication is prevented.

Concurrency safety preserved: sibling-page concurrent enqueues still hit `Crawlee RequestQueue` uniqueKey dedup (confirmed via `interfaces/queue.ts:7,14`). Within-process parallel handlers for same URL still claim via `DedupManager` SADD atomicity. No new race surface.

### 3.5 Cleanup

`gracefulShutdown` in `main.ts` adds:
```ts
try {
    await sharedRedisClient.del(`pushed:${id}`);
    console.log(`Cleaned up pushed set for pushed:${id}`);
} catch (e) {
    console.warn(`Failed to clean pushed set: ${e}`);
}
```

Placed alongside existing `dedup:{id}` and `stats:{id}` teardown (visible in log line `Cleaned up deduplication set for dedup:6649`).

---

## 4. Data flow

### 4.1 Happy path (first attempt succeeds)

```
handler enters
SADD dedup:{id} url           → isNew=true → !isDoublon → proceed
render + detect + enqueueLinks
routerDefaultHandler:
  SADD pushed:{id} url         → isNew=true → tryClaim=true → proceed
  pushData(row)                → row written
  markRequestHandled            → Crawlee ack'd
```

### 4.2 Retry path (the bug case — pushData fired then timeout)

```
Attempt 1:
  handler enters
  SADD dedup:{id} url            → isNew=true → !isDoublon → proceed
  render + detect + enqueueLinks
  routerDefaultHandler:
    SADD pushed:{id} url          → isNew=true → tryClaim=true → proceed
    pushData(row)                 → row written
                                   ← TIMEOUT HERE → handler killed
    markRequestHandled             ← NEVER REACHED

Attempt 2 (retry):
  handler enters (request.retryCount=1)
  SADD dedup:{id} url             → isNew=false → isDoublon=true
  retryCount > 0                  → BYPASS doublon-bail (Option A)
  render + detect + enqueueLinks
  routerDefaultHandler:
    SADD pushed:{id} url           → isNew=false → tryClaim=false → SKIP pushData
    markRequestHandled              → Crawlee ack'd
  → crawl proceeds, no duplicate row, link extraction completed
```

### 4.3 Retry path (timeout before pushData)

```
Attempt 1:
  handler enters
  SADD dedup:{id} url             → isNew=true
  render in progress
                                   ← TIMEOUT HERE → handler killed
  routerDefaultHandler NEVER REACHED

Attempt 2 (retry):
  handler enters (request.retryCount=1)
  SADD dedup:{id} url             → isNew=false → isDoublon=true
  retryCount > 0                  → BYPASS
  render + detect + enqueueLinks
  routerDefaultHandler:
    SADD pushed:{id} url           → isNew=true → tryClaim=true → proceed
    pushData(row)                  → row written ONCE
    markRequestHandled              → Crawlee ack'd
  → row written exactly once
```

---

## 5. Error handling

| Failure point | Behavior |
|---|---|
| Redis SADD throws (Redis loss) | `tryClaim` returns `true` (fail-open, mirrors `DedupManager.addUrl:98`). Proceed with write. Monitor counts error. |
| `pushData` throws | Re-throw → Crawlee retries → next attempt: `tryClaim=false` → skip pushData → `markRequestHandled` → done. **Residual: row never written.** Same data-loss trade as DedupManager. |
| `markRequestHandled` throws after successful `pushData` | Re-throw → Crawlee retries → retry's `tryClaim=false` → skip pushData → `markRequestHandled` → done. No duplicate. |
| Timeout between `tryClaim` and `pushData` | URL claimed but no row. Retry → skip → row lost. Window: ~1ms (Redis SADD latency). Probability ~10⁻⁵ of 120s timeout. Accepted. |
| Timeout between `pushData` and `markRequestHandled` | **This is the bug case the fix saves.** Retry skips pushData via tryClaim, then acks. |
| OOM-relaunch with `pushed:{id}` populated | Redis state persists. Retry across processes works. |
| Hard crash before shutdown cleanup | TTL (24h) auto-evicts. |

**Monitor integration:** `PushedSet` accepts `RedisHealthMonitor` injection same as `DedupManager`. Errors bump the shared health counter. Sustained outage contributes to `redis_lost` exit code 5. **No new `failure_cause` introduced.**

**Counter / metric impact:** None. Per user choice (Q1=Strict-data), stats counters (`processed`, `errors`, `redirects`, `dropped_cb`, `filtered_duplicate`) stay non-idempotent. They measure handler entries, not unique URLs. `new_urls` is already success-block-gated (routes.ts:684-697).

---

## 6. Testing strategy

### 6.1 Unit tests — `PushedSet` (new file `class/PushedSet.test.ts`)

1. `tryClaim` returns `true` on first call, `false` on second for same URL.
2. `tryClaim` returns `true` on Redis error (fail-open semantics).
3. `tryClaim` calls `ensureTtl` (rate-limited per `ttlSeconds/2` window).
4. `release` removes URL from set (smoke; unused by default).
5. `monitor.onError('pushed', e)` fires on SADD failure; `onSuccess('pushed')` fires on SADD success.

### 6.2 Unit tests — `DedupManager` (regression)

6. Existing 4 tests stay green. No API change to DedupManager.

### 6.3 Integration tests — `routes.ts` handler

7. **Happy path** — first attempt succeeds; `pushData` called once; `markRequestHandled` called once.
8. **Retry on doublon (Option A)** — `request.retryCount=1`, `isDoublon=true` → handler bypasses early return, full extraction logic runs.
9. **Retry mid-pushData** — first attempt's pushData fires + then handler throws; second attempt: `tryClaim=false` → pushData not called → `markRequestHandled` called → enqueueLinks continues.
10. **Retry before pushData** — first attempt throws before reaching `routerDefaultHandler`; second attempt: `tryClaim=true` → pushData fires once.
11. **Three pushData callsites coverage** — assert each (main / nfr / error) guards via `tryClaim`. Mock call-count assertions.

### 6.4 Integration tests — `UpdateChecker`

12. `checkUrl(url)` called twice with same URL → first call writes to the action-appropriate JSONL file (deleted / redirected / new_url) exactly once; second call returns `{action: 'ignored', reason: 'already_pushed'}` and performs zero `writeJsonl` invocations. Assert via `jsonlWriter.writeLine` mock call count.

### 6.5 Manual smoke test (operator playbook)

13. In test env, set `requestHandlerTimeoutSecs=10` (via Crawlee config override). Trigger crawl on a known-slow site (or inject a `setTimeout` delay before pushData). Expect:
    - Log shows `tryClaim=false` skip on retry attempt.
    - Dataset JSON output: `grep -c "url" {storagePath}/storage/datasets/{domain}/*.json` equals number of unique URLs (no dup).
    - `requestQueue.markRequestHandled` ack visible.
14. Post-crawl: `redis-cli EXISTS pushed:{crawlId}` → 0 (cleanup fired).

### 6.6 Coverage expectations

Existing test count: **84** (per the recent `npm test` run on 2026-05-24).
New tests added by this spec:
- §6.1 PushedSet unit: **5** (#1–#5).
- §6.3 routes integration: **5** (#7–#11; #11 itself covers all 3 pushData callsites — main / nfr / error — but is counted as one parameterised test).
- §6.4 UpdateChecker integration: **1** (#12).
- **Total: 11 new automated tests.**
- §6.5 manual smoke: **2** operator-executed steps (#13–#14), not part of `npm test` count.

Target post-fix: **95 tests green** (`84 + 11`).

---

## 7. Acceptance criteria

- [ ] `PushedSet` class implemented at `class/PushedSet.ts` with `tryClaim`, `release`, `ensureTtl`.
- [ ] `context.pushedSet` initialised in `main.ts` with shared Redis client and `RedisHealthMonitor`.
- [ ] `routerDefaultHandler` (`functions.ts:1625-1644`) guards `pushData` via `tryClaim`; falls through to `markRequestHandled` on skip.
- [ ] `routes.ts:917` (nfr push) guards via `tryClaim`.
- [ ] `routes.ts:446` (error push) guards via `tryClaim`.
- [ ] `UpdateChecker.checkUrl` guards via `tryClaim`; returns `{action: 'ignored', reason: 'already_pushed'}` on skip.
- [ ] `routes.ts:387` changed to `if (!isDoublon || request.retryCount > 0)`.
- [ ] `gracefulShutdown` cleans up `pushed:{crawlId}` Redis key alongside `dedup:{id}` and `stats:{id}`.
- [ ] All 5 `PushedSet` unit tests pass.
- [ ] All retry-path integration tests pass.
- [ ] Existing 84 tests stay green.
- [ ] Manual smoke playbook executed against a controlled slow-handler scenario: 0 duplicate dataset rows confirmed via `uniq -c` count.

---

## 8. Out of scope (deferred follow-ups)

- **Full-isolation guard for stats counters** (Q1=c rejected). Existing non-idempotent counters stay. If future operational need surfaces, opt in per-counter via the same `PushedSet` pattern.
- **Decision-engine observation idempotency** (questionmark/diez `recordQuestionMarkObservation`, `recordClassification`). Retry may double-count samples → tier promotion fires earlier. Surfaced as known minor side effect; not addressed here.
- **Detection API quota mitigation.** Retry burns one more `DETECTION_MAX_CONCURRENCY` slot. Not a duplicate; quota cost only. Defer.
- **`Dataset.pushData` becoming dedup-safe upstream** — Crawlee Dataset is append-only by design. Upstream Crawlee fix is outside scope.
- **Failure signal for "seed-only crawl after retries"** — currently silent (exit code 2). Adding a `failure_cause = seed_no_extraction` heuristic at shutdown is a separate orthogonal observability spec.
- **`DedupManager` fail-open on Redis error** (`DedupManager.ts:98` returns `true`). Means Redis loss → mass re-render. Different bug class. Defer.
- **Server-side timeout bump** to give Camoufox slow sites more room (raises `requestHandlerTimeoutSecs` from 120s to 180-240s). Orthogonal mitigation. Defer.

---

## 9. References

- Triggering log: crawl 6649 `bp-tech.fr` 2026-05-24T04:31:33Z (in-conversation log).
- Existing dedup pattern: `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts`.
- Health monitor: `apps-microservices/crawler-service/crawler/src/class/RedisHealthMonitor.ts`.
- Shared Redis client factory: `apps-microservices/crawler-service/crawler/src/redisClient.ts` (Spec-C, 2026-05-21).
- Crawlee RequestQueue uniqueKey: `interfaces/queue.ts:7,14`.
- Crawlee `Dataset` semantics: append-only (no built-in URL-keyed dedup).
- Conversation log root cause analysis: 2026-05-24 brainstorming session (this document's parent context).
