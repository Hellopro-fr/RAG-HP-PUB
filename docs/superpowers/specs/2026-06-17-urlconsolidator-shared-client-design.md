# UrlConsolidator Shared Redis Client — Design

**Date:** 2026-06-17
**Status:** Draft — pending user review
**Branch:** `features/poc` (local, unpushed — operator decides push/deploy)
**Scope:** crawler-service Node engine (`apps-microservices/crawler-service/crawler`) only. No proto / shared-lib / Python / BO change.
**Companion to:** `docs/superpowers/specs/2026-06-17-statsmanager-redis-resilience-design.md` (same root cause; StatsManager fixed in `393809f7`..`7695106d`).

---

## 1. Problem

`UrlConsolidator` opens its **own** Redis client (`UrlConsolidator.ts:53`), distinct from the heartbeat-warmed shared client. It is the last remaining per-crawl separate Redis connection (the StatsManager migration flagged it at `crawler-service/CLAUDE.md:384`).

Unlike StatsManager (observability + thresholds), UrlConsolidator's client backs an **update-mode correctness path**: `UpdateChecker.checkUrl` calls `consolidator.isInDataset(loadedUrl)` (`UpdateChecker.ts:224`) on pages during the crawl, to decide whether a URL already belongs to the previous crawl's dataset.

## 2. Root Cause (same idle-reap as StatsManager)

`UrlConsolidator` is instantiated only in **update mode** (`main.ts:679-690`): `new UrlConsolidator(redisUrl, …)` → `connect()`. Its client is then used per-page via `isInDataset` for the crawl lifetime (the dataset SET is deliberately kept alive — `UrlConsolidator.ts` docstring L32-33, and `cleanup()` does NOT delete `datasetKey`).

During a quiet gap > 300 s (long navigation, stall, proxy outage — no pages processed → no `isInDataset` calls), the client sits idle and the server reaper (`CONFIG timeout 300`, set by `redis_diagnose.sh --apply-timeout`) closes it. The shared client never idles (2 s heartbeat).

