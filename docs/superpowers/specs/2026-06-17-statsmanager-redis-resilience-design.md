# StatsManager Redis Resilience — Design

**Date:** 2026-06-17
**Status:** Approved (design) — ready for plan
**Branch:** `features/poc` (local, unpushed — operator decides push/deploy)
**Scope:** crawler-service Node engine (`apps-microservices/crawler-service/crawler`) only. No proto / shared-lib / Python / BO change.

---

## 1. Problem

During crawls, `StatsManager`'s Redis client logs:

```
Redis Stats Error: SocketClosedUnexpectedlyError: Socket closed unexpectedly
```

After the socket drops, the next stat write is silently lost. Stats back two consumers:

1. **Observability** — the deperdition counters reported at `main.ts:982` / `main.ts:1012` and in the BO webhook payload.
2. **Safety early-aborts** — `checkThreshold("errors" | "redirects" | "new_urls", limit)` at `routes.ts:422-424`, which terminate a crawl that exceeds configured limits.

Silent undercount of (2) means a crawl that should abort may keep running.

## 2. Root Cause (systematic-debugging Phase 1-3)

Two facts, both verified against the source:

### 2.1 A separate, traffic-starved client gets idle-reaped

`StatsManager` opens its **own** Redis client (`StatsManager.ts:13`, `createClient({ url })`), distinct from the shared client that `heartbeat` + `DedupManager` + `PushedSet` + `checkedSet` multiplex (`redisClient.ts` `createSharedRedisClient`, wired at `main.ts:371`).

The shared client receives constant traffic — the heartbeat `publish` fires **every 2000 ms** (`main.ts:472`) — so its socket is never idle. The StatsManager client receives **no periodic traffic**:

- `persistenceInterval` (600 s) touches StatsManager only in **update mode** — `generateUpdateReport` (`main.ts:646`) issues 4 `getValue` reads (`functions.ts:1279-1282`). In full-crawl mode it touches only `dedupManager` (`main.ts:625-651`), giving StatsManager zero periodic traffic. Either way a 600 s read cadence cannot keep a client warm against a 300 s reaper, and a quiet 300-600 s gap reaps it even in update mode.
- `saveStateToDisk` at `main.ts:306` lives inside the **memory-pressure handler** (fires only when memory > 85 %), not a fixed schedule.
- All other `statsManager.increment` / `getValue` calls are **request-driven** (`routes.ts`, `functions.ts`, `qmHashTracker.ts`).

The deploy host runs `redis_diagnose.sh --apply-timeout`, which sets `CONFIG SET timeout 300` (`redis_diagnose.sh:65`). That reaper — intended to clean OOM-orphaned half-open connections (CLAUDE.md "Server-side idle reap") — also closes the **live but idle** StatsManager client during quiet gaps: long navigations, crawl-tail with few in-flight requests, or a total proxy outage where every worker stalls > 300 s with zero completions. The shared client is immune because the 2 s heartbeat keeps it warm.

**This is a command-warmth asymmetry, not a keepalive difference.** The shared client explicitly enables socket keepalive (`redisClient.ts:37`, `keepAlive: 30_000`); StatsManager's own client passes only `{ url }` with no socket options (`StatsManager.ts:13`). It does not matter which: TCP keepalive operates at the transport layer and does **not** reset Redis's application-level `CONFIG timeout` reaper, which measures *command* activity. The asymmetry is command warmth — the 2 s heartbeat on the shared client vs zero periodic commands on the StatsManager client.

### 2.2 The lost write is swallowed

node-redis `^4.6.10` auto-reconnects by default (exponential backoff + jitter — confirmed against node-redis docs). So the client recovers; loss is **not** permanent. But per node-redis semantics (FAQ, *"What happens when the network goes down?"*; reconnect default per `client-configuration.md`), when a socket closes unexpectedly, a command **already written to the socket** is rejected, while commands not yet sent are queued until reconnect. After a silent reap, the *first* `increment` writes to the dead socket → rejected with `SocketClosedUnexpectedlyError` → caught at `StatsManager.ts:47-50` → **returns 0, no buffer, no retry**. The increment is lost; the read path (`getValue` / `checkThreshold`) has the same hazard — a read on a dead socket returns 0, i.e. a false "no breach".

**Correction to the initial hypothesis:** the cause is not "no reconnect" (node-redis reconnects) nor "no keepalive" (keepalive is on and irrelevant to app-level idle reap). The cause is **owning a separate, traffic-starved connection that the idle reaper closes**, plus best-effort writes that silently drop the in-flight command.

