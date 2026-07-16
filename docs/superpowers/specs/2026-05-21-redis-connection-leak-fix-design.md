# Redis Connection Leak Fix — Design

**Status:** Draft
**Date:** 2026-05-21
**Author:** Rindra ANDRIANJANAKA
**Scope:** `libs/common-utils` (Python Redis client), `apps-microservices/crawler-service` (Python + Node crawler), `docker-compose.yml`, operator runbook

## 1. Problem

The crawler-service hits two distinct but related Redis failure modes that are cleared by restarting the **client** (not Redis):

- **Node-side**: `Redis Heartbeat Error: [ErrorReply: ERR max number of clients reached]` and `Redis Dedup Error: connect ECONNREFUSED 10.0.1.220:6379`.
- **Python-side**: `Failed to start crawl for domain X: Error 111 connecting to 10.0.1.220:6379. Connection refused` from `crawler_manager.start_crawl` at the `redis_client.set(lock_key, …, nx=True, ex=…)` call.

The errors recur after every restart. Spec-A (`2026-05-21-redis-loss-progress-stall-detection-design.md`) added detection (exit code 5 + `failure_cause=redis_lost`). This spec addresses prevention.

Because restarting the crawler-service drains all its TCP connections and clears the error, the root cause is **client-side connection accumulation**, not Redis instability.

### Root causes (ranked)

1. **OOM-killed Node crawls leave orphan TCP connections** until the Redis server's idle-timeout fires. Redis defaults to `timeout 0` (never reap). OOM relaunch loops compound this fast.
2. **Python pool is unbounded and has no proactive health check** — `redis.from_url()` defaults: `max_connections=50` per replica, `health_check_interval=0`, `socket_keepalive=False`. Stale connections linger in the pool; callers retry, pool grows.
3. **Node opens 2 separate clients per crawl** (heartbeat in `main.ts`, dedup in `DedupManager.ts`). Doubles the per-crawl leak.
4. **No client tagging.** `CLIENT LIST` shows anonymous connections; impossible to attribute leaks to a specific replica or crawl.

## 2. Goals

- Halve the per-crawl Node-side connection footprint (2 → 1).
- Bound the Python-side pool to a defensible cap with proactive health checks.
- Enable server-side reap of orphan connections (the OOM aftermath) without changing the Redis topology.
- Surface attribution: every connection visible in `CLIENT LIST` is named with replica or crawl identity.
- Operator can verify the fix with a single client-side script (no Redis-host shell required).

## 3. Non-goals

- Prometheus gauges for pool stats (deferred — wire only if observation demands).
- `BlockingConnectionPool` / circuit breaker (Approach C — over-engineered for current scale).
- Redis topology change (HA, sentinel, cluster).
- Raising `maxclients` on the Redis server (out of operator scope here; we only set `timeout` and `tcp-keepalive`).
- Changes to existing Spec-A detection (`RedisHealthMonitor` / `ProgressMonitor`) — this spec **prevents** the trigger, does not modify the detector.

## 4. Approach

**Approach A + light B (selected during brainstorm):** tactical 3-pronged client + server fix, plus one diagnostic endpoint + one operator shell script.

Alternatives considered:

