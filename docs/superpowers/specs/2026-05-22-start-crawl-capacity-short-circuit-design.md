# start_crawl Capacity Short-Circuit + Redis Retry — Design

**Status:** Draft
**Date:** 2026-05-22
**Author:** Rindra ANDRIANJANAKA
**Scope:** `apps-microservices/crawler-service/app/core/crawler_manager.py` (`start_crawl` reorder + retry wrap)

## 1. Symptom

Under bursty BO load (every 5min cron tick), the crawler-service log shows ~20 rapid `/start` requests, most rejected with 503 `REPLICA_CAPACITY_EXCEEDED`, plus an occasional 500 `ConnectionRefusedError` from Redis mid-burst.

Excerpt from `crawler-service-4` at 21:48:49-21:49:07:

```
WARNING | Max concurrent crawls for this replica reached. Rejecting job '6397'. Global counter rolled back.
INFO    | POST /start HTTP/1.0 503
... [18 more identical lines for different crawl_ids] ...
ERROR   | Failed to start crawl for domain epcomediterranee.com: Error 111 connecting to 10.0.1.220:6379. Connection refused.
INFO    | POST /start HTTP/1.0 500
... [10 more 503s continue] ...
```

19 rejections + 1 transient 500 in ~18 seconds, on a single replica. Same pattern repeats across all 7 replicas every 5min.

## 2. Root cause

### 2.1 Why the 503 storm

BO's `script_lancer_enqueue_crawling.php` correctly probes `GET /capacity` and checks `running_jobs < max_global_jobs` (L454-466, L574, L580, L658). But the BO probe is **global-level**, while crawler-service rejects at **replica-level** via `MAX_CONCURRENT_CRAWLS=1` per replica.

The flow:

1. BO probes capacity → `running_jobs=4 / max_global_jobs=7` → 3 slots seen as available.
2. BO loop fires 3+ `wget` calls to crawler-service through nginx LB in quick succession (no inter-call delay).
3. nginx round-robin distributes the calls — one lands on a replica that already has its 1 slot occupied.
4. That replica returns 503 `REPLICA_CAPACITY_EXCEEDED`.

BO cannot prevent this — nginx LB hides per-replica state from BO. Even a perfect global-capacity probe still hits saturated single replicas under uneven crawl durations.

### 2.2 Per-rejection Redis cost

Each 503 still costs **7 Redis ops** on the rejecting replica before the function returns. Current `start_crawl` ordering (`crawler_manager.py:347-432`):

| Step | Line | Redis op | Required for? |
|---|---|---|---|
| Build job_data | 356-368 | (none) | always |
| **Lock SET NX** | **374** | **op #1** | always (acquire claim) |
| **State set_json** | **383** | **op #2** | always (observability) |
| Get max_global | 399 | op #3 | global cap check |
| **INCR counter** | **402** | **op #4** | global cap check (atomic) |
| Local cap check | 420-421 | (none — in-memory `self.local_processes`) | replica cap check |
| Rollback decrement | 422→395 | op #5 | only on rejection |
| Rollback del lock | 422→392 | op #6 | only on rejection |
| Rollback del state | 422→393 | op #7 | only on rejection |

**Observation:** the local capacity check (the only one that distinguishes which replica is full) runs AFTER 4 Redis ops. When the replica is at cap, those 4 ops are wasted, then 3 more rollback ops are spent. 7 ops per rejection × 19 rejections × 7 replicas = ~930 Redis ops per BO cron tick on saturated cluster.

### 2.3 Why the transient 500

The 500 at 21:48:56 is `redis.exceptions.ConnectionError` raised on the `SET NX lock_key` call at L374. During the 7-Redis-op storm, the bounded Spec-C pool (`max_connections=20` per process) saturates briefly. A new connection fails (ECONNREFUSED — pool exhausted or transient Redis-side back-pressure).

Each crawl_id where this happens is LOST until the next BO cron tick (5min latency). On a domain with `nb_retry_eci` already at the cap, the failed start counts as another failure → status moves to terminal `failed`.