## 3. Decision

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Migrate `StatsManager` onto the injected shared client** (direction a). | Eliminates the separate idle connection — the root cause. The shared client is heartbeat-warmed, so the reaper never fires. Also fixes the read path. |
| D2 | **Best-effort writes — no in-memory buffer** (durability: option 1). | Once the reap is gone, the only residual loss is a rare in-flight blip. Thresholds are cumulative (`hIncrBy`) and re-checked every request, so a missed increment fires an abort one event late, not never. A buffer is complexity for a failure mode the root-cause fix already removes (YAGNI). |
| D3 | **Mirror `DedupManager`'s `ownsClient` pattern; no monitor wiring; no `RedisHealthMonitor` change.** | On the injected path the owner already attached the `'error'` listener (`redisClient.ts:41`), which reports transport faults under `'shared'`. `RedisHealthMonitor.ClientName` is a closed union with no `'stats'` member; the established injected-client pattern (DedupManager docstring) does not report per-op to the monitor. |
| D4 | **Backward-compatible constructor** — keep the URL form. | Legacy callers / tests can still construct `StatsManager(url, …)`. Only the `main.ts` production callsite switches to the injected client. |
| D5 | **No config flag.** | Pure internal resilience fix with no behavior toggle. Nothing for an operator to tune. |

## 4. Architecture

`StatsManager` becomes a client *consumer*, not a client *owner*, exactly like `DedupManager`, `PushedSet`, and `checkedSet`. After this change the crawler subprocess holds **one** Redis connection per crawl (the shared client). StatsManager was the last separate-client holdout flagged at CLAUDE.md:384.

```
            ┌─────────────────────────── sharedRedis (createSharedRedisClient) ───────────┐
heartbeat ──┤ publish crawler:heartbeat (every 2s — keeps socket warm)                    │
DedupManager┤ sAdd / sIsMember / sScan …            (ownsClient=false)                     │
PushedSet   ┤ sAdd …                                 (ownsClient=false)                     │
checkedSet  ┤ sAdd …                                 (ownsClient=false)                     │
StatsManager┤ hIncrBy / hGet / hGetAll / expire / del  (ownsClient=false)  ◄── THIS CHANGE  │
            └──────────────────────────────────────────────────────────────────────────────┘
                 single 'error' listener (owner) → redisMonitor.onError('shared', …)
```

## 5. Component Specs

### 5.1 `StatsManager.ts` — accept an injected client

