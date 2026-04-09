# Milvus Global Concurrency Guard — Design Spec

**Date:** 2026-04-09
**Status:** Approved
**Author:** Rindra + Claude

## Problem Statement

The 5 ingestion database services (`di-database-qdrant-service`, `document-database-qdrant-service`, `echange-database-qdrant-service`, `product-database-qdrant-service`, `website-database-qdrant-service`) and the read service (`database-recherche-service`) all hit a self-hosted Milvus instance independently, with no cross-service coordination.

**Current state:**
- 4 out of 5 writer services have **unlimited** RabbitMQ prefetch (no `basic_qos`)
- `document-database-qdrant-service` has prefetch=100, semaphore=100 — still excessive
- Each writer runs **4 replicas** = 20 writer instances with zero concurrency limits
- `database-recherche-service` has its own local `asyncio.Semaphore(2)` for non-HIGH paths, but HIGH priority search has **no rate limiter at all**
- No service is aware of load imposed by other services
- Result: concurrent spikes cause Milvus VM RAM to climb dangerously, degrading all operations

**Three root problems:**
1. No control over how many concurrent operations hit Milvus
2. Services are isolated — each blind to the load the others impose
3. Read path (database-recherche-service) and write path (ingestion services) have no shared visibility

## Constraints & Requirements

- **Search always wins:** Under pressure, ingestion slows down; search latency must stay low
- **Write priorities are configurable:** Product and devis ingestion are higher priority than website/echange/document, but this is adjustable via environment variables
- **Target database:** Self-hosted Milvus on a VM (not Zilliz Cloud, not Qdrant — Qdrant code paths are dead weight)
- **Safe threshold unknown:** The team has never established a safe concurrency limit for the Milvus VM — the solution must be tunable empirically
- **Redis is available:** Already in the stack, used by multiple services

## Approach: Redis-Based Global Semaphore

A shared concurrency coordinator backed by Redis. All services acquire a "slot" from a global pool before hitting Milvus. The pool has a configurable max size with tiered priority.

### Rejected Alternatives

- **Local rate limits only (per-service semaphores):** Blind allocation, no cross-service awareness, fragile tuning. Band-aid.
- **Centralized Milvus proxy:** Major refactor of all 5 writer services, single point of failure, over-engineering for a concurrency control problem.

## Global Concurrency Model

### The Pool

Two tunable parameters, configured via environment variables:

```
MILVUS_GLOBAL_MAX_CONCURRENT = 50   # Total budget, all tiers combined
MILVUS_WRITE_CEILING = 30           # Max slots writers can occupy
```

### Tiered Dynamic Priority

| Tier | Services | Can acquire up to | Blocked when |
|------|----------|-------------------|--------------|
| **Tier 1 — Search** | `database-recherche-service` | `MILVUS_GLOBAL_MAX_CONCURRENT` (50) | Global pool full (50/50) |
| **Tier 2 — High-priority writes** | Configurable (default: product, devis) | `MILVUS_WRITE_CEILING` (30), minus active Tier 3 | Write ceiling reached |
| **Tier 3 — Low-priority writes** | Configurable (default: website, echange, document) | `MILVUS_WRITE_CEILING` minus active Tier 2 | Write ceiling reached, or Tier 2 has waiters |

### How It Works

- **Search idle, writes busy:** Writers fill up to 30 slots. 20 slots remain available. Writers cannot go above 30 regardless.
- **Search active (10 slots), writes busy:** Writers still fill up to 30. Total = 40/50.
- **Search spike (40 slots):** Search occupies 40 — allowed because Tier 1 cap is 50. Writers still hold their existing slots (up to 30), but total could hit 50. New writers wait.
- **Search spike (50 slots):** Search takes the full pool. Writers drain naturally as they finish — no preemption, but no new write slots acquired.
- **Only writers, no search:** Writers max at 30. The remaining 20 are available (not wasted), just not acquirable by writers. The moment search arrives, it gets a slot instantly.
- **Within write ceiling:** Products (Tier 2) has waiters → website (Tier 3) cannot acquire until product waiters are served.

### Why Write Ceiling Instead of Hard Reservation

- No idle/wasted slots — search gets slots instantly because writers are always capped below the max
- Search is still protected — writers can never consume more than the ceiling
- Simpler to reason about — one number (write ceiling) instead of managing reserved vs shared pools
- Also fixes the current bug where HIGH priority search has zero rate limiting — now it draws from the same global pool

## Implementation Architecture

### New Module: `MilvusConcurrencyGuard`

Location: `libs/common-utils/src/common_utils/concurrency/`

```
concurrency/
    __init__.py
    milvus_concurrency_guard.py    # Async guard (for aio_pika and asyncio services)
    milvus_concurrency_guard_sync.py  # Sync wrapper (for pika-based services)
    config.py                       # GuardConfig dataclass
```

### Redis Data Model