- **B (diagnostic-first):** instrument + observe 24-48h before fixing. Rejected because the user is bleeding now; the failure modes are well-understood enough to act.
- **C (aggressive caps + watchdog):** `BlockingConnectionPool`, single client + auto-reconnect on Node, Redis `maxclients` change, `CLIENT KILL TYPE normal IDLE 600` cron, replica watchdog. Rejected as over-engineered: 5+ moving parts to solve a leak that is fixable with 3 surgical edits.

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ crawler-service container                                       │
│                                                                 │
│  ┌───────────────────────┐      ┌────────────────────────────┐  │
│  │ Python FastAPI        │      │ Node child (per crawl)     │  │
│  │                       │      │                            │  │
│  │ cache_service.py      │      │ main.ts                    │  │
│  │  ── (1) bounded pool  │      │  ── (2) SHARED Redis client│  │
│  │      max=20           │      │      heartbeat + dedup     │  │
│  │      keepalive=True   │      │      named: crawl-{id}     │  │
│  │      health=30s       │      │                            │  │
│  │      named: py-{rep}  │      │ DedupManager.ts            │  │
│  │                       │      │  ── accepts injected client│  │
│  │ /admin/redis-debug    │      │                            │  │
│  │  (NEW admin endpoint) │      │                            │  │
│  └───────────┬───────────┘      └────────────┬───────────────┘  │
│              │                               │                  │
└──────────────┼───────────────────────────────┼──────────────────┘
               │ TCP                           │ TCP
               ▼                               ▼
        ┌──────────────────────────────────────────────┐
        │ Redis (10.0.1.220:6379)                      │
        │                                              │
        │  (3) operator runs from any client:          │
        │      CONFIG SET timeout 300                  │
        │      CONFIG SET tcp-keepalive 60             │
        │      CONFIG REWRITE                          │
        │                                              │
        │  Effect: server reaps idle conns after 5min  │
        │  → OOM-orphan conns self-clean               │
        └──────────────────────────────────────────────┘
               ▲
               │ redis-cli (loads .env)
               │
        ┌──────┴───────────────────────────────────────┐
        │ (4) redis_diagnose.sh (NEW)                  │
        │  Mirrors scale_crawlers.sh pattern.          │
        │  Outputs: maxclients, timeout, tcp-keepalive,│
        │  connected_clients, top 20 clients by addr,  │
        │  client name distribution.                   │
        └──────────────────────────────────────────────┘
```

### Boundaries + interfaces

| Component | Responsibility | Interface |
|---|---|---|
| `cache_service.init_redis_pool()` | Build bounded, keepalive-protected client | env reads → `redis.from_url(**kwargs)` |
| `crawler/src/redisClient.ts` (NEW) | Single Redis client factory; named, error-tagged | `createSharedRedisClient(url, {crawlId, monitor}) → RedisClientType` |
| `DedupManager` ctor | Accept injected shared client OR fall back to URL form | `new DedupManager(clientOrUrl, crawlId, ttl, monitor)` |
| `main.ts` heartbeat | Reuse shared client for `PUBLISH` | shared client, different command |
| `app/router/admin.py:/redis-debug` (NEW) | Operator-callable connection snapshot | `GET /admin/redis-debug` → JSON `{info_clients, client_list_top, pool_stats}` |
| `redis_diagnose.sh` (NEW) | Phase-0 client-side diagnostic + optional `--apply-timeout` | reads `.env`, prints config + client stats |
| Redis `CONFIG SET` | Server-side idle reap | one-shot operator command (documented in runbook) |

### Why these boundaries

- Shared Node client extracted to its own module — keeps `main.ts` lean, isolates `createClient` + connect + error wiring, mirrors the Spec-A `browserKill.ts` / Spec-B `cgroupMemory.ts` extraction pattern (avoids `main.ts` top-level execution firing on test import).
- `DedupManager` becomes client-agnostic — receives client by injection. Easier to test (mock injected), enables sharing.
- `/admin/redis-debug` lives in an admin router (not the user-facing `crawler.py` router) — avoids accidental public exposure. Reuses the existing `require_admin` auth pattern.
- `redis_diagnose.sh` is a shell script (not a Python module) — matches `scale_crawlers.sh` operator-tooling style. Run pre-fix to baseline + post-fix to confirm.

## 6. Components

### 6.1 `cache_service.py` — bounded pool

Replace `init_redis_pool` body. Add env-driven knobs with safe defaults.

```python
# libs/common-utils/src/common_utils/redis/cache_service.py

import os
import logging
import redis.asyncio as redis

DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_SOCKET_TIMEOUT_S = 10
DEFAULT_SOCKET_CONNECT_TIMEOUT_S = 5
DEFAULT_HEALTH_CHECK_INTERVAL_S = 30