Constructor signature changes to accept `RedisClientType | string`, mirroring `DedupManager.ts:23-49`.

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
     * connect/disconnect lifecycle — StatsManager does NOT register a second
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
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err) => console.error('Redis Stats Error:', err));
        } else {
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

    // ensureTtl / increment / getValue / checkThreshold / saveStateToDisk /
    // loadStateFromDisk — UNCHANGED.

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

Notes:
- `del(this.key)` still runs on both paths — it removes the per-crawl `stats:{id}` key without touching the shared connection.
- `cleanup()` calls `disconnect()`, which is a no-op on the injected path — so the shared client survives, consistent with `DedupManager.cleanup()`.
- No `ClientName` / monitor change (D3).

### 5.2 `main.ts` — inject the shared client

Single production callsite, `main.ts:545`:

```typescript
// before
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");
// after
context.statsManager = new StatsManager(sharedRedis, id, storagePath || ".");
```

`sharedRedis` is already created and connected at `main.ts:371-375`, well before line 545. The downstream calls are already safe:
- `main.ts:547` `await context.statsManager.connect()` → no-op on the injected path (`ownsClient=false`); the legacy URL path (`ownsClient=true`) still connects. Keep as-is. Do **not** read `connect()` as globally a no-op.
- `main.ts:563-566` dropData path: `cleanup()` (del only) → `connect()` (no-op) → `loadStateFromDisk()`. Correct — the shared client is never disconnected here.
- `main.ts:565` — the comment "StatsManager still owns its own client" becomes false after this change; update it (e.g. "Shared client survives statsManager.cleanup (ownsClient=false), mirrors dedupManager").
- `main.ts:1126` shutdown: `statsManager.cleanup()` (del only) runs **before** `main.ts:1131` `sharedRedis.disconnect()`. Order preserved — no premature close.

### 5.3 `RedisHealthMonitor.ts` — no change

The closed union `ClientName = 'heartbeat' | 'dedup' | 'shared' | 'pushed'` is untouched. StatsManager rides the shared client's existing `'shared'` error listener for transport-fault visibility.

### 5.4 `context.ts` — no change

`context.statsManager` stays typed `StatsManager`; the public method surface is unchanged.

## 6. Data Flow & Invariants

- Redis key `stats:{crawlId}` (hash), field names, and 7-day TTL are unchanged.
- The only difference is the underlying socket: shared (warm) instead of own (idle-reaped).
- Invariant preserved: the shared client is connected once (`main.ts:373`) and disconnected once (`main.ts:1131`); no manager except a legacy URL-owner ever connects/disconnects it.

**Concurrency semantics (accepted, D2):**
- `increment` (`hIncrBy`) and `ensureTtl` (`expire`) are two separate, non-atomic ops — the TTL may briefly lag a write. Acceptable: best-effort, no buffer.
- Cross-manager interference is impossible — keys are namespaced (`stats:{id}` vs `dedup:{id}` vs `pushed:{id}` vs `checked:{id}`), so a `del` on one path never touches another's data.
- Multiplexing four logical users on one socket is the existing, proven DedupManager/PushedSet/checkedSet pattern; node-redis pipelines concurrent commands on a single connection.

## 7. Blast Radius & Impact

- **Files:** `StatsManager.ts`, `StatsManager.test.ts`, `main.ts` (one line), CLAUDE.md. No other consumer — `StatsManager` is instantiated only at `main.ts:545`.
- **Backward compatibility:** the URL constructor form is retained; any non-production caller is unaffected.
- **Improvement beyond the bug:** StatsManager transport faults become visible to `RedisHealthMonitor` under `'shared'` (previously invisible), and per-crawl connection count drops 2 → 1.
- **No external contract change:** webhook payload fields, `/status`, BO — all unchanged.

## 8. Testing Strategy

Remote-only constraint: no live Redis. The injected path needs **no** DI seam — `StatsManager` now accepts a `RedisClientType` directly, so the test constructs `new StatsManager(fakeClient, id, '.')` with a plain fake object. (The `redisClient.ts` `__setCreateClientForTests` seam is for the *legacy* `createClient` path and does **not** apply here.)

Define the fake inline in `StatsManager.test.ts` with the methods StatsManager calls, recording invocations so an incomplete implementation fails cleanly: `hIncrBy(key, field, by) → Promise<number>`, `hGet → Promise<string|null>`, `hGetAll → Promise<Record<string,string>>`, `expire → Promise<boolean>`, `del → Promise<number>`, `isOpen: boolean`, `connect`/`disconnect` as spies, `on(event, fn)` no-op.

Extend `StatsManager.test.ts` (node:test, run via `npm test`):

1. **Injected lifecycle no-ops** — construct with the fake; assert `connect()` and `disconnect()` do **not** invoke the fake's `connect`/`disconnect`; assert `cleanup()` calls the fake's `del(key)` but **not** `disconnect`. *This is the regression guard for the `ownsClient` branch — it fails if a future refactor drops the guard.*
2. **Injected delegation** — `increment("errors", 2)` calls `hIncrBy(key, "errors", 2)` and returns its value; `getValue("errors")` calls `hGet` and parses the result.
3. **Error path (the load-bearing loss claim, §2.2)** — make the fake's `hIncrBy` reject (e.g. a `SocketClosedUnexpectedlyError`); assert `increment()` catches, logs, and returns `0` without rethrowing. Make `hGet` reject; assert `getValue()` returns `0`.
4. **Legacy path (backward compat)** — `new StatsManager("redis://localhost:6379", id, ".")` constructs without throwing (the constructor does not connect — `createClient` is lazy). The legacy `connect()`/`disconnect()` lifecycle is not unit-tested offline (no live Redis; would need a DI seam StatsManager intentionally lacks, D4) and mirrors the proven DedupManager split; the injected no-op tests above are the active regression guard.
5. **Retained** — the existing method-surface and Ch.A counter-name assertions stay green.

Verify: `npm run build` (tsc, 0 errors) + `npm test` (all green).

## 9. Rollout

Low risk, no phased gate. Deploy = rebuild the crawler-service image with the new engine. No env var, no operator step. The existing `redis_diagnose.sh --apply-timeout` idle reap stays in place — it now only ever reaps genuine orphans, since no live client sits idle.

## 10. Deferred Follow-ups

- **(c) Fail-soft increment buffer** — re-apply an increment that hit a dead socket on the next call. Only if real threshold undercount is observed post-deploy. Rejected for now (YAGNI; D2).
- **(b) `pingInterval` on a separate client** — rejected outright (keeps the redundant connection, against the leak-prevention goal).
- **Real Redis-backed integration test** for the deperdition counters — still deferred to staging smoke tests (as noted in `StatsManager.test.ts`); unchanged by this work.

## 11. Tasks (for the plan)

| Task | Files | Verify |
|------|-------|--------|
| **T1** — `StatsManager` injected-client constructor (`ownsClient`) + lifecycle no-ops + tests (injected no-op, delegation, **error-path reject→0**, legacy construct) | `StatsManager.ts`, `StatsManager.test.ts` | `npm run build && npm test` |
| **T2** — wire `sharedRedis` into `StatsManager` at `main.ts:545`; update the stale `main.ts:565` comment | `main.ts` | `npm run build` (tdd-gate stem `main` satisfied by existing `src/tests/test_main.ts`) |
| **T3** — docs: replace CLAUDE.md:384 note + record migration | `apps-microservices/crawler-service/CLAUDE.md` | grep the updated note |

**T3 replacement text.** CLAUDE.md:384 currently reads *"Note: `StatsManager` still opens its own Redis client. Deferred follow-up — see spec § Deferred follow-ups."* — false after this change. Replace with:

> `StatsManager` now consumes the injected shared client (`ownsClient=false`), eliminating the separate idle-reaped connection; per-crawl Redis connection count is **1**. The legacy URL constructor is retained for tests. See `docs/superpowers/specs/2026-06-17-statsmanager-redis-resilience-design.md`.