## 3. Fix

### 3.1 Reorder `start_crawl` — checks before claims

Move both capacity checks BEFORE any Redis write:

```python
# NEW ORDER (proposed)
# A. Local capacity check (in-memory, 0 Redis ops)
if not is_restart:
    active_local = sum(1 for p in self.local_processes.values() if p.returncode is None)
    if active_local >= settings.MAX_CONCURRENT_CRAWLS:
        logger.warning(f"Max concurrent crawls for this replica reached. Rejecting job '{crawl_id}'. No Redis ops performed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(REPLICA_CAP_RETRY_AFTER_S)},
            detail={
                "error_code": "REPLICA_CAPACITY_EXCEEDED",
                "message": "This service instance is at its maximum capacity.",
                "replica_capacity": settings.MAX_CONCURRENT_CRAWLS,
                "rejected_request": {"crawl_id": crawl_id, "domain": domain},
            },
        )

# B. Global capacity READ probe (2 Redis ops, non-mutating)
if not is_restart:
    redis_max_global_str = await _with_retry(cache_service.get_key, CRAWL_MAX_GLOBAL_KEY)
    current_max_global = int(redis_max_global_str) if redis_max_global_str else settings.DEFAULT_MAX_GLOBAL_CRAWLS
    current_running_str = await _with_retry(cache_service.get_key, CRAWL_RUNNING_COUNT_KEY)
    current_running = int(current_running_str) if current_running_str else 0
    if current_running >= current_max_global:
        logger.warning(f"Global capacity probe shows full ({current_running}/{current_max_global}). Rejecting '{crawl_id}'. No mutating Redis ops performed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(GLOBAL_CAP_RETRY_AFTER_S)},
            detail={
                "error_code": "GLOBAL_CAPACITY_EXCEEDED",
                "message": "The service has reached its global concurrency limit.",
                "global_limit": current_max_global,
                "current_running": current_running,
            },
        )

# C. Lock SET NX (op #1 — claim)
# ... (existing code)

# D. State set_json (op #2)
# ... (existing code)

# E. Atomic INCR counter + race-safe rollback (existing INCR-overshoot logic preserved
#    as last-line defense in case A+B were stale)
new_count = await _with_retry(cache_service.increment_key, CRAWL_RUNNING_COUNT_KEY)
if new_count > current_max_global:
    # Race detected: probe said OK but INCR overshot.
    await _rollback_claim(decrement_counter=True)
    raise HTTPException(status_code=503, headers={...}, detail={...})
```

**Net effect on rejection paths:**

| Rejection path | Before (Redis ops) | After (Redis ops) |
|---|---|---|
| Replica-saturated (the actual bursty case) | 7 | **0** |
| Global-saturated | 7 | **2** (read-only probe) |
| Race (probe stale → INCR overshoots) | 7 | 5 (lock + state + INCR + 2 rollback) — same path, less common |

### 3.2 `Retry-After` header

Both 503 paths add `Retry-After: <seconds>` header. Defaults:

- Replica cap: 5s (short — slot turnover is fast)
- Global cap: 15s (longer — needs other replicas to free)

BO doesn't need to consume this immediately. It's operator-visible (`curl -I /start | grep Retry-After`) and enables future BO improvements without another spec.

### 3.3 Redis retry on load-bearing ops

The 4 Redis calls on the accepted path (`SET NX`, `set_json`, `INCR`, `delete_key` in rollbacks) get wrapped with a tight retry helper. New helper in `crawler_manager.py` (module-private):