def _replica_name() -> str:
    # Container hostname is per-replica (docker compose --scale gives unique names).
    return os.getenv("HOSTNAME") or f"pid-{os.getpid()}"

async def _ping_safe(client) -> bool:
    try:
        return await client.ping()
    except Exception:
        return False

async def init_redis_pool():
    global redis_client
    if redis_client and await _ping_safe(redis_client):
        logger.info("Redis pool already initialized and connected.")
        return

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.critical("REDIS_URL not set; caching disabled.")
        redis_client = None
        return

    max_conn = max(1, int(os.getenv("REDIS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS)))
    sock_to = float(os.getenv("REDIS_SOCKET_TIMEOUT_S", DEFAULT_SOCKET_TIMEOUT_S))
    sock_conn_to = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT_S", DEFAULT_SOCKET_CONNECT_TIMEOUT_S))
    health_iv = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL_S", DEFAULT_HEALTH_CHECK_INTERVAL_S))
    client_name = f"crawler-py-{_replica_name()}"

    try:
        logger.info(f"Connecting to Redis at {redis_url.split('@')[-1]} (max_conn={max_conn}, name={client_name})")
        redis_client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=max_conn,
            socket_keepalive=True,
            socket_connect_timeout=sock_conn_to,
            socket_timeout=sock_to,
            health_check_interval=health_iv,
            client_name=client_name,
        )
        await redis_client.ping()
        global _safe_decr_script, _delete_if_terminal_script
        _safe_decr_script = redis_client.register_script(_SAFE_DECR_LUA)
        _delete_if_terminal_script = redis_client.register_script(_DELETE_IF_TERMINAL_LUA)
        logger.info("Redis connected.")
    except redis.RedisError as e:
        logger.warning(f"Redis connect failed: {e}. Caching unavailable.")
        redis_client = None
```

**Why bounded at 20 (not 50):**
- 7 replicas × 20 = 140 Python conns at hard cap.
- Current call patterns are short transactions (SET NX, INCR, GET, SCAN, PUBLISH, EVAL). 20 in-flight per replica is generous.
- If we burst, `redis-py` raises `ConnectionError("Too many connections")` immediately — surfaces in logs, points us at the real consumer, not silently grows.

**Why `_ping_safe`:** the original early-return guard calls `await redis_client.ping()` directly. On Redis unavailable, `ping()` **raises** → the function blows up at the guard and the caller can't recover. Wrap → return False → fall through to fresh init.

### 6.2 Node — `redisClient.ts` (NEW shared client factory)

```typescript
// apps-microservices/crawler-service/crawler/src/redisClient.ts

import { createClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './class/RedisHealthMonitor.js';

export interface SharedRedisClientOpts {
    crawlId: string;
    monitor?: RedisHealthMonitor;
}

/**
 * Single named Redis client for the crawler child process.
 * Both heartbeat publishes and DedupManager operations multiplex on this client.
 *
 * Why single client: each TCP conn to Redis costs a server-side FD. OOM-killed
 * Node processes leave orphan conns until server idle-timeout. Halving the
 * per-crawl conn count (2 → 1) halves the orphan blast radius.
 *
 * Why named: CLIENT LIST attributes conns to a crawl_id for diagnostics.
 * `crawler-node-{crawlId}` is unique per crawl + survives reconnect.
 */
export function createSharedRedisClient(
    redisUrl: string,
    { crawlId, monitor }: SharedRedisClientOpts,
): RedisClientType {
    const client: RedisClientType = createClient({
        url: redisUrl,
        name: `crawler-node-${crawlId}`,
        socket: {
            keepAlive: 30_000,
            connectTimeout: 5_000,
        },
    });
    client.on('error', (err) => {
        console.error('Redis Client Error:', err);
        monitor?.onError('shared', err);
    });
    return client;
}
```

### 6.3 `DedupManager` — inject client

```typescript
// apps-microservices/crawler-service/crawler/src/class/DedupManager.ts (excerpt)

import { createClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './RedisHealthMonitor.js';

export class DedupManager {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private blockedKey: string;
    private ownsClient: boolean;

    constructor(
        clientOrUrl: RedisClientType | string,
        crawlId: string,
        ttlSeconds: number = 7 * 24 * 3600,
        monitor?: RedisHealthMonitor,
    ) {
        if (typeof clientOrUrl === 'string') {
            // Backward-compatible URL form (legacy + tests).
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err) => {
                console.error('Redis Dedup Error:', err);
                this.monitor?.onError('dedup', err);
            });
        } else {
            this.redis = clientOrUrl;
            this.ownsClient = false;
        }
        this.monitor = monitor;
        this.key = `dedup:${crawlId}`;
        this.blockedKey = `blocked_log:${crawlId}`;
        this.ttl = ttlSeconds;
    }

    async connect() {
        if (!this.ownsClient) return;   // shared client connected by owner
        try {
            await this.redis.connect();
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            throw e;
        }
    }

    async disconnect() {
        if (!this.ownsClient) return;   // shared client closed by owner
        if (this.redis.isOpen) {
            try {
                await this.redis.disconnect();
                this.monitor?.onSuccess('dedup');
            } catch (e) {
                this.monitor?.onError('dedup', e);
                throw e;
            }
        }
    }

    // addUrl, isKnown, isKnownBatch, filterNewBlockedBatch, getCount,
    // getAllUrlsIterator, loadFromIterator, cleanup — all unchanged.
    // They call this.redis.xxx, which works identically whether shared or owned.
}
```

`ownsClient` flag preserves backward compat for tests and external callers that still pass a URL.

### 6.4 `main.ts` — wire shared client

```typescript
// apps-microservices/crawler-service/crawler/src/main.ts (excerpt)

import { createSharedRedisClient } from "./redisClient.js";

const sharedRedis = createSharedRedisClient(redisUrl, { crawlId, monitor: redisMonitor });
try {
    await sharedRedis.connect();
    redisMonitor.onSuccess('shared');
} catch (err) {
    console.error('Failed to connect shared Redis client:', err);
    process.exit(5);
}

// Heartbeat — was a separate createClient + connect. Reuse sharedRedis:
const heartbeatTimer = setInterval(async () => {
    try {
        await sharedRedis.publish(`crawler:heartbeat:${crawlId}`, JSON.stringify(payload));
        redisMonitor.onSuccess('shared');
    } catch (e) {
        redisMonitor.onError('shared', e);
        console.error('Failed to send heartbeat:', e);
    }
}, HEARTBEAT_INTERVAL_MS);

// Dedup — pass sharedRedis instead of redisUrl:
const dedup = new DedupManager(sharedRedis, crawlId, undefined, redisMonitor);
// No dedup.connect() needed — shared client already connected.

// gracefulShutdown: close shared client once, after both consumers stopped:
async function gracefulShutdown(reason, exitCode) {
    clearInterval(heartbeatTimer);
    redisMonitor.stop();
    progressMonitor.stop();
    try { await dedup.cleanup(); } catch (e) { /* logged inside */ }
    try {
        if (sharedRedis.isOpen) await sharedRedis.disconnect();
    } catch (e) { console.error('Shared Redis disconnect error:', e); }
    process.exit(exitCode);
}
```

**Net per crawl:** 2 TCP conns → 1 TCP conn. At 7 replicas × 3 crawls = 42 → 21 Node-side conns.

### 6.5 `redis_diagnose.sh` (NEW operator tool)

```bash
#!/bin/bash
# apps-microservices/crawler-service/redis_diagnose.sh
#
# Mirrors scale_crawlers.sh: loads .env, runs redis-cli against external Redis.
# Use BEFORE applying server-side CONFIG SET + AFTER fix deploys to verify.
#
# Usage: ./redis_diagnose.sh [--apply-timeout]
#   --apply-timeout : also runs CONFIG SET timeout 300 + tcp-keepalive 60 + REWRITE

set -e

if ! command -v redis-cli &> /dev/null; then
    echo "ERROR: redis-cli not installed."; exit 1
fi
if [ ! -f .env ]; then echo "ERROR: .env not found."; exit 1; fi
set -o allexport; source .env; set +o allexport
RCLI=(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_SECRET" --no-auth-warning)

echo "=== Redis config ==="
"${RCLI[@]}" CONFIG GET maxclients
"${RCLI[@]}" CONFIG GET timeout
"${RCLI[@]}" CONFIG GET tcp-keepalive
"${RCLI[@]}" CONFIG GET maxmemory

echo "=== Connection stats ==="
"${RCLI[@]}" INFO clients

echo "=== Top 20 clients by addr ==="
"${RCLI[@]}" CLIENT LIST | awk '{print $2, $4}' | sort | uniq -c | sort -rn | head -20

echo "=== Client name distribution ==="
"${RCLI[@]}" CLIENT LIST | grep -oP 'name=\K[^ ]+' | sort | uniq -c | sort -rn | head -20

if [ "$1" = "--apply-timeout" ]; then
    echo "=== Applying server-side idle reap ==="
    "${RCLI[@]}" CONFIG SET timeout 300
    "${RCLI[@]}" CONFIG SET tcp-keepalive 60
    "${RCLI[@]}" CONFIG REWRITE
    echo "Done. New conns will be reaped after 300s idle."
fi
```

### 6.6 `/admin/redis-debug` endpoint

```python
# apps-microservices/crawler-service/app/router/admin.py (NEW or extend existing)

from collections import Counter
from fastapi import APIRouter, Depends, HTTPException
from common_utils.redis.cache_service import redis_client
from app.core.auth import require_admin  # reuse existing pattern

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/redis-debug")
async def redis_debug(_: None = Depends(require_admin)):
    if not redis_client:
        raise HTTPException(503, "Redis not connected")
    try:
        info = await redis_client.info("clients")
        all_clients = await redis_client.client_list()
        return {
            "info_clients": info,
            "total_clients": len(all_clients),
            "client_name_counts": _count_by(all_clients, "name"),
            "client_addr_counts": _count_by(all_clients, "addr"),
            "sample_clients": all_clients[:50],
            "pool_stats": _pool_stats(redis_client),
        }
    except Exception as e:
        raise HTTPException(500, f"redis-debug failed: {e}")

def _count_by(clients, key):
    return Counter(c.get(key, "<unset>") for c in clients).most_common(20)

def _pool_stats(client):
    try:
        pool = client.connection_pool
        return {
            "max_connections": pool.max_connections,
            "created_connections": getattr(pool, "_created_connections", None),
            "available": len(getattr(pool, "_available_connections", [])),
            "in_use": len(getattr(pool, "_in_use_connections", [])),
        }
    except Exception as e:
        return {"error": str(e)}
```

**Why both `redis_diagnose.sh` AND the endpoint:**
- Shell script: server-side global view (every client Redis sees).
- Endpoint: per-replica view (what THIS replica thinks its pool looks like).
- Diff between the two is the leak signature.

## 7. Data flow

### 7.1 Happy path (per crawl)

```
T+0    main.ts: createSharedRedisClient → 1 TCP conn opened (named crawler-node-{id})
T+0    sharedRedis.connect() → CLIENT SETNAME crawler-node-{id} sent
T+0    DedupManager(sharedRedis, ...) → no new conn; reuses sharedRedis
T+0…   Heartbeat publish + dedup sAdd/sIsMember → multiplex on same conn
T+End  gracefulShutdown:
       - dedup.cleanup() → DEL keys (no disconnect; ownsClient=false)
       - sharedRedis.disconnect() → 1 conn FIN-closed
       - process.exit(0)
Result: 1 TCP conn opened + 1 closed per crawl. Net = 0.
```

### 7.2 OOM-kill path (the leak before this spec)

```
T+0    1 conn opened (sharedRedis)
T+OOM  Kernel SIGKILL → process gone instantly. No graceful shutdown.
T+OOM  TCP conn remains half-open on Redis side (SYN sent, FIN never received).
T+OOM+300s  Redis server-side idle timeout fires → conn FIN-closed by server.
Result: orphan reaped 5min after kill. With repeated OOM relaunches in
        cardinality M: peak conns = M, decays as orphans age out.
```

**Versus pre-spec:** 2 orphans per OOM → 1 orphan per OOM (halved). Plus server-side reap (was never).

### 7.3 Redis brief unavailability (network blip)

```
T+0    Redis blips for 8s (e.g., GC pause, network jitter).
T+0    Python pool: in-flight cmd raises ConnectionError. health_check_interval=30s
       discards stale conn → opens fresh. socket_connect_timeout=5s bounds retry.
T+0    Node sharedRedis: 'error' event → monitor.onError('shared'). Client
       auto-reconnects via built-in retry. monitor sees recovering onSuccess
       within REDIS_LOSS_THRESHOLD_MS → no exit.
Result: transient handled. No exit-5 false positive.
```

### 7.4 Sustained Redis loss (existing exit-5 path, preserved)

```
T+0    Redis goes down + stays down.
T+0…60s  monitor.onError fires on every retry. monitor.onSuccess stays cold.
T+60s  RedisHealthMonitor.fire → gracefulShutdown('REDIS_LOST', 5).
T+60s+ε  Python orchestrator: status=failed, failure_cause=redis_lost.
Result: Spec-A behavior unchanged.
```

### 7.5 Pool cap hit (new bounded path)

```
T+0    Python replica under burst: 21st coroutine asks for conn.
       ConnectionPool.get_connection raises ConnectionError("Too many connections").
       Caller surfaces 500 to API client → loud failure.
Result: visible, attributable, fixable by raising REDIS_MAX_CONNECTIONS env var.
```

## 8. Edge cases

| Case | Behavior |
|---|---|
| Redis password rotation | `init_redis_pool` re-init guarded by `_ping_safe`. Failing ping → fresh client built with new env. No double-pool. |
| `from_url` raises on init | `redis_client = None`. Existing `if not redis_client` guards across cache_service make every op a no-op. `/start` returns 500 immediately (same as today). |
| Shared client mid-crawl error | `redis` library auto-reconnects with exponential backoff. Monitor sees onError → onSuccess delta. Existing `RedisHealthMonitor` window applies. |
| Dedup ops error AFTER shutdown | `gracefulShutdown` flips `redisMonitor.stop()` before close → no late-fire of exit-5 on the way out. Already true post-Spec-A. |
| Operator runs `redis_diagnose.sh --apply-timeout` twice | Idempotent. CONFIG SET to same value is no-op. CONFIG REWRITE rewrites redis.conf — also idempotent. |
| `/admin/redis-debug` called during incident with 10k+ clients | `sample_clients[:50]` caps payload. `client_name_counts` + `addr_counts` aggregate the rest. |
| `connection_pool` private attrs renamed in future redis-py | `_pool_stats` wrapped in try/except → returns `{"error": ...}`. Diagnostic-only, non-critical. |
| `REDIS_MAX_CONNECTIONS=0` misconfig | redis-py treats 0 = unlimited (legacy). Clamp via `max(1, int(env))`. |
| Backward-compat callers passing URL to `DedupManager` | `ownsClient=true` branch preserves old behavior. Tests + external callers unaffected. |
| `HOSTNAME` unset (CI / local dev) | Falls back to `pid-{getpid()}`. Names are diagnostic-only, never identifiers in keys. |

## 9. Testing

### 9.1 Unit — Python

`libs/common-utils/tests/test_cache_service.py` (extend or create):

| Test | Asserts |
|---|---|
| `test_init_uses_bounded_pool_defaults` | Monkeypatch `redis.from_url`; assert kwargs include `max_connections=20`, `socket_keepalive=True`, `health_check_interval=30`, `client_name="crawler-py-..."` |
| `test_init_reads_env_overrides` | `REDIS_MAX_CONNECTIONS=5` → from_url got 5 |
| `test_init_clamps_zero_to_one` | `REDIS_MAX_CONNECTIONS=0` → from_url got 1 |
| `test_ping_safe_returns_false_on_exception` | Mock raises; expect False; no propagation |
| `test_init_skips_when_existing_client_pings_ok` | Pre-set client; ping True; from_url not called |
| `test_init_rebuilds_when_existing_client_ping_fails` | Pre-set client raises on ping; from_url called once |

### 9.2 Unit — Node

`crawler/src/tests/redisClient.test.ts` (NEW):

| Test | Asserts |
|---|---|
| `factory passes name option` | Mock `createClient`; assert opts.name = `crawler-node-{id}` |
| `factory passes keepAlive 30000` | opts.socket.keepAlive === 30000 |
| `error handler reports to monitor` | Emit synthetic error → monitor.onError called with `'shared'` |
| `factory tolerates monitor=undefined` | No throw when monitor omitted |

`crawler/src/tests/DedupManager.shared.test.ts` (NEW):

| Test | Asserts |
|---|---|
| `accepts injected client; connect is no-op` | Pass mock RedisClientType; `dedup.connect()` resolves; mock.connect NOT called |
| `accepts injected client; disconnect is no-op` | Pass mock; `dedup.disconnect()` resolves; mock.disconnect NOT called |
| `URL form still owns + connects client` | Pass URL string; mock createClient; dedup.connect() calls mock.connect |
| `addUrl uses injected client` | Mock client.sAdd; `dedup.addUrl` → sAdd called with `dedup:{id}` |

### 9.3 Integration — operator-driven smoke

After deploy:

1. `./redis_diagnose.sh` baseline → record `connected_clients`, `client_name_counts`.
2. Trigger 3 concurrent crawls on test domains.
3. `./redis_diagnose.sh` mid-crawl → expect `crawler-node-{id}` entries = active crawl count (not 2× count).
4. Force-kill one crawler child (`docker exec … kill -9 <pid>`).
5. `./redis_diagnose.sh` immediately + 6min later → expect orphan present, then reaped.
6. `curl http://crawler-service:8503/admin/redis-debug` (with auth) → JSON returns; `pool_stats.in_use` < 20.

### 9.4 No integration test for Redis cap

Out of scope. Setting up Redis with low `maxclients` in CI is brittle. The bounded pool change is verified by unit tests on the `from_url` kwargs.

## 10. Configuration

### 10.1 Python env

| Var | Default | Purpose |
|---|---|---|
| `REDIS_MAX_CONNECTIONS` | 20 | Pool cap per replica |
| `REDIS_SOCKET_TIMEOUT_S` | 10 | Per-command timeout |
| `REDIS_SOCKET_CONNECT_TIMEOUT_S` | 5 | Connect handshake timeout |
| `REDIS_HEALTH_CHECK_INTERVAL_S` | 30 | Proactive ping cadence |

### 10.2 Node (no new vars)

Shared client uses hardcoded `keepAlive: 30_000`, `connectTimeout: 5_000`. Add env knobs only if observation demands.

### 10.3 Server-side (one-shot operator command)

`./redis_diagnose.sh --apply-timeout` applies:

- `timeout 300`
- `tcp-keepalive 60`
- `CONFIG REWRITE` (persists to redis.conf)

### 10.4 `docker-compose.yml` — crawler-service

Add to `environment:` (defaults hold if unset):

```yaml
- REDIS_MAX_CONNECTIONS=${REDIS_MAX_CONNECTIONS:-20}
- REDIS_SOCKET_TIMEOUT_S=${REDIS_SOCKET_TIMEOUT_S:-10}
- REDIS_SOCKET_CONNECT_TIMEOUT_S=${REDIS_SOCKET_CONNECT_TIMEOUT_S:-5}
- REDIS_HEALTH_CHECK_INTERVAL_S=${REDIS_HEALTH_CHECK_INTERVAL_S:-30}
```

## 11. Rollout + observability

### 11.1 Order of operations

1. **Pre-deploy baseline:** operator runs `./redis_diagnose.sh` → record current `maxclients`, `timeout`, `connected_clients`, name distribution.
2. **Apply server-side reap:** `./redis_diagnose.sh --apply-timeout`. Idempotent. No service restart needed.
3. **Deploy code (Python + Node together):** bounded pool + shared Node client + `/admin/redis-debug` endpoint. Single image build.
4. **Post-deploy verification:** rerun `./redis_diagnose.sh`. Expect: `timeout=300`, `tcp-keepalive=60`, conn count drops within 5min as orphans reap. `crawler-node-*` count = active crawls (not 2× crawls).
5. **24h watch:** check `/admin/redis-debug` once per shift. `pool_stats.in_use` should sit well below `max_connections`.

### 11.2 Failure modes during rollout

| Failure | Detection | Action |
|---|---|---|
| Bounded pool too tight | Python logs `redis.exceptions.ConnectionError: Too many connections`. `/start` returns 500. | Bump `REDIS_MAX_CONNECTIONS` env to 40, redeploy. |
| Server-side timeout kills legitimate long-lived conns | `socket_keepalive=True` + `health_check_interval=30` already protect Python clients; Node `keepAlive: 30000` protects Node. If still happening: raise server `timeout` to 600. | Operator: `redis-cli CONFIG SET timeout 600`. |
| Shared client crashes both heartbeat + dedup on single fault | `RedisHealthMonitor` fires exit-5. Sub-optimal but correct (Spec-A already designed for this). | Acceptable. |
| `/admin/redis-debug` auth misconfigured | 401 from internal callers. | Confirm `require_admin` dependency works; fix env. Endpoint is operator-only — no user impact. |

### 11.3 Deferred follow-ups (data-driven)

- Prometheus gauges for `pool.in_use`, `pool.available`, `pool.created`.
- Auto-scale `REDIS_MAX_CONNECTIONS` based on `MAX_CONCURRENT_CRAWLS` × constant.
- Move Node single-client pattern to `libs/` if other Node services adopt it.
- `CONFIG SET maxclients` change on the Redis server.

## 12. File touch summary

```
libs/common-utils/src/common_utils/redis/cache_service.py        MOD  bounded pool + _ping_safe
libs/common-utils/tests/test_cache_service.py                    NEW or MOD  6 unit tests

apps-microservices/crawler-service/crawler/src/redisClient.ts             NEW  shared client factory
apps-microservices/crawler-service/crawler/src/tests/redisClient.test.ts  NEW  4 unit tests
apps-microservices/crawler-service/crawler/src/class/DedupManager.ts      MOD  inject client + ownsClient flag
apps-microservices/crawler-service/crawler/src/tests/DedupManager.shared.test.ts NEW  4 unit tests
apps-microservices/crawler-service/crawler/src/main.ts                    MOD  shared client wiring; replace 2 createClient calls

apps-microservices/crawler-service/app/router/admin.py        NEW or MOD  /admin/redis-debug
apps-microservices/crawler-service/main.py                    MOD  register admin router if new

apps-microservices/crawler-service/redis_diagnose.sh          NEW  client-side diagnostic + --apply-timeout
apps-microservices/crawler-service/CLAUDE.md                  MOD  /admin/redis-debug + redis_diagnose.sh + env vars

docker-compose.yml                                            MOD  4 env passthroughs on crawler-service
```

## 13. References

- `libs/common-utils/src/common_utils/redis/cache_service.py:18-47` — current unbounded `init_redis_pool`.
- `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts:13-23` — current per-crawl second client.
- `apps-microservices/crawler-service/crawler/src/main.ts` — heartbeat block (separate client today).
- `apps-microservices/crawler-service/scale_crawlers.sh` — operator-tooling pattern mirrored by `redis_diagnose.sh`.
- `docs/superpowers/specs/2026-05-21-redis-loss-progress-stall-detection-design.md` — Spec-A (detection; this spec prevents the trigger).

## 14. Open questions

None at spec time. Operator unknown about Redis-side `maxclients` is acceptable — `redis_diagnose.sh` exposes it as part of Phase 0.