| Key | Type | Purpose |
|-----|------|---------|
| `milvus:slots:total` | Integer (INCR/DECR) | Current total active operations across all tiers |
| `milvus:slots:writes` | Integer (INCR/DECR) | Current active write operations (Tier 2 + Tier 3) |
| `milvus:slots:tier2_waiters` | Integer (INCR/DECR) | Count of Tier 2 services currently waiting for a slot. Tier 3 checks this before acquiring. Incremented when Tier 2 enters wait loop, decremented on acquire or timeout. |
| `milvus:slots:lease:{lease_id}` | String with TTL | One key per acquired slot. Value = `{service}:{tier}:{timestamp}`. Auto-expires for crash safety. |

### Class Interface

```python
class MilvusConcurrencyGuard:
    def __init__(self, redis_client, config: GuardConfig):
        """
        config contains:
            global_max: int          # MILVUS_GLOBAL_MAX_CONCURRENT (default 50)
            write_ceiling: int       # MILVUS_WRITE_CEILING (default 30)
            tier: int                # 1=search, 2=high-write, 3=low-write
            service_name: str        # For lease identification and logging
            lease_ttl: int           # Seconds before auto-release (default 60)
            acquire_timeout: int     # Max wait time in seconds (default 30)
            retry_interval: float    # Poll interval in seconds (default 0.5)
        """

    async def acquire(self) -> str:
        """Acquire a slot. Returns lease_id. Raises TimeoutError if acquire_timeout exceeded."""

    async def release(self, lease_id: str):
        """Release a slot by lease_id."""

    async def extend_lease(self, lease_id: str):
        """Extend TTL for long-running operations."""

    @asynccontextmanager
    async def slot(self):
        """Context manager: acquire, yield, release. Handles cleanup on exception."""
```

`MilvusConcurrencyGuardSync` provides the same interface synchronously for pika-based consumers.

### Acquire Logic (Lua Script)

Single Lua script executed atomically in Redis:

```
function ACQUIRE(tier, global_max, write_ceiling):
    total = GET milvus:slots:total (default 0)
    writes = GET milvus:slots:writes (default 0)

    if tier == 1:  # Search
        if total >= global_max → DENY
        INCR milvus:slots:total
        CREATE lease key with TTL
        → GRANT

    if tier == 2 or tier == 3:  # Writers
        if writes >= write_ceiling → DENY
        if total >= global_max → DENY
        if tier == 3:
            if tier2_waiters > 0 → DENY
        INCR milvus:slots:total
        INCR milvus:slots:writes
        CREATE lease key with TTL
        → GRANT
```

### Release Logic (Lua Script)

```
function RELEASE(lease_id, tier):
    if lease key exists:
        DELETE lease key
        DECR milvus:slots:total
        if tier == 2 or tier == 3:
            DECR milvus:slots:writes
```

### Crash Safety

- Each lease gets a Redis key with TTL (default 60s)
- Long Milvus operations call `extend_lease()` periodically via background task
- If a service crashes, its lease keys expire → counters become stale
- Background correction task (every 30s): counts actual lease keys vs counter values. If divergent, corrects counters.

### Graceful Degradation

If Redis is unavailable:
- Guard falls back to a local semaphore with conservative limit (default 5 per instance)
- Logs warning: "Redis unavailable — falling back to local concurrency limit"
- Periodically retries Redis connection
- When Redis recovers, seamlessly switches back to global coordination

## Integration Points

### Writer Services (5 services)

**Change 1: Add `basic_qos` to all consumers**

Local safety net — even if Redis is temporarily unavailable:

| Service | Current prefetch | New prefetch |
|---------|-----------------|--------------|
| di-database-qdrant-service | Unlimited | 10 |
| echange-database-qdrant-service | Unlimited | 10 |
| product-database-qdrant-service | Unlimited | 10 |
| website-database-qdrant-service | Unlimited | 10 |
| document-database-qdrant-service | 100 | 10 |

With 4 replicas per service, max in-flight messages per service = 40.

**Change 2: Wrap Milvus CRUD calls with guard**

In each service's `processor.py`, wrap Milvus CRUD calls with the guard.

**Sync services** (di, echange, product, website — use pika/blocking):
```python
# Uses MilvusConcurrencyGuardSync
with concurrency_guard.slot():
    result = milvus_crud.insert_produits(data)
```

**Async service** (document — uses aio_pika):
```python
# Uses MilvusConcurrencyGuard (async)
async with concurrency_guard.slot():
    result = milvus_crud.insert_document(data)
```

Guard initialized once at service startup in `main.py`.

**New infrastructure dependency:** The 5 writer services do not currently depend on Redis. This change adds `REDIS_URL` as a required environment variable for all writer services. The graceful degradation fallback (local semaphore) ensures services still function if Redis is temporarily unavailable.

**Default tier assignments:**

