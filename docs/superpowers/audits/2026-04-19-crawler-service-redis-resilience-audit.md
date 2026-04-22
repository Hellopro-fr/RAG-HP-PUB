# Crawler-service Redis Resilience Audit

**Date:** 2026-04-19
**Scope:** Behavior of `crawler-service` (both Python orchestrator and Node.js crawler engine) when Redis is unavailable — at startup, mid-operation, and during shutdown.
**Status:** Reference audit only. Each finding is a candidate for a future brainstorming session; no implementation has been performed based on this document.

## How to Read This

This is a **punch list**, not a design. Each finding has:
- Location (file + approximate line range)
- What goes wrong when Redis is unavailable
- Why it's bad (user-visible or operational consequence)
- A severity tag (CRITICAL / HIGH / MEDIUM / LOW)
- A short hint on the remediation direction — not a spec

**CRITICAL** = data loss, silent correctness failure, cascade failure, or unbounded resource consumption.
**HIGH** = user-visible failure mode returns confusing signal (500 instead of 503, generic exit code instead of specific) or observable degradation of a key feature.
**MEDIUM** = feature quietly degrades without visible error.
**LOW** = cosmetic or minor operational inconvenience.

## Executive Summary

- **9 CRITICAL findings** (5 Python, 4 Node.js): capacity bypass, heartbeat silent failure (kills active crawls + loses data), reconciliation counter reset, circuit breaker silent disable, shutdown data loss
- **5 HIGH findings**: pipeline crash as 500, disk recovery bypassed, webhook callback loss, dedup returns-true-on-error, no Redis-specific exit code
- **10 MEDIUM/LOW findings**: structured logging gaps, batch-op silent defaults, startup degraded mode, no circuit breaker, shutdown timeout missing

### Recurring anti-patterns

1. **Silent degradation is the default** — almost every Redis call site catches exceptions and returns a "safe" default (`0`, `[]`, `True`) that masks the real problem instead of surfacing it.
2. **No Redis-specific error surface** — HTTP 500s instead of 503s; exit code 1 instead of a distinct code the orchestrator can route on.
3. **No circuit breaker or structured backoff** — each request/tick keeps trying during a full outage.
4. **Startup doesn't fail fast on either side** — service appears "up" in degraded mode, masking an unusable state.

### Recommended fix ordering

When specs are written for individual fixes, this is the suggested priority (highest-risk first):