```python
import asyncio
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

_REDIS_RETRY_ATTEMPTS = 2  # 2 retries = 3 total attempts
_REDIS_RETRY_BACKOFF_MS = 50  # 50ms between retries


async def _with_retry(callable_coro, *args, **kwargs):
    """Run a Redis call with bounded retry on transient connection errors.

    Wraps `cache_service.*` async helpers. On (RedisConnectionError, RedisTimeoutError, OSError)
    retries up to _REDIS_RETRY_ATTEMPTS times with _REDIS_RETRY_BACKOFF_MS ms backoff between
    attempts. Other exceptions propagate immediately (e.g. business-logic ValueError).
    """
    last_exc = None
    for attempt in range(_REDIS_RETRY_ATTEMPTS + 1):
        try:
            return await callable_coro(*args, **kwargs)
        except (RedisConnectionError, RedisTimeoutError, OSError) as e:
            last_exc = e
            if attempt < _REDIS_RETRY_ATTEMPTS:
                await asyncio.sleep(_REDIS_RETRY_BACKOFF_MS / 1000.0)
                logger.warning(
                    f"Redis transient error on attempt {attempt + 1}/{_REDIS_RETRY_ATTEMPTS + 1}: {e}. Retrying."
                )
                continue
            raise last_exc
```

Apply `_with_retry` to:

- `cache_service.redis_client.set(lock_key, ...)` (L374)
- `cache_service.set_json(job_key, ...)` (L383)
- `cache_service.get_key(CRAWL_MAX_GLOBAL_KEY)` (L399 → moved to probe)
- `cache_service.get_key(CRAWL_RUNNING_COUNT_KEY)` (new probe)
- `cache_service.increment_key(CRAWL_RUNNING_COUNT_KEY)` (L402)
- `_rollback_claim` internals (`delete_key`, `safe_decrement_key`)

Worst-case added latency for a single failed-then-succeeded call: 100ms (2 × 50ms backoff). Acceptable for `/start`.

### 3.4 Why this is sufficient (alternatives rejected)

- **Pre-flight `/start` cache** (queue jobs in memory, return 202): defer — large contract change, BO doesn't currently consume 202 semantics.
- **BO-side per-replica routing**: impossible — nginx LB hides replicas.
- **BO-side inter-launch sleep**: slows queue throughput on healthy days; the service-side reorder is strictly better.
- **Increase `MAX_CONCURRENT_CRAWLS` per replica**: trades throughput for resource pressure; orthogonal decision, defer.

## 4. Components

### 4.1 `crawler_manager.py` — module additions

Add 2 module-level constants near the top:

```python
REPLICA_CAP_RETRY_AFTER_S = 5
GLOBAL_CAP_RETRY_AFTER_S = 15
```

Add `_with_retry` async helper (see § 3.3).

### 4.2 `crawler_manager.py` — `start_crawl` body reorder

Insert sections A (local check), B (global probe) BEFORE the existing lock SET NX (L374). The existing global INCR + overshoot rollback (L402-417) stays as the last-line race defense — its rejection arm now becomes a rare path.

Existing `_rollback_claim` helper signature unchanged. All `cache_service.*` callsites in `start_crawl` get wrapped in `_with_retry(...)`.

### 4.3 Test file

New file: `apps-microservices/crawler-service/tests/test_start_crawl_capacity.py`. 5 tests:

1. **`test_replica_saturated_returns_503_with_zero_redis_ops`**
   - Pre-populate `local_processes` to `MAX_CONCURRENT_CRAWLS`.
   - Mock `cache_service.redis_client` such that ANY call raises.
   - Assert: `start_crawl` raises HTTPException(503), `Retry-After=5` header, no Redis op was attempted.

2. **`test_global_saturated_returns_503_with_only_read_probe`**
   - `local_processes` empty; mock `get_key` → returns `running=10, max=10`.
   - Assert: `start_crawl` raises HTTPException(503) `GLOBAL_CAPACITY_EXCEEDED`, `Retry-After=15`, no `SET NX` / `INCR` calls happened.

3. **`test_race_condition_overshoot_rolls_back`**
   - `local_processes` empty; probe returns `running=9, max=10` (acceptable), but `INCR` returns `11` (race — another replica filled in).
   - Assert: `_rollback_claim(decrement_counter=True)` called, HTTPException(503) raised.