**Impact (worse than StatsManager's silent stat loss):** the first `isInDataset` after the reap hits the dead socket → caught at `UrlConsolidator.ts:95-98` → **returns `false`** (fail-open). A URL that *is* in the previous dataset is then misjudged as not-in-dataset → wrong update-mode dedup/classification for that page. node-redis auto-reconnects, so subsequent calls recover; the error is bounded to pages processed immediately after a reap, but it is a **correctness** fault, not just a metric undercount.

Secondary: it is a standing separate connection (counts against the connection-cap leak-prevention goal — `CLAUDE.md` "Redis Connection Leak Prevention").

**Note on `connect()`/`disconnect()`:** `connect()` (`L63-67`) already no-ops on an already-open client, so passing the connected shared client is safe. But `disconnect()` (`L69-73`) and `cleanup()` (`L319-326`) call `this.redis.disconnect()` unconditionally when open — on an injected shared client that would **close the shared connection** mid/post-crawl. The `ownsClient` guard is therefore mandatory.

## 3. Decision

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Migrate `UrlConsolidator` onto the injected shared client** (mirror StatsManager / DedupManager `ownsClient`). | Removes the last separate per-crawl client (root cause); warm socket → no reap → no wrong-dedup. |
| D2 | **Best-effort, no buffer; `isInDataset` keeps its fail-open `return false` on error — unchanged.** | Once the reap is gone, the residual is a rare reconnect blip. Changing the fail-open default is a separate behavioral decision, out of scope. |
| D3 | **Mirror the `ownsClient` pattern; no monitor wiring; no `RedisHealthMonitor` change.** | Injected path: owner attached the `'shared'` error listener; per-op monitor reporting is intentionally skipped (DedupManager precedent). |
| D4 | **Backward-compatible constructor — keep the URL form.** | Legacy callers / tests still construct `UrlConsolidator(url, …)`. Only `main.ts:688` switches to the injected client. |
| D5 | **No config flag.** | Pure internal resilience fix. |
| D6 | **Update-mode only — no behavior change for non-update crawls** (they never create a UrlConsolidator). | Bounds the blast radius. |

## 4. Architecture

After this change the crawler subprocess holds **one** Redis connection per crawl (the shared client), in both update and non-update modes. `UrlConsolidator` joins `DedupManager` / `PushedSet` / `checkedSet` / `StatsManager` as a consumer of the injected shared client.

```
sharedRedis (createSharedRedisClient — heartbeat keeps it warm)
  ├─ heartbeat   publish crawler:heartbeat (2s)
  ├─ DedupManager      sAdd / sIsMember …      (ownsClient=false)
  ├─ PushedSet         sAdd …                  (ownsClient=false)
  ├─ checkedSet        sAdd …                  (ownsClient=false)
  ├─ StatsManager      hIncrBy / hGet …        (ownsClient=false)
  └─ UrlConsolidator   sAdd / sIsMember / sScan / expire / del  (ownsClient=false)  ◄── THIS CHANGE
```

## 5. Component Specs

### 5.1 `UrlConsolidator.ts` — accept an injected client

Add `private ownsClient: boolean;`. Constructor first param becomes `clientOrUrl: RedisClientType | string`.

```typescript
constructor(
    clientOrUrl: RedisClientType | string,
    crawlId: string,
    previousCrawlId: string,
    domain: string,
    ttlSeconds: number = 7 * 24 * 3600,
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

async connect(): Promise<void> {
    if (!this.ownsClient) return;            // shared client connected by owner
    if (!this.redis.isOpen) await this.redis.connect();
}

async disconnect(): Promise<void> {
    if (!this.ownsClient) return;            // shared client closed by owner
    if (this.redis.isOpen) await this.redis.disconnect();
}
```

`cleanup()` and `fullCleanup()` are unchanged in body — they still `del` their namespaced keys and call `this.disconnect()`, which is now a no-op on the injected path:
- `cleanup()`: `del(requestQueueKey)` + `del(requestUrlKey)` + `disconnect()` (no-op). `datasetKey` is intentionally kept for `isInDataset` (unchanged — expires via TTL).
- `fullCleanup()`: also `del(datasetKey)` + `disconnect()` (no-op).

`isInDataset` / `consolidate` / `ensureTtl` / `loadRequestQueueUrls` — **unchanged** (including `isInDataset`'s fail-open `return false` on error, per D2).

### 5.2 `main.ts` — inject the shared client

Single production callsite, `main.ts:688` (inside the update-mode branch):

```typescript
// before
const consolidator = new UrlConsolidator(redisUrl, id, previousCrawlId, domain);
// after
const consolidator = new UrlConsolidator(sharedRedis, id, previousCrawlId, domain);
```

`sharedRedis` is created/connected at `main.ts:371-375`, far above line 688. `await consolidator.connect()` (`main.ts:689`) → no-op (injected). Shutdown `context.urlConsolidator.cleanup()` (`main.ts:1124`) dels the temp keys without disconnecting the shared client, before the single `sharedRedis.disconnect()` (`main.ts:1133`). The local `const redisUrl` at `main.ts:687` becomes unused if no other consumer needs it — verify and remove only if dead (it may still feed other update-mode code; leave it if referenced).

### 5.3 `RedisHealthMonitor.ts` / `context.ts` — no change

Closed `ClientName` union untouched; `context.urlConsolidator` stays typed `UrlConsolidator | null`. Public method surface unchanged.

## 6. Data Flow & Invariants

- Redis keys unchanged: `update_dataset:{id}`, `update_rq:{id}`, `update_ru:{id}`, 7-day TTL.
- `datasetKey` still survives `cleanup()` (kept for `isInDataset`); only `update_rq`/`update_ru` are deleted at `cleanup()`. Keys are namespaced — no collision with `dedup:`/`pushed:`/`checked:`/`stats:`.
- The shared client is connected once (`main.ts:373`) and disconnected once (`main.ts:1133`); UrlConsolidator never connects/disconnects it on the injected path.
- `increment`-style concurrency: `sAdd`/`sIsMember`/`sScan`/`expire` multiplexed on the shared socket — node-redis pipelines them; the proven pattern for the other four consumers.

## 7. Blast Radius & Impact

- **Files:** `UrlConsolidator.ts`, a new `UrlConsolidator.test.ts`, `main.ts` (one line), `CLAUDE.md`. UrlConsolidator is instantiated only at `main.ts:688`.
- **Consumers:** `UpdateChecker` (via `isInDataset`) — unaffected (same method surface). `context.ts` field type unchanged.
- **Backward compatibility:** URL constructor form retained; existing `makeMockConsolidator()`-based UpdateChecker tests pass a mock (not a real client) and are unaffected.
- **No external contract change.** Update-mode only.

## 8. Testing Strategy

No `UrlConsolidator.test.ts` exists today (UpdateChecker tests use a mock consolidator). Create one — this also satisfies the tdd-gate (editing `UrlConsolidator.ts` needs `UrlConsolidator.test.*`). Remote-only: a plain fake `RedisClientType` object (no live Redis, no DI seam needed — the injected path takes a client directly).

Fake records calls and supports: `isOpen`, `on`, `connect`/`disconnect` (spies), `del`, `sIsMember`, `sAdd`, `sScan`, `expire`.

`UrlConsolidator.test.ts` (node:test, `npm test`):
1. **Injected lifecycle no-ops** — `connect()`/`disconnect()` do not call the fake's connect/disconnect (regression guard for the `ownsClient` branch — without it, `disconnect()` would close the shared client).
2. **cleanup del-not-disconnect + keeps datasetKey** — `cleanup()` calls `del('update_rq:{id}')` and `del('update_ru:{id}')`, does **not** call `del('update_dataset:{id}')`, and does **not** disconnect.
3. **fullCleanup dels all three + no disconnect** — `del` of dataset/rq/ru keys; no disconnect on injected.
4. **isInDataset delegation** — `isInDataset(url)` calls `sIsMember('update_dataset:{id}', url)` and returns its boolean.
5. **Error path (the load-bearing correctness claim, §2)** — make the fake's `sIsMember` reject; assert `isInDataset()` catches and returns `false` (documents the fail-open behavior the reap exploits).
6. **Legacy URL path** — `new UrlConsolidator('redis://localhost:6379', id, prev, domain)` constructs without throwing (constructor does not connect — `createClient` is lazy).

Verify: `cd apps-microservices/crawler-service/crawler && npm run build && npm test` → tsc 0 errors; all `*.test.ts` pass (baseline 157 + the new UrlConsolidator suite).

## 9. Rollout

Low risk, no phased gate, no env var. Deploy = rebuild the crawler-service image. The `redis_diagnose.sh --apply-timeout` idle reap stays — it now only reaps genuine orphans.

## 10. Deferred Follow-ups

- **`isInDataset` fail-open default** (`return false` on error → treat as not-in-dataset). After this fix a reap can't occur, so it is effectively unreachable; revisiting fail-open vs fail-closed is a separate behavioral decision, out of scope.
- With this done, **no per-crawl separate Redis client remains** in the Node engine — the leak-prevention narrative closes.

## 11. Tasks (for the plan)

| Task | Files | Verify |
|------|-------|--------|
| **UC-T1** — `UrlConsolidator` injected-client constructor (`ownsClient`) + `connect`/`disconnect` guards + new `UrlConsolidator.test.ts` (injected no-op, cleanup/fullCleanup del-not-disconnect, isInDataset delegation, error-path reject→false, legacy construct) | `UrlConsolidator.ts`, `UrlConsolidator.test.ts` | `npm run build && npm test` |
| **UC-T2** — wire `sharedRedis` into `UrlConsolidator` at `main.ts:688` | `main.ts` | `npm run build` (tdd-gate stem `main` satisfied by `src/tests/test_main.ts`) |
| **UC-T3** — docs: update the `CLAUDE.md:384` note (drop the "Remaining separate client: UrlConsolidator … deferred" caveat now that it is fixed; record that no separate per-crawl client remains) | `apps-microservices/crawler-service/CLAUDE.md` | grep the updated note |