1. **Heartbeat failure handling** (Python #2 + Node.js #1) — these are paired; fixing one without the other leaves active crawls exposed to SIGKILL + data loss.
2. **Capacity bypass** (Python #1) — silent correctness failure; fixable in a narrow one-line change but has outsized impact.
3. **Graceful shutdown data loss** (Node.js #4) — URLs crawled during the session are currently lost if Redis is down at shutdown.
4. **Reconciliation counter reset** (Python #3) — causes over-concurrency cascades on next requests.
5. **Circuit breaker silent disable** (Node.js #3) — lets broken sites continue consuming crawler capacity.
6. **Manager startup validation** (Node.js #2) — establishes the pattern for the rest of the Node.js fixes.
7. Remaining HIGH items in small batches.
8. MEDIUM/LOW items can be addressed opportunistically when related code is being touched.

---

## Python Side (crawler-service)

### CRITICAL — P-1. Capacity check bypassed when Redis is down

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~198` in `start_crawl`.
- **What happens:** `cache_service.increment_key(CRAWL_RUNNING_COUNT_KEY)` returns `0` on error (per [libs/common-utils/.../cache_service.py:~144](libs/common-utils/src/common_utils/redis/cache_service.py)). The subsequent check `if new_count > current_max_global` is always `False` when `new_count == 0`, so the capacity guard passes.
- **Why it's bad:** Silent correctness failure. Unlimited crawls are admitted while Redis is down. The counter remains corrupted even after Redis recovers (every new admit is also 0-returning, but the running crawls still hold real slots).
- **Remediation hint:** Distinguish "increment failed" from "increment returned 0". Either change `increment_key` to raise on error or return `None` on error, and treat None as a 503 in `start_crawl` via `_rollback_claim`.

### CRITICAL — P-2. Heartbeat silent failure kills active crawls

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~759-776` in `_monitor_process` heartbeat loop.
- **What happens:** After 2 failed retries writing `last_heartbeat` to Redis, the loop logs the error and continues without updating Redis or the lock TTL. Reconciliation (running on any replica with Redis access) detects `last_heartbeat` stale after `STALE_JOB_THRESHOLD_REMOTE = 600s`, marks job failed, and fires the failure webhook. But the LOCAL `_monitor_process` is still running — when the Node.js process eventually exits, the normal completion path fires a second webhook.
- **Why it's bad:** Active crawl is terminated mid-run from the reconciliation side. If Redis comes back mid-crawl, two webhooks fire for the same crawl. Counter drift accumulates.
- **Remediation hint:** After N consecutive heartbeat failures, escalate: kill the local Node.js process (so `_monitor_process` exits naturally), OR suspend the crawl until Redis recovers, OR exit the process with a dedicated exit code. Decision depends on whether we want "Redis down = all crawls pause" or "Redis down = all crawls fail fast".

### CRITICAL — P-3. Reconciliation counter reset on scan failure

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~1876` in `_reconcile_locked` + `libs/common-utils/.../cache_service.py:~126-134` in `scan_keys_by_prefix`.
- **What happens:** `scan_keys_by_prefix` catches exceptions and returns `[]` (empty list) instead of raising. Reconciliation reads the empty list, concludes "no jobs", and resets `CRAWL_RUNNING_COUNT_KEY` to 0. Local crawls keep running and holding slots; next `/start` requests see counter=0 and admit up to `max_global_crawls`.
- **Why it's bad:** Over-concurrency. Multiplied resource consumption. Can cascade to OOM on constrained hosts.
- **Remediation hint:** `scan_keys_by_prefix` should return `None` (or raise) on error; reconciliation should treat that distinctly from "no jobs" and abort the cycle without resetting the counter.

### CRITICAL — P-4. Unhandled `pipeline.execute()` crash

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~999-1002` in `get_all_statuses`.
- **What happens:** Direct `cache_service.redis_client.pipeline()` with no `try/except` or None-check. If `redis_client is None` or Redis is down mid-call, raises and returns HTTP 500 with a generic message.
- **Why it's bad:** Status endpoint appears broken (500) instead of returning a clear "Redis unavailable" 503 that clients can backoff on.
- **Remediation hint:** Null-check `redis_client`, wrap the block in `try/except RedisError`, return 503 with `{"error_code": "REDIS_UNAVAILABLE"}`.

### CRITICAL — P-5. Pub/Sub `_publish_update` failures swallowed

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~114-127` in `_publish_update` + ~20 call sites throughout the module.
- **What happens:** Every status transition (`running`, `finished`, `failed`, `stopping`, `archived`, `restarting_oom`) calls `_publish_update`. On Redis error, the method catches the exception and logs it. No event delivery, no retry, no persistent queue.
- **Why it's bad:** Any subscriber relying on pub/sub to track status (dashboards, real-time monitoring, webhook triggers) silently misses events. Reconciling later requires a full poll.
- **Remediation hint:** Decide whether pub/sub is "best-effort telemetry" or a load-bearing integration. If load-bearing, persist missed events in Redis list (which itself may be down — catch-22) or on disk, and replay on recovery. If best-effort, add a structured log + Prometheus metric so the outage is visible at least.

### HIGH — P-6. `get_job_or_recover` can't fall back to disk when Redis is down

- **Location:** `apps-microservices/crawler-service/app/router/crawler.py:~23-117` (FastAPI dependency).
- **What happens:** `await cache_service.get_json(job_key)` raises `ConnectionError`; the dependency has no `try/except`, so FastAPI converts to HTTP 500. The disk-based recovery path (lines ~37-117) is never reached.
- **Why it's bad:** Defeats the whole purpose of the disk recovery fallback. Users can't query job status when they need it most (during a Redis outage).
- **Remediation hint:** Wrap the Redis read in `try/except ConnectionError`; on failure, log and fall through to the existing disk recovery logic.

### HIGH — P-7. `/capacity` endpoint crashes when Redis disconnects mid-request

- **Location:** `apps-microservices/crawler-service/app/router/crawler.py:~133-162` in `get_capacity`.
- **What happens:** The initial `if not cache_service.redis_client` check handles the "Redis was never connected" case. But if Redis disconnects after that check and the subsequent `get_key` call raises, the request returns 500.
- **Why it's bad:** Load balancer / schedulers see intermittent 500s instead of the expected 503 signal.
- **Remediation hint:** Single `try/except RedisError` around the whole block; return 503 on any failure.

### HIGH — P-8. Failed webhook callbacks are lost if Redis is ALSO down

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~513-526` in `_store_failed_callback`.
- **What happens:** When a webhook delivery fails after retries, the failure record is pushed to a Redis list for manual replay. If Redis is also down, `rpush` raises, the exception is caught, and logged — but the entry is lost.
- **Why it's bad:** Double failure (webhook down + Redis down) silently eats notifications. No manual replay possible.
- **Remediation hint:** Disk-backed fallback queue. On failed `rpush`, write to a local append-only log; on startup, drain the log back into Redis.

### MEDIUM — P-9. Reconciliation leader election has no local fallback

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~1843-1864` in `reconcile_jobs`.
- **What happens:** `SET NX reconcile_leader_lock` fails when Redis is down. The `try/except` around the lock release is defensive but doesn't handle the initial acquire failure — the function silently skips reconciliation. All replicas simultaneously "aren't leader", so reconciliation never runs.
- **Why it's bad:** Counter drift continues unchecked during Redis outages.
- **Remediation hint:** Explicit handling of `SET NX` failure: if Redis is down, either skip with a structured log or attempt a local-only reconciliation (won't catch other replicas' state, but will keep this replica's state correct).

### MEDIUM — P-10. `/pending-callbacks` crashes on Redis failure

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~1815-1828` + `app/router/crawler.py` (webhook inspector endpoints).
- **What happens:** `lrange` has no error handling; raised exception becomes a 500.
- **Why it's bad:** Operators trying to inspect failed callbacks during an outage get a 500 instead of a graceful "unavailable".
- **Remediation hint:** Same pattern as P-6/P-7.

### MEDIUM — P-11. Stale-detection can kill healthy processes under intermittent Redis latency

- **Location:** `apps-microservices/crawler-service/app/core/crawler_manager.py:~1950-1978` (stale detection in `_reconcile_locked`).
- **What happens:** Slow Redis writes cause `last_heartbeat` to lag. After the stale threshold (600s remote), reconciliation kills the process. The existing `local_processes` override mitigates this on the OWNING replica, but another replica running reconciliation will kill via the cross-replica path.
- **Why it's bad:** Wrongfully terminates healthy crawls during Redis flaps. Data loss.
- **Remediation hint:** Require N consecutive reconciliation cycles confirming staleness before killing. Alternatively, require a successful Redis write in the same cycle before declaring staleness.

### MEDIUM — P-12. Shutdown has no Redis close timeout

- **Location:** `apps-microservices/crawler-service/main.py:~173-175` in `shutdown_event`.
- **What happens:** `await close_redis_pool()` can block indefinitely if Redis is hanging. Docker's stop_grace_period (30s per our recent fix) elapses and SIGKILL fires before the Python shutdown handler completes.
- **Why it's bad:** Loses the graceful shutdown webhooks we recently added (see webhook idempotency spec).
- **Remediation hint:** Wrap in `asyncio.wait_for(close_redis_pool(), timeout=5)`; fallback to `connection_pool.disconnect()` on timeout.

### LOW — P-13. Startup doesn't fail fast

- **Location:** `libs/common-utils/src/common_utils/redis/cache_service.py:~20-47` in `init_redis_pool`.
- **What happens:** Connection failure logs a warning and sets `redis_client = None`. Service reports healthy to Docker/K8s but the first request will hit the failures listed above.
- **Why it's bad:** Masks the real problem. The service looks "up" in orchestrator health checks but isn't functional.
- **Remediation hint:** Either raise on connection failure (fail fast) or add a `/healthz` endpoint that checks Redis and returns 503 if unhealthy. Consider env flag `REDIS_REQUIRED_AT_STARTUP=true` so environments with delayed Redis startup can still boot.

### LOW — P-14. No circuit breaker or backoff

- **Location:** All Redis call sites.
- **What happens:** Every request keeps trying Redis individually during an outage, piling up async tasks, increasing pressure on whatever comes back first when Redis recovers.
- **Remediation hint:** Wrap Redis client in a circuit breaker (e.g., open after 5 consecutive failures; half-open retry every 30s; close after 1 success). Reject calls with a cached "Redis unavailable" response while open.

### LOW — P-15. No structured logging / metrics for Redis operations

- **Location:** `libs/common-utils/.../cache_service.py` + all call sites.
- **What happens:** Logs are free-text. No latency distribution, no per-operation error rate, no cache hit ratio.
- **Remediation hint:** Add structured fields (`operation`, `key_prefix`, `duration_ms`, `status`) to each log line. Optionally export Prometheus counters.

---

## Node.js Side (crawler engine)

### CRITICAL — N-1. Heartbeat silent failure, paired with Python P-2

- **Location:** `apps-microservices/crawler-service/crawler/src/main.ts:~370-484` (heartbeat publish loop).
- **What happens:** `redisClient.publish('crawler:heartbeat', ...)` fails every 2 seconds; exception caught and logged. The heartbeat interval keeps running but emits nothing. The Python side (P-2) sees no heartbeat and eventually marks the job stale → SIGKILL → mid-crawl data loss.
- **Why it's bad:** CRITICAL data loss. The Node.js process has no idea Python is about to kill it.
- **Remediation hint:** Paired with P-2. After N consecutive heartbeat publish failures, exit with a dedicated exit code (e.g., `5` = "startup Redis failure", `6` = "mid-crawl Redis failure"). Python maps these to specific webhook messages.

### CRITICAL — N-2. Manager startup has no try/catch

- **Location:** `apps-microservices/crawler-service/crawler/src/main.ts:~545-546`.
- **What happens:** `await context.dedupManager.connect()` and `await context.statsManager.connect()` are awaited without surrounding `try/catch`. If Redis is down, exceptions propagate and crash the Node.js process with generic non-zero exit code (typically `1`).
- **Why it's bad:** Python can't distinguish a Redis failure from a TypeScript bug or missing arg. The crawl webhook reports generic failure.
- **Remediation hint:** Wrap both `connect()` calls in a `try/catch`; on failure, log clearly and `process.exit(5)` for a Redis-specific code.

### CRITICAL — N-3. Circuit breaker silently disabled when StatsManager returns 0

- **Location:** `apps-microservices/crawler-service/crawler/src/class/StatsManager.ts:~41-60` (`increment` and `getValue`) + `src/routes.ts:~244-295` (circuit breaker evaluation).
- **What happens:** `getValue` catches the Redis error and returns `0`. The circuit breaker then computes `errorRate = 0 / 0 = NaN` (or `0`), which is not `> maxErrorRate`. No circuit breaker trigger. The crawl continues unabated even on sites emitting 100% errors.
- **Why it's bad:** A broken site can consume unlimited crawl capacity when Redis is down. Defeats the circuit breaker entirely.
- **Remediation hint:** StatsManager should raise or return `null`/`undefined` on error; the circuit breaker should treat "stats unavailable" as a distinct condition (conservatively: abort the crawl, OR maintain a local in-memory stats cache that persists across the session).

### CRITICAL — N-4. Graceful shutdown data loss on SSCAN failure

- **Location:** `apps-microservices/crawler-service/crawler/src/main.ts:~964-981` (`gracefulShutdown`) + `DedupManager.getAllUrlsIterator` (which calls SSCAN).
- **What happens:** At shutdown, the crawler iterates all crawled URLs via Redis SSCAN and persists them to disk (`updateUrlsCrawledStreaming`). If Redis is down, SSCAN raises → exception caught in DedupManager → empty iterator → **no URLs persisted**.
- **Why it's bad:** Complete data loss for the current session. All crawled URLs disappear.
- **Remediation hint:** Maintain a local in-memory mirror of the URL set during the crawl (dedup already emits per-URL SADD, we could shadow-track). On shutdown, if Redis is unavailable, fall back to the in-memory mirror.

### HIGH — N-5. DedupManager returns `true` on error

- **Location:** `apps-microservices/crawler-service/crawler/src/class/DedupManager.ts:~41-50` in `addUrl`.
- **What happens:** On Redis error, `addUrl` catches the exception and returns `true` (meaning "URL is new, process it"). Same URL gets enqueued multiple times.
- **Why it's bad:** Duplicates inflate the crawled dataset and waste capacity. Stats diverge from reality.
- **Remediation hint:** Decide policy: raise and let the page fail (stricter, risk of cascading failures), OR track a local in-memory set as fallback (softer, small memory overhead).

### HIGH — N-6. No Redis-specific exit code

- **Location:** All Node.js exit paths.
- **What happens:** Current exit codes are `0` (success), `2` (partial), `3` (OOM), `4` (update no data), `1` (generic). There's no distinct code for "Redis was unavailable." Python treats all non-mapped non-zero codes as generic failure and sends the same webhook message.
- **Why it's bad:** Operators can't tell from the failure webhook whether the crawl failed because the site was broken or because Redis went down.
- **Remediation hint:** Add code `5` for "Redis unavailable at startup" and `6` for "Redis failed mid-crawl". Update Python's `_send_failure_webhook` exit-code → error-message mapping (see `crawler_manager.py:~575` — the existing `if exit_code == 3: error_message = "Out Of Memory"` pattern).

### MEDIUM — N-7. Batch dedup operations return empty/default on error

- **Location:** `DedupManager.ts:~67-85` (`isKnownBatch`) and `~93-122` (`filterNewBlockedBatch`).
- **What happens:** On error, returns empty Set or treats all URLs as new. Batch pre-filtering before `enqueueLinks` fails open.
- **Remediation hint:** Same treatment as N-5: decide policy and make it explicit.

### MEDIUM — N-8. Blocked URL log spam on Redis error

- **Location:** `src/routes.ts:~776-792`.
- **What happens:** `filterNewBlockedBatch` catches error and returns input unchanged — every blocked URL gets logged on every page.
- **Why it's bad:** Log spam (not functional).
- **Remediation hint:** Local in-memory fallback cache keyed by URL.

### MEDIUM — N-9. StatsManager disk persistence unreliable

- **Location:** `StatsManager.ts:~78-85` in `saveStateToDisk`.
- **What happens:** On Redis HGETALL failure, logs and returns — `update_stats.json` is not updated. Resume starts from stale or zero state.
- **Remediation hint:** If Redis is unavailable at shutdown, write local in-memory counters (tracked alongside the Redis writes during the session) to disk instead.

### LOW — N-10. `UrlConsolidator` has no try/catch on SADD in phases 1-3

- **Location:** `src/class/UrlConsolidator.ts` — phase loops in `consolidate`.
- **What happens:** SADD failure propagates out of `consolidate`, crashing the crawler with unhandled exception. Used only at startup of update-mode crawls.
- **Why it's bad:** Update-mode startup fails with opaque error.
- **Remediation hint:** Wrap phase loops; on Redis failure, return empty iterator (triggers existing exit code 4 "update no data") or exit with the new Redis-specific code from N-6.

---

## Cross-Cutting: Coordination Between Sides

### C-1. Python and Node.js don't coordinate on "Redis is down"

Currently each side handles Redis failure independently. Ideal behavior:

- Python's `/start` should refuse to spawn a crawler if Redis is down (pre-flight check).
- Node.js should fail fast if Redis is unreachable at startup (see N-2), AND should communicate the specific failure mode via exit code (see N-6).
- Python's `_monitor_process` should recognize the Redis-specific exit codes from Node.js and treat them differently from generic failures (e.g., don't retry at the scheduler level, surface clearly in the webhook).

### C-2. No health check considers Redis

Neither side exposes a `/healthz` endpoint that actually pings Redis. Docker/K8s liveness probes return healthy even when the service is non-functional.

**Remediation hint:** Add `/healthz` (unauthenticated, returns 200 if Redis `PING` succeeds, 503 otherwise). Configure Docker healthcheck to use it.

---

## Testing Strategy (for future fixes)

When writing specs for each fix, tests should cover:

- **At startup**: Redis unreachable → expected behavior (fail fast with clear exit code, or degraded mode with structured log)
- **Mid-operation**: Redis becomes unavailable → expected behavior (retry / circuit break / fail)
- **Recovery**: Redis comes back → state re-syncs correctly, no duplicate work
- **Latency spike**: Redis is slow (not down) → timeouts trigger appropriately without false staleness

A shared Docker Compose profile with a `toxiproxy` or `iptables`-based network blocker between the service and Redis would let integration tests reliably simulate outages.

---

## Appendix: Quick Reproduction Steps (manual testing)

To observe each failure mode manually:

1. Start the stack normally: `docker compose up -d crawler-service`
2. Trigger a crawl via `/start` to confirm baseline
3. Kill Redis: `docker compose stop redis` (or block network between crawler and Redis)
4. Observe behavior for each finding above:
   - Try `/start` → observe whether capacity check still admits (P-1)
   - Wait 10+ minutes → observe reconciliation behavior (P-3, P-11)
   - Check logs for heartbeat failures (P-2, N-1)
   - Check `/capacity` and `/status` → observe 500 vs 503 (P-4, P-7)
5. Restart Redis: `docker compose start redis`
6. Observe recovery: counter drift, orphaned jobs, missing pub/sub events

## Next Steps

Each finding above is a candidate for a dedicated brainstorming → design → implementation cycle. Recommended ordering is in the Executive Summary. The fixes are **not** one giant spec — they have distinct trade-offs (fail-fast vs degraded mode, local fallback vs abort, specific exit codes vs generic) that deserve individual discussion.