4. **`test_with_retry_succeeds_on_second_attempt`**
   - Mock `cache_service.get_key` to raise `RedisConnectionError` on first call, return `"10"` on second.
   - Assert: `_with_retry` returns `"10"`, mock called twice.

5. **`test_with_retry_exhausts_and_raises`**
   - Mock always raises `RedisConnectionError`.
   - Assert: after 3 attempts (1 initial + 2 retries), `_with_retry` raises `RedisConnectionError`.

## 5. Edge cases

| Case | Behavior |
|---|---|
| `is_restart=True` (OOM relaunch) | Bypasses both A and B checks (matches existing behavior). Lock + state writes preserved. Retry wrap still applies to the writes. |
| Stale local_processes (zombie subprocess) | `p.returncode is None` filter excludes dead children. False-positive local saturation only on `defunct` children, which `_monitor_process` should reap. Not worsened by this change. |
| Probe shows space, but mutating INCR overshoots | Existing INCR-then-decrement rollback covers it (§ 3.3, last path). Spec-A behavior preserved as the race-safe backstop. |
| `Retry-After` 5s too short under sustained load | Operator can tune `REPLICA_CAP_RETRY_AFTER_S` constant. Out of scope for env-vars (defer until observed need). |
| Redis is completely down for >100ms | `_with_retry` exhausts → 500 response. Same as today, no regression. |
| BO ignores `Retry-After` header (current behavior) | No effect — header is purely informational until BO consumes it. |

## 6. Rollout

1. Apply changes (1 source file + 1 new test file).
2. Run `cd apps-microservices/crawler-service && python -m pytest tests/test_start_crawl_capacity.py -v`. Expect 5 passed.
3. Run broader suite: `python -m pytest tests/ -x -q --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py`. Expect no new failures.
4. Deploy to one canary replica first (`scale_crawlers.sh` with 1 replica at the target).
5. Trigger BO cron tick. Observe in `/admin/redis-debug`:
   - `client_addr_counts` for the canary should show DROP in connection turnover during BO bursts.
   - `pool_stats.in_use` should stay well below `max_connections=20` even during BO peak.
6. Verify in canary logs:
   - 503 `REPLICA_CAPACITY_EXCEEDED` warnings include "No Redis ops performed" note.
   - 503 responses have `Retry-After: 5` header (`curl -I` against the rejecting endpoint).
   - No `redis.exceptions.ConnectionError` traces during burst.
7. After 1h of canary observation, scale rollout to remaining replicas.

## 7. Files touched

```
apps-microservices/crawler-service/app/core/crawler_manager.py        MOD  reorder start_crawl + _with_retry helper + Retry-After headers
apps-microservices/crawler-service/tests/test_start_crawl_capacity.py NEW  5 unit tests
```

## 8. Deferred follow-ups

- BO-side `Retry-After` header consumption + adaptive backoff.
- BO-side capacity refresh interval tuning (every-3 → every-1).
- `MAX_CONCURRENT_CRAWLS` per-replica raise (capacity-vs-resource tradeoff).
- In-process queue with 202 Accepted contract (large change, defer until A insufficient).
- `_with_retry` extraction to `libs/common-utils` if other services adopt the pattern.

## 9. References

- `apps-microservices/crawler-service/app/core/crawler_manager.py:340-447` — current `start_crawl` flow (the one being reordered).
- `Hellopro/BO/script/chatgpt/script_lancer_enqueue_crawling.php:454-720` — BO caller (capacity probe + loop launching).
- `Hellopro/BO/script/chatgpt/sh_enqueue_scraping_crawling.sh` — cron wrapper (every 5min).
- Spec-C `2026-05-21-redis-connection-leak-fix-design.md` — bounded Spec-C pool (max=20).
- Spec-D `2026-05-21-cache-service-client-name-fix-design.md` — SERVICE_NAME naming.
- Operator log @ 2026-05-21 21:48:49-21:49:07 — 19 503 rejections + 1 transient 500 in 18s on replica 4.