| Service | Tier | Rationale |
|---------|------|-----------|
| product-database-qdrant-service | 2 (high write) | Core business entity |
| di-database-qdrant-service | 2 (high write) | Directly tied to revenue |
| echange-database-qdrant-service | 3 (low write) | Can tolerate delay |
| website-database-qdrant-service | 3 (low write) | Crawl data not time-sensitive |
| document-database-qdrant-service | 3 (low write) | Attachment processing can wait |

Configurable per service via `MILVUS_CONCURRENCY_TIER` env var.

### database-recherche-service (Read Path)

**Change 1:** Replace local `_zilliz_rate_limiter` (`asyncio.Semaphore(2)`) with Tier 1 global guard. Both HIGH and non-HIGH paths use the same guard.

**Change 2:** Acquire per batch execution, not per incoming gRPC request. Since batching collapses N requests into 1 Milvus call, the guard wraps `_process_queue_batch()`:

```python
async with self._concurrency_guard.slot():
    result = await loop.run_in_executor(executor, _sync_search)
```

16 batched search requests = 1 slot acquired = 1 Milvus call.

### docker-compose.yml Configuration

New environment variables for all 6 services:

```yaml
# Shared
- MILVUS_GLOBAL_MAX_CONCURRENT=50
- MILVUS_WRITE_CEILING=30
- MILVUS_CONCURRENCY_LEASE_TTL=60
- MILVUS_CONCURRENCY_ACQUIRE_TIMEOUT=30
- REDIS_URL=redis://:${REDIS_SECRET}@${REDIS_HOST}:${REDIS_PORT}

# Per-service
- MILVUS_CONCURRENCY_TIER=2  # or 3
```

## Observability

### Prometheus Metrics

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `milvus_guard_slots_active` | Gauge | `tier`, `service` | Current slots in use |
| `milvus_guard_slots_max` | Gauge | — | Current global max value |
| `milvus_guard_write_ceiling` | Gauge | — | Current write ceiling value |
| `milvus_guard_acquire_duration_seconds` | Histogram | `tier`, `service` | Wait time for slot acquisition |
| `milvus_guard_acquire_timeouts_total` | Counter | `tier`, `service` | Acquire failures — pool too small |
| `milvus_guard_lease_expirations_total` | Counter | `service` | Crash-recovery events |
| `milvus_guard_fallback_active` | Gauge | `service` | 1 if Redis down, local fallback active |

### Tuning Workflow

1. **Start conservative:** `MILVUS_GLOBAL_MAX_CONCURRENT=30`, `MILVUS_WRITE_CEILING=20`
2. **Monitor two signals:**
   - RAM climbing → lower the values
   - `acquire_timeouts_total` increasing → pool too small, raise if RAM allows
   - `acquire_duration_seconds` p95 > 5s for Tier 1 → lower write ceiling
3. **Adjust via env vars** — no code change, just docker-compose restart

### Grafana Dashboard

Single panel: stacked area chart of slots by tier + horizontal threshold lines + Milvus VM RAM overlay.

### Structured Logging

| Event | Level | Content |
|-------|-------|---------|
| Slot acquired | DEBUG | service, tier, lease_id, wait_time_ms, active_slots |
| Slot released | DEBUG | service, tier, lease_id, held_duration_ms |
| Acquire timeout | WARN | service, tier, waited_seconds, active_slots, write_slots |
| Redis fallback activated | WARN | service, fallback_limit |
| Redis recovered | INFO | service |
| Counter correction | WARN | expected, actual, corrected_by |

## Testing Strategy

### Unit Tests (`libs/common-utils/tests/test_milvus_concurrency_guard.py`)

| Test | Validates |
|------|-----------|
| `test_acquire_release_basic` | Acquire increments, release decrements |
| `test_tier1_not_blocked_by_writers` | Search acquires when write ceiling is full |
| `test_writers_blocked_at_ceiling` | Tier 2/3 denied at write ceiling |
| `test_tier3_blocked_when_tier2_waiting` | Low-priority yields to high-priority |
| `test_global_max_blocks_all_tiers` | Search denied at global max |
| `test_acquire_timeout` | TimeoutError after deadline |
| `test_lease_expiry_releases_slot` | Crash simulation — lease expires, counters corrected |
| `test_counter_correction` | Background task fixes drift |
| `test_lua_script_atomicity` | Two concurrent acquires on last slot — only one wins |
| `test_redis_fallback` | Redis down → local semaphore activates |
| `test_redis_recovery` | Redis back → switches to global |
| `test_context_manager_releases_on_exception` | slot() releases on Milvus exception |
| `test_sync_wrapper` | Sync wrapper works identically for pika consumers |

### Integration Tests

Redis-only (no Milvus needed):
- Simulate 6 services with different tiers under contention
- Verify tier priorities respected
- Verify counter accuracy after 1000 rapid acquire/release cycles
- Verify lease expiry under simulated crashes

### Service-Level Tests

Each writer service: mock Redis + Milvus, verify:
- `insertion_data()` acquires slot before CRUD call
- Slot released on CRUD failure
- `TimeoutError` treated as transient (nacked to retry queue, not DLQ)