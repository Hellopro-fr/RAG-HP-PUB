# Milvus Global Concurrency Guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Redis-backed global concurrency guard so all services that hit Milvus share a single, tiered slot pool — preventing RAM overload on the Milvus VM.

**Architecture:** A `MilvusConcurrencyGuard` module in `libs/common-utils` uses Redis Lua scripts to atomically acquire/release slots from a global pool. Three tiers (Search > High-write > Low-write) ensure search latency is protected. Each service wraps its Milvus CRUD calls with the guard. A write ceiling prevents writers from starving search. Crash safety via TTL-based leases with background counter correction.

**Tech Stack:** Python 3.10+, redis (sync + async), Lua scripts, pika, aio_pika, prometheus_client, pytest, fakeredis

**Spec:** `docs/superpowers/specs/2026-04-09-milvus-global-concurrency-guard-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `libs/common-utils/src/common_utils/concurrency/__init__.py` | Package init, exports |
| Create | `libs/common-utils/src/common_utils/concurrency/config.py` | `GuardConfig` dataclass |
| Create | `libs/common-utils/src/common_utils/concurrency/lua_scripts.py` | ACQUIRE / RELEASE / CORRECT Lua script strings |
| Create | `libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard.py` | Async guard (for aio_pika + asyncio services) |
| Create | `libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard_sync.py` | Sync guard (for pika services) |
| Create | `libs/common-utils/src/common_utils/concurrency/metrics.py` | Prometheus metrics for the guard |
| Create | `libs/common-utils/tests/test_milvus_concurrency_guard.py` | Unit tests (fakeredis) |
| Create | `libs/common-utils/tests/test_milvus_concurrency_guard_sync.py` | Unit tests for sync wrapper |
| Create | `libs/common-utils/tests/test_concurrency_integration.py` | Multi-tier contention tests |
| Modify | `libs/common-utils/setup.py` | Add `redis` dependency |
| Modify | `apps-microservices/di-database-qdrant-service/app/main.py` | Init guard |
| Modify | `apps-microservices/di-database-qdrant-service/app/core/processor.py` | Wrap CRUD calls |
| Modify | `apps-microservices/di-database-qdrant-service/app/messaging/consumer.py` | Add `basic_qos` |
| Modify | `apps-microservices/echange-database-qdrant-service/app/main.py` | Init guard |
| Modify | `apps-microservices/echange-database-qdrant-service/app/core/processor.py` | Wrap CRUD calls |
| Modify | `apps-microservices/echange-database-qdrant-service/app/messaging/consumer.py` | Add `basic_qos` |
| Modify | `apps-microservices/product-database-qdrant-service/app/main.py` | Init guard |
| Modify | `apps-microservices/product-database-qdrant-service/app/core/processor.py` | Wrap CRUD calls |
| Modify | `apps-microservices/product-database-qdrant-service/app/messaging/consumer.py` | Add `basic_qos` |
| Modify | `apps-microservices/website-database-qdrant-service/app/main.py` | Init guard |
| Modify | `apps-microservices/website-database-qdrant-service/app/core/processor.py` | Wrap CRUD calls |
| Modify | `apps-microservices/website-database-qdrant-service/app/messaging/consumer.py` | Add `basic_qos` |
| Modify | `apps-microservices/document-database-qdrant-service/app/main.py` | Init async guard |
| Modify | `apps-microservices/document-database-qdrant-service/app/core/processor.py` | Wrap CRUD calls (async) |
| Modify | `apps-microservices/document-database-qdrant-service/app/messaging/consumer.py` | Lower prefetch to 10 |
| Modify | `apps-microservices/database-recherche-service/infrastructure/grpc_server.py` | Replace local semaphore with Tier 1 guard |
| Modify | `docker-compose.yml` | Add env vars for all 6 services |

---

## Task 1: GuardConfig and Lua Scripts

**Files:**
- Create: `libs/common-utils/src/common_utils/concurrency/__init__.py`
- Create: `libs/common-utils/src/common_utils/concurrency/config.py`
- Create: `libs/common-utils/src/common_utils/concurrency/lua_scripts.py`
- Test: `libs/common-utils/tests/test_milvus_concurrency_guard.py`

- [ ] **Step 1: Create the concurrency package with config**

```python
# libs/common-utils/src/common_utils/concurrency/__init__.py
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
from common_utils.concurrency.milvus_concurrency_guard_sync import MilvusConcurrencyGuardSync

__all__ = ["GuardConfig", "MilvusConcurrencyGuard", "MilvusConcurrencyGuardSync"]
```

```python
# libs/common-utils/src/common_utils/concurrency/config.py
import os
from dataclasses import dataclass, field


@dataclass
class GuardConfig:
    """Configuration for MilvusConcurrencyGuard."""

    global_max: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_GLOBAL_MAX_CONCURRENT", "50"))
    )
    write_ceiling: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_WRITE_CEILING", "30"))
    )
    tier: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_TIER", "3"))
    )
    service_name: str = field(
        default_factory=lambda: os.getenv("MILVUS_CONCURRENCY_SERVICE_NAME", "unknown")
    )
    lease_ttl: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_LEASE_TTL", "60"))
    )
    acquire_timeout: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_ACQUIRE_TIMEOUT", "30"))
    )
    retry_interval: float = field(
        default_factory=lambda: float(os.getenv("MILVUS_CONCURRENCY_RETRY_INTERVAL", "0.5"))
    )
    fallback_limit: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_FALLBACK_LIMIT", "5"))
    )
    correction_interval: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_CORRECTION_INTERVAL", "30"))
    )
```

- [ ] **Step 2: Create Lua scripts**

```python
# libs/common-utils/src/common_utils/concurrency/lua_scripts.py
"""
Atomic Lua scripts for Redis-based concurrency guard.
All slot operations (acquire/release/correct) run atomically via EVAL/EVALSHA.
"""

# Keys used:
#   milvus:slots:total          — current total active operations
#   milvus:slots:writes         — current active write operations (tier 2+3)
#   milvus:slots:tier2_waiters  — count of tier 2 services waiting

ACQUIRE_SCRIPT = """
local total_key = KEYS[1]           -- milvus:slots:total
local writes_key = KEYS[2]         -- milvus:slots:writes
local tier2_waiters_key = KEYS[3]  -- milvus:slots:tier2_waiters
local lease_key = KEYS[4]          -- milvus:slots:lease:{lease_id}

local tier = tonumber(ARGV[1])
local global_max = tonumber(ARGV[2])
local write_ceiling = tonumber(ARGV[3])
local lease_value = ARGV[4]        -- "{service}:{tier}:{timestamp}"
local lease_ttl = tonumber(ARGV[5])

local total = tonumber(redis.call('GET', total_key) or '0')
local writes = tonumber(redis.call('GET', writes_key) or '0')

if tier == 1 then
    -- Search: only blocked by global max
    if total >= global_max then
        return 0  -- DENIED
    end
    redis.call('INCR', total_key)
    redis.call('SET', lease_key, lease_value, 'EX', lease_ttl)
    return 1  -- GRANTED

else
    -- Writers (tier 2 or 3)
    if writes >= write_ceiling then
        return 0  -- DENIED: write ceiling reached
    end
    if total >= global_max then
        return 0  -- DENIED: global max reached
    end
    if tier == 3 then
        local tier2_waiters = tonumber(redis.call('GET', tier2_waiters_key) or '0')
        if tier2_waiters > 0 then
            return 0  -- DENIED: tier 2 has priority
        end
    end
    redis.call('INCR', total_key)
    redis.call('INCR', writes_key)
    redis.call('SET', lease_key, lease_value, 'EX', lease_ttl)
    return 1  -- GRANTED
end
"""

RELEASE_SCRIPT = """
local total_key = KEYS[1]      -- milvus:slots:total
local writes_key = KEYS[2]     -- milvus:slots:writes
local lease_key = KEYS[3]      -- milvus:slots:lease:{lease_id}

local tier = tonumber(ARGV[1])

-- Only release if lease still exists (idempotent — prevents double-release)
if redis.call('EXISTS', lease_key) == 1 then
    redis.call('DEL', lease_key)
    redis.call('DECR', total_key)
    -- Floor at 0 to prevent negative drift
    if tonumber(redis.call('GET', total_key) or '0') < 0 then
        redis.call('SET', total_key, '0')
    end
    if tier == 2 or tier == 3 then
        redis.call('DECR', writes_key)
        if tonumber(redis.call('GET', writes_key) or '0') < 0 then
            redis.call('SET', writes_key, '0')
        end
    end
    return 1  -- Released
end
return 0  -- Lease already expired or released
"""

CORRECT_COUNTERS_SCRIPT = """
local total_key = KEYS[1]   -- milvus:slots:total
local writes_key = KEYS[2]  -- milvus:slots:writes
local lease_prefix = ARGV[1] -- "milvus:slots:lease:"

-- Count actual lease keys
local cursor = '0'
local total_leases = 0
local write_leases = 0
repeat
    local result = redis.call('SCAN', cursor, 'MATCH', lease_prefix .. '*', 'COUNT', 100)
    cursor = result[1]
    local keys = result[2]
    for _, key in ipairs(keys) do
        total_leases = total_leases + 1
        local value = redis.call('GET', key)
        if value then
            -- value format: "service:tier:timestamp"
            local tier_str = value:match(':(%d+):')
            local tier = tonumber(tier_str)
            if tier == 2 or tier == 3 then
                write_leases = write_leases + 1
            end
        end
    end
until cursor == '0'

-- Compare and correct
local stored_total = tonumber(redis.call('GET', total_key) or '0')
local stored_writes = tonumber(redis.call('GET', writes_key) or '0')
local corrected = 0

if stored_total ~= total_leases then
    redis.call('SET', total_key, tostring(total_leases))
    corrected = 1
end
if stored_writes ~= write_leases then
    redis.call('SET', writes_key, tostring(write_leases))
    corrected = 1
end

return {corrected, total_leases, write_leases, stored_total, stored_writes}
"""
```

- [ ] **Step 3: Write initial test for config**

```python
# libs/common-utils/tests/test_milvus_concurrency_guard.py
import pytest
from common_utils.concurrency.config import GuardConfig


class TestGuardConfig:
    def test_defaults(self):
        config = GuardConfig()
        assert config.global_max == 50
        assert config.write_ceiling == 30
        assert config.tier == 3
        assert config.lease_ttl == 60
        assert config.acquire_timeout == 30
        assert config.retry_interval == 0.5
        assert config.fallback_limit == 5
        assert config.correction_interval == 30

    def test_custom_values(self):
        config = GuardConfig(
            global_max=100,
            write_ceiling=60,
            tier=1,
            service_name="test-service",
            lease_ttl=120,
        )
        assert config.global_max == 100
        assert config.write_ceiling == 60
        assert config.tier == 1
        assert config.service_name == "test-service"
        assert config.lease_ttl == 120

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MILVUS_GLOBAL_MAX_CONCURRENT", "200")
        monkeypatch.setenv("MILVUS_WRITE_CEILING", "80")
        monkeypatch.setenv("MILVUS_CONCURRENCY_TIER", "2")
        config = GuardConfig()
        assert config.global_max == 200
        assert config.write_ceiling == 80
        assert config.tier == 2
```

- [ ] **Step 4: Run tests to verify config works**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py::TestGuardConfig -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```
feat(common-utils): add GuardConfig and Lua scripts for Milvus concurrency guard
```

---

## Task 2: Prometheus Metrics for the Guard

**Files:**
- Create: `libs/common-utils/src/common_utils/concurrency/metrics.py`
- Test: `libs/common-utils/tests/test_milvus_concurrency_guard.py` (append)

- [ ] **Step 1: Write metrics test**

Append to `libs/common-utils/tests/test_milvus_concurrency_guard.py`:

```python
from prometheus_client import REGISTRY
from common_utils.concurrency.metrics import GuardMetrics


class TestGuardMetrics:
    def setup_method(self):
        # Clear existing collectors to avoid duplicates across tests
        collectors = list(REGISTRY._names_to_collectors.keys())
        for name in collectors:
            if name.startswith("milvus_guard_"):
                REGISTRY.unregister(REGISTRY._names_to_collectors[name])

    def test_metrics_registered(self):
        metrics = GuardMetrics()
        assert metrics.slots_active is not None
        assert metrics.slots_max is not None
        assert metrics.write_ceiling is not None
        assert metrics.acquire_duration is not None
        assert metrics.acquire_timeouts is not None
        assert metrics.lease_expirations is not None
        assert metrics.fallback_active is not None

    def test_record_acquire(self):
        metrics = GuardMetrics()
        metrics.record_acquire(tier="2", service="test-svc", duration=0.5)
        # Verify the histogram observed a value (no error)
        assert metrics.acquire_duration._metrics  # internal check that labels exist

    def test_record_timeout(self):
        metrics = GuardMetrics()
        metrics.record_timeout(tier="2", service="test-svc")
        # Counter should have incremented
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py::TestGuardMetrics -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common_utils.concurrency.metrics'`

- [ ] **Step 3: Implement metrics**

```python
# libs/common-utils/src/common_utils/concurrency/metrics.py
from prometheus_client import Gauge, Histogram, Counter


class GuardMetrics:
    """Prometheus metrics for MilvusConcurrencyGuard."""

    def __init__(self):
        self.slots_active = Gauge(
            "milvus_guard_slots_active",
            "Current Milvus concurrency slots in use",
            ["tier", "service"],
        )
        self.slots_max = Gauge(
            "milvus_guard_slots_max",
            "Configured global max concurrent Milvus operations",
        )
        self.write_ceiling = Gauge(
            "milvus_guard_write_ceiling",
            "Configured max concurrent write operations",
        )
        self.acquire_duration = Histogram(
            "milvus_guard_acquire_duration_seconds",
            "Time spent waiting to acquire a Milvus concurrency slot",
            ["tier", "service"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        )
        self.acquire_timeouts = Counter(
            "milvus_guard_acquire_timeouts_total",
            "Number of acquire attempts that timed out",
            ["tier", "service"],
        )
        self.lease_expirations = Counter(
            "milvus_guard_lease_expirations_total",
            "Number of lease expirations detected during counter correction",
            ["service"],
        )
        self.fallback_active = Gauge(
            "milvus_guard_fallback_active",
            "1 if Redis is unavailable and local fallback is active",
            ["service"],
        )

    def record_acquire(self, tier: str, service: str, duration: float):
        self.slots_active.labels(tier=tier, service=service).inc()
        self.acquire_duration.labels(tier=tier, service=service).observe(duration)

    def record_release(self, tier: str, service: str):
        self.slots_active.labels(tier=tier, service=service).dec()

    def record_timeout(self, tier: str, service: str):
        self.acquire_timeouts.labels(tier=tier, service=service).inc()

    def set_config_gauges(self, global_max: int, write_ceiling: int):
        self.slots_max.set(global_max)
        self.write_ceiling.set(write_ceiling)

    def set_fallback(self, service: str, active: bool):
        self.fallback_active.labels(service=service).set(1 if active else 0)

    def record_lease_expiration(self, service: str, count: int = 1):
        self.lease_expirations.labels(service=service).inc(count)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py::TestGuardMetrics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
feat(common-utils): add Prometheus metrics for Milvus concurrency guard
```

---

## Task 3: Async MilvusConcurrencyGuard

**Files:**
- Create: `libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard.py`
- Test: `libs/common-utils/tests/test_milvus_concurrency_guard.py` (append)

- [ ] **Step 1: Install test dependency**

Run: `cd libs/common-utils && pip install fakeredis[lua]`

fakeredis with Lua support lets us test Lua scripts without a real Redis server.

- [ ] **Step 2: Write failing tests for async guard**

Append to `libs/common-utils/tests/test_milvus_concurrency_guard.py`:

```python
import asyncio
import time
import uuid
import fakeredis.aioredis
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def make_guard(redis_client):
    """Factory to create guards with different configs."""
    def _make(tier=1, global_max=5, write_ceiling=3, service_name="test"):
        config = GuardConfig(
            global_max=global_max,
            write_ceiling=write_ceiling,
            tier=tier,
            service_name=service_name,
            lease_ttl=10,
            acquire_timeout=2,
            retry_interval=0.1,
            fallback_limit=2,
            correction_interval=300,
        )
        return MilvusConcurrencyGuard(redis_client, config)
    return _make


class TestMilvusConcurrencyGuard:
    @pytest.mark.asyncio
    async def test_acquire_release_basic(self, make_guard, redis_client):
        guard = make_guard(tier=1)
        lease_id = await guard.acquire()
        assert lease_id is not None
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 1
        await guard.release(lease_id)
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    @pytest.mark.asyncio
    async def test_tier1_not_blocked_by_writers(self, make_guard, redis_client):
        """Search (tier 1) can acquire even when write ceiling is full."""
        # Fill write ceiling with tier 2
        t2_guard = make_guard(tier=2)
        leases = []
        for _ in range(3):  # write_ceiling=3
            leases.append(await t2_guard.acquire())
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert writes == 3

        # Tier 1 should still succeed (total=3 < global_max=5)
        t1_guard = make_guard(tier=1)
        lease = await t1_guard.acquire()
        assert lease is not None
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 4

        # Cleanup
        await t1_guard.release(lease)
        for l in leases:
            await t2_guard.release(l)

    @pytest.mark.asyncio
    async def test_writers_blocked_at_ceiling(self, make_guard):
        """Tier 2/3 denied when write ceiling reached."""
        t2_guard = make_guard(tier=2)
        leases = []
        for _ in range(3):  # write_ceiling=3
            leases.append(await t2_guard.acquire())

        # Next tier 2 should timeout
        t2_blocked = make_guard(tier=2, service_name="blocked")
        with pytest.raises(TimeoutError):
            await t2_blocked.acquire()

        for l in leases:
            await t2_guard.release(l)

    @pytest.mark.asyncio
    async def test_tier3_blocked_when_tier2_waiting(self, make_guard, redis_client):
        """Tier 3 cannot acquire while tier 2 has waiters."""
        # Fill write ceiling minus 1
        t2_guard = make_guard(tier=2)
        l1 = await t2_guard.acquire()
        l2 = await t2_guard.acquire()
        # 2 of 3 slots used — 1 remaining

        # Simulate tier 2 waiter by setting the counter
        await redis_client.set("milvus:slots:tier2_waiters", "1")

        # Tier 3 should be denied even though write ceiling not full
        t3_guard = make_guard(tier=3, service_name="t3")
        with pytest.raises(TimeoutError):
            await t3_guard.acquire()

        # Cleanup waiter counter
        await redis_client.set("milvus:slots:tier2_waiters", "0")
        await t2_guard.release(l1)
        await t2_guard.release(l2)

    @pytest.mark.asyncio
    async def test_global_max_blocks_all_tiers(self, make_guard):
        """Even search is denied when global max is reached."""
        t1_guard = make_guard(tier=1)
        leases = []
        for _ in range(5):  # global_max=5
            leases.append(await t1_guard.acquire())

        # Next acquire should timeout
        t1_blocked = make_guard(tier=1, service_name="blocked")
        with pytest.raises(TimeoutError):
            await t1_blocked.acquire()

        for l in leases:
            await t1_guard.release(l)

    @pytest.mark.asyncio
    async def test_acquire_timeout(self, make_guard):
        """Acquire raises TimeoutError after deadline."""
        t1_guard = make_guard(tier=1)
        leases = []
        for _ in range(5):  # global_max=5
            leases.append(await t1_guard.acquire())

        t1_blocked = make_guard(tier=1, service_name="blocked")
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            await t1_blocked.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 1.5  # acquire_timeout=2, should be close to 2s

        for l in leases:
            await t1_guard.release(l)

    @pytest.mark.asyncio
    async def test_context_manager_releases_on_exception(self, make_guard, redis_client):
        """slot() context manager releases even if the wrapped code raises."""
        guard = make_guard(tier=2)
        with pytest.raises(ValueError):
            async with guard.slot():
                total = int(await redis_client.get("milvus:slots:total") or 0)
                assert total == 1
                raise ValueError("simulated CRUD failure")

        # Slot should be released
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    @pytest.mark.asyncio
    async def test_double_release_is_idempotent(self, make_guard, redis_client):
        """Releasing the same lease twice should not cause negative counters."""
        guard = make_guard(tier=2)
        lease_id = await guard.acquire()
        await guard.release(lease_id)
        await guard.release(lease_id)  # Second release — should be no-op
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 0
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert writes == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py::TestMilvusConcurrencyGuard -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement async guard**

```python
# libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard.py
import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.lua_scripts import (
    ACQUIRE_SCRIPT,
    CORRECT_COUNTERS_SCRIPT,
    RELEASE_SCRIPT,
)
from common_utils.concurrency.metrics import GuardMetrics

logger = logging.getLogger(__name__)

TOTAL_KEY = "milvus:slots:total"
WRITES_KEY = "milvus:slots:writes"
TIER2_WAITERS_KEY = "milvus:slots:tier2_waiters"
LEASE_PREFIX = "milvus:slots:lease:"


class MilvusConcurrencyGuard:
    """Async Redis-backed global concurrency guard for Milvus operations."""

    def __init__(self, redis_client, config: GuardConfig, metrics: GuardMetrics | None = None):
        self._redis = redis_client
        self._config = config
        self._metrics = metrics or GuardMetrics()
        self._fallback_semaphore = asyncio.Semaphore(config.fallback_limit)
        self._using_fallback = False
        self._acquire_sha = None
        self._release_sha = None
        self._correct_sha = None
        self._correction_task: asyncio.Task | None = None
        self._metrics.set_config_gauges(config.global_max, config.write_ceiling)

    async def _ensure_scripts(self):
        """Register Lua scripts on first use."""
        if self._acquire_sha is None:
            self._acquire_sha = self._redis.register_script(ACQUIRE_SCRIPT)
            self._release_sha = self._redis.register_script(RELEASE_SCRIPT)
            self._correct_sha = self._redis.register_script(CORRECT_COUNTERS_SCRIPT)

    async def acquire(self) -> str:
        """Acquire a slot. Returns lease_id. Raises TimeoutError on deadline."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)
        is_tier2_waiter = False

        try:
            await self._ensure_scripts()
        except Exception as e:
            logger.warning("Redis unavailable for script registration: %s — using fallback", e)
            return await self._acquire_fallback()

        lease_id = f"{service}:{uuid.uuid4().hex[:12]}"
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        lease_value = f"{service}:{tier}:{int(time.time())}"

        start = time.monotonic()
        deadline = start + self._config.acquire_timeout

        # If tier 2 is about to wait, increment the waiter counter
        # so tier 3 knows to yield
        first_attempt = True

        while True:
            try:
                result = await self._acquire_sha(
                    keys=[TOTAL_KEY, WRITES_KEY, TIER2_WAITERS_KEY, lease_key],
                    args=[tier, self._config.global_max, self._config.write_ceiling, lease_value, self._config.lease_ttl],
                )

                if result == 1:
                    # GRANTED
                    if is_tier2_waiter:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    duration = time.monotonic() - start
                    self._metrics.record_acquire(tier=tier_str, service=service, duration=duration)
                    if self._using_fallback:
                        self._using_fallback = False
                        self._metrics.set_fallback(service, False)
                        logger.info("Redis recovered — switching back to global guard")
                    logger.debug(
                        "Slot acquired: service=%s tier=%s lease=%s wait_ms=%.0f",
                        service, tier, lease_id, duration * 1000,
                    )
                    return lease_id

                # DENIED — wait and retry
                if first_attempt and tier == 2:
                    await self._redis.incr(TIER2_WAITERS_KEY)
                    is_tier2_waiter = True
                    first_attempt = False

                if time.monotonic() >= deadline:
                    if is_tier2_waiter:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    self._metrics.record_timeout(tier=tier_str, service=service)
                    logger.warning(
                        "Acquire timeout: service=%s tier=%s waited=%.1fs",
                        service, tier, self._config.acquire_timeout,
                    )
                    raise TimeoutError(
                        f"Could not acquire Milvus slot within {self._config.acquire_timeout}s "
                        f"(service={service}, tier={tier})"
                    )

                await asyncio.sleep(self._config.retry_interval)

            except TimeoutError:
                raise
            except Exception as e:
                if is_tier2_waiter:
                    try:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    except Exception:
                        pass
                logger.warning("Redis error during acquire: %s — using fallback", e)
                return await self._acquire_fallback()

    async def _acquire_fallback(self) -> str:
        """Local semaphore fallback when Redis is unavailable."""
        if not self._using_fallback:
            self._using_fallback = True
            self._metrics.set_fallback(self._config.service_name, True)
            logger.warning(
                "Redis unavailable — falling back to local concurrency limit (%d)",
                self._config.fallback_limit,
            )
        await self._fallback_semaphore.acquire()
        return f"fallback:{uuid.uuid4().hex[:12]}"

    async def release(self, lease_id: str):
        """Release a slot by lease_id."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)

        if lease_id.startswith("fallback:"):
            self._fallback_semaphore.release()
            logger.debug("Fallback slot released: service=%s lease=%s", service, lease_id)
            return

        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            await self._ensure_scripts()
            result = await self._release_sha(
                keys=[TOTAL_KEY, WRITES_KEY, lease_key],
                args=[tier],
            )
            if result == 1:
                self._metrics.record_release(tier=tier_str, service=service)
                logger.debug("Slot released: service=%s tier=%s lease=%s", service, tier, lease_id)
            else:
                logger.debug("Lease already expired: service=%s lease=%s", service, lease_id)
        except Exception as e:
            logger.warning("Redis error during release: %s — slot may leak until TTL expires", e)

    async def extend_lease(self, lease_id: str):
        """Extend TTL for long-running operations."""
        if lease_id.startswith("fallback:"):
            return
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            await self._redis.expire(lease_key, self._config.lease_ttl)
        except Exception as e:
            logger.warning("Failed to extend lease %s: %s", lease_id, e)

    @asynccontextmanager
    async def slot(self):
        """Context manager: acquire, yield, release. Handles cleanup on exception."""
        lease_id = await self.acquire()
        try:
            yield lease_id
        finally:
            await self.release(lease_id)

    async def start_correction_loop(self):
        """Start background counter correction task."""
        if self._correction_task is not None:
            return
        self._correction_task = asyncio.create_task(self._correction_loop())

    async def _correction_loop(self):
        """Periodically verify counters match actual lease keys."""
        while True:
            await asyncio.sleep(self._config.correction_interval)
            try:
                await self._ensure_scripts()
                result = await self._correct_sha(
                    keys=[TOTAL_KEY, WRITES_KEY],
                    args=[LEASE_PREFIX],
                )
                corrected, actual_total, actual_writes, stored_total, stored_writes = result
                if corrected:
                    logger.warning(
                        "Counter correction: total %d->%d, writes %d->%d",
                        stored_total, actual_total, stored_writes, actual_writes,
                    )
                    self._metrics.record_lease_expiration(
                        self._config.service_name,
                        abs(stored_total - actual_total),
                    )
            except Exception as e:
                logger.debug("Counter correction skipped: %s", e)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py::TestMilvusConcurrencyGuard -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```
feat(common-utils): implement async MilvusConcurrencyGuard with Lua-based acquire/release
```

---

## Task 4: Sync MilvusConcurrencyGuardSync

**Files:**
- Create: `libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard_sync.py`
- Create: `libs/common-utils/tests/test_milvus_concurrency_guard_sync.py`

- [ ] **Step 1: Write failing tests for sync guard**

```python
# libs/common-utils/tests/test_milvus_concurrency_guard_sync.py
import pytest
import threading
import fakeredis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard_sync import MilvusConcurrencyGuardSync


@pytest.fixture
def redis_client():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    client.flushall()
    client.close()


@pytest.fixture
def make_guard(redis_client):
    def _make(tier=2, global_max=5, write_ceiling=3, service_name="test-sync"):
        config = GuardConfig(
            global_max=global_max,
            write_ceiling=write_ceiling,
            tier=tier,
            service_name=service_name,
            lease_ttl=10,
            acquire_timeout=2,
            retry_interval=0.1,
            fallback_limit=2,
            correction_interval=300,
        )
        return MilvusConcurrencyGuardSync(redis_client, config)
    return _make


class TestMilvusConcurrencyGuardSync:
    def test_acquire_release_basic(self, make_guard, redis_client):
        guard = make_guard(tier=2)
        lease_id = guard.acquire()
        assert lease_id is not None
        total = int(redis_client.get("milvus:slots:total") or 0)
        assert total == 1
        writes = int(redis_client.get("milvus:slots:writes") or 0)
        assert writes == 1
        guard.release(lease_id)
        total = int(redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    def test_context_manager(self, make_guard, redis_client):
        guard = make_guard(tier=2)
        with guard.slot() as lease_id:
            assert lease_id is not None
            total = int(redis_client.get("milvus:slots:total") or 0)
            assert total == 1
        total = int(redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    def test_context_manager_releases_on_exception(self, make_guard, redis_client):
        guard = make_guard(tier=2)
        with pytest.raises(ValueError):
            with guard.slot():
                raise ValueError("boom")
        total = int(redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    def test_writers_blocked_at_ceiling(self, make_guard):
        guard = make_guard(tier=2)
        leases = [guard.acquire() for _ in range(3)]  # write_ceiling=3
        blocked = make_guard(tier=2, service_name="blocked")
        with pytest.raises(TimeoutError):
            blocked.acquire()
        for l in leases:
            guard.release(l)

    def test_fallback_on_redis_error(self):
        """When Redis is broken, sync guard falls back to local threading.Semaphore."""
        config = GuardConfig(
            global_max=5, write_ceiling=3, tier=2,
            service_name="fallback-test", lease_ttl=10,
            acquire_timeout=2, retry_interval=0.1, fallback_limit=2,
        )
        # Pass None as redis client to force error
        guard = MilvusConcurrencyGuardSync(None, config)
        lease_id = guard.acquire()
        assert lease_id.startswith("fallback:")
        guard.release(lease_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard_sync.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement sync guard**

```python
# libs/common-utils/src/common_utils/concurrency/milvus_concurrency_guard_sync.py
import logging
import threading
import time
import uuid
from contextlib import contextmanager

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.lua_scripts import ACQUIRE_SCRIPT, RELEASE_SCRIPT
from common_utils.concurrency.metrics import GuardMetrics

logger = logging.getLogger(__name__)

TOTAL_KEY = "milvus:slots:total"
WRITES_KEY = "milvus:slots:writes"
TIER2_WAITERS_KEY = "milvus:slots:tier2_waiters"
LEASE_PREFIX = "milvus:slots:lease:"


class MilvusConcurrencyGuardSync:
    """Synchronous Redis-backed global concurrency guard for pika-based services."""

    def __init__(self, redis_client, config: GuardConfig, metrics: GuardMetrics | None = None):
        self._redis = redis_client
        self._config = config
        self._metrics = metrics or GuardMetrics()
        self._fallback_semaphore = threading.Semaphore(config.fallback_limit)
        self._using_fallback = False
        self._acquire_script = None
        self._release_script = None
        self._metrics.set_config_gauges(config.global_max, config.write_ceiling)

    def _ensure_scripts(self):
        if self._redis is None:
            raise ConnectionError("Redis client is None")
        if self._acquire_script is None:
            self._acquire_script = self._redis.register_script(ACQUIRE_SCRIPT)
            self._release_script = self._redis.register_script(RELEASE_SCRIPT)

    def acquire(self) -> str:
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)
        is_tier2_waiter = False

        try:
            self._ensure_scripts()
        except Exception as e:
            logger.warning("Redis unavailable: %s — using fallback", e)
            return self._acquire_fallback()

        lease_id = f"{service}:{uuid.uuid4().hex[:12]}"
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        lease_value = f"{service}:{tier}:{int(time.time())}"

        start = time.monotonic()
        deadline = start + self._config.acquire_timeout
        first_attempt = True

        while True:
            try:
                result = self._acquire_script(
                    keys=[TOTAL_KEY, WRITES_KEY, TIER2_WAITERS_KEY, lease_key],
                    args=[tier, self._config.global_max, self._config.write_ceiling, lease_value, self._config.lease_ttl],
                )
                if result == 1:
                    if is_tier2_waiter:
                        self._redis.decr(TIER2_WAITERS_KEY)
                    duration = time.monotonic() - start
                    self._metrics.record_acquire(tier=tier_str, service=service, duration=duration)
                    if self._using_fallback:
                        self._using_fallback = False
                        self._metrics.set_fallback(service, False)
                        logger.info("Redis recovered — switching back to global guard")
                    logger.debug(
                        "Slot acquired: service=%s tier=%s lease=%s wait_ms=%.0f",
                        service, tier, lease_id, duration * 1000,
                    )
                    return lease_id

                if first_attempt and tier == 2:
                    self._redis.incr(TIER2_WAITERS_KEY)
                    is_tier2_waiter = True
                    first_attempt = False

                if time.monotonic() >= deadline:
                    if is_tier2_waiter:
                        self._redis.decr(TIER2_WAITERS_KEY)
                    self._metrics.record_timeout(tier=tier_str, service=service)
                    raise TimeoutError(
                        f"Could not acquire Milvus slot within {self._config.acquire_timeout}s "
                        f"(service={service}, tier={tier})"
                    )
                time.sleep(self._config.retry_interval)

            except TimeoutError:
                raise
            except Exception as e:
                if is_tier2_waiter:
                    try:
                        self._redis.decr(TIER2_WAITERS_KEY)
                    except Exception:
                        pass
                logger.warning("Redis error: %s — using fallback", e)
                return self._acquire_fallback()

    def _acquire_fallback(self) -> str:
        if not self._using_fallback:
            self._using_fallback = True
            self._metrics.set_fallback(self._config.service_name, True)
            logger.warning(
                "Redis unavailable — falling back to local concurrency limit (%d)",
                self._config.fallback_limit,
            )
        self._fallback_semaphore.acquire()
        return f"fallback:{uuid.uuid4().hex[:12]}"

    def release(self, lease_id: str):
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)

        if lease_id.startswith("fallback:"):
            self._fallback_semaphore.release()
            return

        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            self._ensure_scripts()
            result = self._release_script(
                keys=[TOTAL_KEY, WRITES_KEY, lease_key],
                args=[tier],
            )
            if result == 1:
                self._metrics.record_release(tier=tier_str, service=service)
        except Exception as e:
            logger.warning("Redis error during release: %s", e)

    def extend_lease(self, lease_id: str):
        if lease_id.startswith("fallback:"):
            return
        try:
            self._redis.expire(f"{LEASE_PREFIX}{lease_id}", self._config.lease_ttl)
        except Exception as e:
            logger.warning("Failed to extend lease: %s", e)

    @contextmanager
    def slot(self):
        lease_id = self.acquire()
        try:
            yield lease_id
        finally:
            self.release(lease_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard_sync.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Update setup.py to add redis dependency**

Modify `libs/common-utils/setup.py`:

```python
from setuptools import setup, find_packages
setup(
    name="common-utils",
    version="0.1",
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        "redis>=5.0.0",
    ],
)
```

- [ ] **Step 6: Commit**

```
feat(common-utils): implement sync MilvusConcurrencyGuardSync and add redis dependency
```

---

## Task 5: Integration Test — Multi-Tier Contention

**Files:**
- Create: `libs/common-utils/tests/test_concurrency_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# libs/common-utils/tests/test_concurrency_integration.py
"""
Multi-tier contention tests simulating 6 services competing for slots.
Uses fakeredis — no real Redis needed.
"""
import asyncio
import pytest
import fakeredis.aioredis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard


@pytest.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


def make_guard(redis_client, tier, service_name, global_max=10, write_ceiling=6):
    config = GuardConfig(
        global_max=global_max,
        write_ceiling=write_ceiling,
        tier=tier,
        service_name=service_name,
        lease_ttl=30,
        acquire_timeout=5,
        retry_interval=0.05,
        fallback_limit=2,
        correction_interval=300,
    )
    return MilvusConcurrencyGuard(redis_client, config)


class TestMultiTierContention:
    @pytest.mark.asyncio
    async def test_search_always_served_under_write_pressure(self, redis_client):
        """With write ceiling full, search (tier 1) should still acquire instantly."""
        # Fill write ceiling with tier 2
        t2 = make_guard(redis_client, tier=2, service_name="product-db")
        t2_leases = []
        for _ in range(6):  # write_ceiling=6
            t2_leases.append(await t2.acquire())

        # Search should succeed immediately
        search = make_guard(redis_client, tier=1, service_name="db-recherche")
        lease = await search.acquire()
        assert lease is not None

        # Cleanup
        await search.release(lease)
        for l in t2_leases:
            await t2.release(l)

    @pytest.mark.asyncio
    async def test_write_ceiling_respected_across_services(self, redis_client):
        """Multiple writer services cannot exceed write_ceiling combined."""
        product = make_guard(redis_client, tier=2, service_name="product-db")
        devis = make_guard(redis_client, tier=2, service_name="di-db")
        website = make_guard(redis_client, tier=3, service_name="website-db")

        leases = []
        # 3 from product (tier 2)
        for _ in range(3):
            leases.append(("product", await product.acquire()))
        # 2 from devis (tier 2)
        for _ in range(2):
            leases.append(("devis", await devis.acquire()))
        # 1 from website (tier 3) — total writes = 6 = ceiling
        leases.append(("website", await website.acquire()))

        # Next writer should be blocked
        echange = make_guard(redis_client, tier=3, service_name="echange-db",
                             global_max=10, write_ceiling=6)
        echange._config.acquire_timeout = 1
        with pytest.raises(TimeoutError):
            await echange.acquire()

        for name, l in leases:
            if name == "product":
                await product.release(l)
            elif name == "devis":
                await devis.release(l)
            else:
                await website.release(l)

    @pytest.mark.asyncio
    async def test_tier2_priority_over_tier3(self, redis_client):
        """When tier 2 is waiting, tier 3 cannot acquire even if slots available."""
        t2 = make_guard(redis_client, tier=2, service_name="product-db")
        t3 = make_guard(redis_client, tier=3, service_name="website-db")

        # Fill 5 of 6 write slots
        t2_leases = []
        for _ in range(5):
            t2_leases.append(await t2.acquire())

        # Signal tier 2 is waiting (simulated by setting the key)
        await redis_client.set("milvus:slots:tier2_waiters", "1")

        # Tier 3 should be blocked even though 1 write slot remains
        t3._config.acquire_timeout = 1
        with pytest.raises(TimeoutError):
            await t3.acquire()

        # Clean up
        await redis_client.set("milvus:slots:tier2_waiters", "0")
        for l in t2_leases:
            await t2.release(l)

    @pytest.mark.asyncio
    async def test_rapid_acquire_release_accuracy(self, redis_client):
        """After many rapid acquire/release cycles, counters should be zero."""
        guards = [
            make_guard(redis_client, tier=1, service_name="search"),
            make_guard(redis_client, tier=2, service_name="product"),
            make_guard(redis_client, tier=3, service_name="website"),
        ]

        async def hammer(guard, count):
            for _ in range(count):
                lease = await guard.acquire()
                await asyncio.sleep(0.001)  # tiny simulated work
                await guard.release(lease)

        # Run 100 cycles per guard concurrently
        await asyncio.gather(
            hammer(guards[0], 100),
            hammer(guards[1], 100),
            hammer(guards[2], 100),
        )

        total = int(await redis_client.get("milvus:slots:total") or 0)
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert total == 0, f"Expected total=0, got {total}"
        assert writes == 0, f"Expected writes=0, got {writes}"
```

- [ ] **Step 2: Run tests**

Run: `cd libs/common-utils && python -m pytest tests/test_concurrency_integration.py -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Commit**

```
test(common-utils): add multi-tier contention integration tests for concurrency guard
```

---

## Task 6: Integrate Guard into Sync Writer Services (di, echange, product, website)

This task covers all 4 synchronous pika-based writer services. The pattern is identical for each.

**Files:**
- Modify: `apps-microservices/di-database-qdrant-service/app/main.py`
- Modify: `apps-microservices/di-database-qdrant-service/app/core/processor.py`
- Modify: `apps-microservices/di-database-qdrant-service/app/messaging/consumer.py`
- Modify: `apps-microservices/echange-database-qdrant-service/app/main.py`
- Modify: `apps-microservices/echange-database-qdrant-service/app/core/processor.py`
- Modify: `apps-microservices/echange-database-qdrant-service/app/messaging/consumer.py`
- Modify: `apps-microservices/product-database-qdrant-service/app/main.py`
- Modify: `apps-microservices/product-database-qdrant-service/app/core/processor.py`
- Modify: `apps-microservices/product-database-qdrant-service/app/messaging/consumer.py`
- Modify: `apps-microservices/website-database-qdrant-service/app/main.py`
- Modify: `apps-microservices/website-database-qdrant-service/app/core/processor.py`
- Modify: `apps-microservices/website-database-qdrant-service/app/messaging/consumer.py`

- [ ] **Step 1: Add `basic_qos` to all 4 sync consumers**

In each consumer's `start_consuming()` method, add `basic_qos` before `basic_consume`:

**di-database-qdrant-service** (`consumer.py` line 126): Insert before `self.channel.basic_consume(...)`:
```python
self.channel.basic_qos(prefetch_count=10)
```

**echange-database-qdrant-service** (`consumer.py` line 126): Same — insert before `self.channel.basic_consume(...)`:
```python
self.channel.basic_qos(prefetch_count=10)
```

**product-database-qdrant-service** (`consumer.py` line 129): Insert before `self.channel.basic_consume(...)`:
```python
self.channel.basic_qos(prefetch_count=10)
```

**website-database-qdrant-service** (`consumer.py` line 124): Insert before `self.channel.basic_consume(...)`:
```python
self.channel.basic_qos(prefetch_count=10)
```

- [ ] **Step 2: Initialize guard in each main.py**

For each of the 4 sync services, add the guard initialization in `main.py` after the RabbitMQ connection is established and before the consumer is created.

**Pattern (same for all 4 — adjust import path and service name):**

Add import at the top:
```python
import redis as sync_redis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard_sync import MilvusConcurrencyGuardSync
```

Add initialization after `start_metrics_server_in_thread(port=8530)` and before `publisher = Publisher(connection)`:
```python
    # --- Initialize Milvus concurrency guard ---
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            redis_client = sync_redis.from_url(redis_url, decode_responses=True)
            redis_client.ping()
            logger.info("Connected to Redis for concurrency guard.")
        except Exception as e:
            logger.warning("Could not connect to Redis: %s — guard will use local fallback", e)
            redis_client = None

    guard_config = GuardConfig(service_name="<SERVICE_NAME>")
    concurrency_guard = MilvusConcurrencyGuardSync(redis_client, guard_config)
```

Service names:
- di-database-qdrant-service: `service_name="di-database-qdrant-service"`
- echange-database-qdrant-service: `service_name="echange-database-qdrant-service"`
- product-database-qdrant-service: `service_name="product-database-qdrant-service"`
- website-database-qdrant-service: `service_name="website-database-qdrant-service"`

Then make the guard accessible to processor. Add to `main.py` after creating the guard:
```python
    # Make guard available to processor module
    import <module_name>.core.processor as proc_module
    proc_module._concurrency_guard = concurrency_guard
```

Where `<module_name>` is:
- `di_database_qdrant_service`
- `echange_database_qdrant_service`
- `product_database_qdrant_service`
- `website_database_qdrant_service`

- [ ] **Step 3: Wrap Milvus calls in each processor.py**

For each processor, add at the top of the file:
```python
# Initialized by main.py at startup
_concurrency_guard = None
```

Then wrap the body of `insertion_data()` with the guard. The guard should encompass ALL Milvus calls within a single message processing (get + insert/update + correspondence), since they represent one logical operation:

**di-database-qdrant-service** (`processor.py`): Wrap the entire body of `insertion_data()` after the validation/setup section (after line 47 where `func` is assigned) and before the return:

```python
def insertion_data(devis_data: dict) -> dict:
    # ... existing validation/setup code (lines 18-47) ...

    func = processing_functions.get(collection_enum)
    result = []

    if not func or len(devis) <= 0:
        raise ValueError("Aucune donnée à insérer ou fonction de traitement non trouvée.")

    lead_id = devis[0].get("lead_id", "lead_id inconnu")

    # Wrap all Milvus operations in concurrency guard
    if _concurrency_guard:
        with _concurrency_guard.slot():
            return _execute_insertion(base_vectorielle, func, devis, lead_id, bdd, collection, _correspondance_devis)
    else:
        return _execute_insertion(base_vectorielle, func, devis, lead_id, bdd, collection, _correspondance_devis)
```

Extract the existing Milvus logic into a helper function `_execute_insertion()` containing the code from `res = base_vectorielle.get_devis(...)` through the end of the function.

**Apply the same pattern to the other 3 sync services:** extract Milvus operations into an inner function, wrap the call with `_concurrency_guard.slot()`.

For **echange-database-qdrant-service**: wrap from `res = base_vectorielle.get_echange(...)` to return.
For **product-database-qdrant-service**: wrap from `res = base_vectorielle.get_produit(...)` to return.
For **website-database-qdrant-service**: wrap from `base_vectorielle.delete_website_by_*()` to return.

- [ ] **Step 4: Commit**

```
feat(ingestion): integrate MilvusConcurrencyGuardSync into 4 sync writer services

- Add basic_qos(prefetch_count=10) to all 4 consumers
- Initialize guard from REDIS_URL in main.py
- Wrap all Milvus CRUD calls with guard.slot()
- Services: di-database, echange-database, product-database, website-database
```

---

## Task 7: Integrate Guard into document-database-qdrant-service (Async)

**Files:**
- Modify: `apps-microservices/document-database-qdrant-service/app/main.py`
- Modify: `apps-microservices/document-database-qdrant-service/app/core/processor.py`
- Modify: `apps-microservices/document-database-qdrant-service/app/messaging/consumer.py`

- [ ] **Step 1: Lower prefetch and semaphore in consumer.py**

In `apps-microservices/document-database-qdrant-service/app/messaging/consumer.py`:

Change line 117 from:
```python
await channel.set_qos(prefetch_count=100)
```
to:
```python
await channel.set_qos(prefetch_count=10)
```

Change line 126 from:
```python
semaphore = asyncio.Semaphore(100)
```
to:
```python
semaphore = asyncio.Semaphore(10)
```

- [ ] **Step 2: Initialize async guard in main.py**

In `apps-microservices/document-database-qdrant-service/app/main.py`, add imports after line 8:

```python
import redis.asyncio as aioredis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
```

Inside the `async with connection:` block (after line 33), before creating publisher/consumer:

```python
            # --- Initialize Milvus concurrency guard ---
            redis_url = os.environ.get("REDIS_URL")
            redis_client = None
            if redis_url:
                try:
                    redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                    await redis_client.ping()
                    logger.info("Connected to Redis for concurrency guard.")
                except Exception as e:
                    logger.warning("Could not connect to Redis: %s — guard will use local fallback", e)
                    redis_client = None

            guard_config = GuardConfig(service_name="document-database-qdrant-service")
            concurrency_guard = MilvusConcurrencyGuard(redis_client, guard_config)
            await concurrency_guard.start_correction_loop()

            # Make guard available to processor
            import document_database_qdrant_service.core.processor as proc_module
            proc_module._concurrency_guard = concurrency_guard
```

- [ ] **Step 3: Wrap Milvus calls in processor.py**

In `apps-microservices/document-database-qdrant-service/app/core/processor.py`, add at top:
```python
_concurrency_guard = None
```

Wrap the entire Milvus operation section of `insertion_data()`. Since this function is already async, use `async with`:

After the validation section (after `func = processing_functions.get(collection_enum)` at line 60), wrap the Milvus operations:

```python
    if _concurrency_guard:
        async with _concurrency_guard.slot():
            return await _execute_insertion(documents, page_type, nb_pages, fichier_source, collection, bdd, func)
    else:
        return await _execute_insertion(documents, page_type, nb_pages, fichier_source, collection, bdd, func)
```

Extract the existing Milvus logic (from `if len(documents) > 0:` through the end) into `async def _execute_insertion(...)`.

- [ ] **Step 4: Commit**

```
feat(document-database): integrate async MilvusConcurrencyGuard

- Lower prefetch from 100 to 10, semaphore from 100 to 10
- Initialize async guard from REDIS_URL
- Start background counter correction loop
- Wrap all Milvus CRUD calls with async guard.slot()
```

---

## Task 8: Integrate Guard into database-recherche-service (Read Path)

**Files:**
- Modify: `apps-microservices/database-recherche-service/infrastructure/grpc_server.py`

- [ ] **Step 1: Add guard initialization in __init__**

In `grpc_server.py`, add imports at the top:
```python
import redis.asyncio as aioredis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
```

In the `__init__` method, replace the line at line 97:
```python
self._zilliz_limiter = asyncio.Semaphore(DB_MAX_CONCURRENT_ZILLIZ_DEFAULT)
```

with:
```python
# Global concurrency guard replaces local semaphore
redis_url = os.environ.get("REDIS_URL")
_redis_client = None
if redis_url:
    try:
        _redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        logging.info("database-recherche-service: Connected to Redis for concurrency guard.")
    except Exception as e:
        logging.warning("database-recherche-service: Redis unavailable: %s — using fallback", e)

_guard_config = GuardConfig(
    tier=1,  # Tier 1 = Search (highest priority)
    service_name="database-recherche-service",
)
self._concurrency_guard = MilvusConcurrencyGuard(_redis_client, _guard_config)
```

- [ ] **Step 2: Replace limiter usage in _process_queue_batch**

In `_process_queue_batch` (around lines 206-210 and 249-253), replace the limiter pattern:

**Before** (lines 206-210):
```python
if limiter:
    async with limiter:
        results = await loop.run_in_executor(executor, _sync_search)
else:
    results = await loop.run_in_executor(executor, _sync_search)
```

**After:**
```python
async with self._concurrency_guard.slot():
    results = await loop.run_in_executor(executor, _sync_search)
```

Apply the same change for hybrid_search (around lines 249-253).

- [ ] **Step 3: Remove limiter parameter from all worker calls**

Change HIGH priority call (line 299-301) from:
```python
await self._process_queue_batch(
    batch, executor=self._high_executor, limiter=None
)
```
to:
```python
await self._process_queue_batch(
    batch, executor=self._high_executor
)
```

Change SHARED call (line 343-347) from:
```python
await self._process_queue_batch(
    batch,
    executor=self._default_executor,
    limiter=self._zilliz_limiter,
)
```
to:
```python
await self._process_queue_batch(
    batch,
    executor=self._default_executor,
)
```

Apply the same to MEDIUM (line 377-381) and LOW (line 409-413) worker calls.

Remove the `limiter=None` parameter from the `_process_queue_batch` method signature (line 163):
```python
# Before
async def _process_queue_batch(self, batch, executor, limiter=None):
# After
async def _process_queue_batch(self, batch, executor):
```

Also remove the `limiter` parameter from `_execute_task` if it passes through there.

- [ ] **Step 4: Start correction loop**

In the server startup code (in `app/main.py` or the `serve()` function), add after creating the gRPC server:
```python
await service_impl._concurrency_guard.start_correction_loop()
```

- [ ] **Step 5: Commit**

```
feat(database-recherche): replace local Zilliz semaphore with global concurrency guard

- Tier 1 (search) priority — never blocked by writers
- Acquire per batch execution, not per gRPC request
- Both HIGH and non-HIGH paths now use the global guard
- Removes the uncontrolled HIGH priority path (was limiter=None)
```

---

## Task 9: Docker Compose Configuration

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add environment variables to all 6 services**

For **database-recherche-service** (around line 258), add to the `environment:` section:
```yaml
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=1
      - MILVUS_CONCURRENCY_SERVICE_NAME=database-recherche-service
      - MILVUS_CONCURRENCY_LEASE_TTL=60
      - MILVUS_CONCURRENCY_ACQUIRE_TIMEOUT=30
```

For **di-database-qdrant-service** (around line 1010), add `environment:` section (currently only has `env_file`):
```yaml
    environment:
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=2
      - MILVUS_CONCURRENCY_SERVICE_NAME=di-database-qdrant-service
```

For **echange-database-qdrant-service** (around line 1027):
```yaml
    environment:
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=3
      - MILVUS_CONCURRENCY_SERVICE_NAME=echange-database-qdrant-service
```

For **website-database-qdrant-service** (around line 1044):
```yaml
    environment:
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=3
      - MILVUS_CONCURRENCY_SERVICE_NAME=website-database-qdrant-service
```

For **product-database-qdrant-service** (around line 1061):
```yaml
    environment:
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=2
      - MILVUS_CONCURRENCY_SERVICE_NAME=product-database-qdrant-service
```

For **document-database-qdrant-service** (around line 1097):
```yaml
    environment:
      - MILVUS_GLOBAL_MAX_CONCURRENT=30
      - MILVUS_WRITE_CEILING=20
      - MILVUS_CONCURRENCY_TIER=3
      - MILVUS_CONCURRENCY_SERVICE_NAME=document-database-qdrant-service
```

Note: `REDIS_URL` should already be in the `.env` file. If not, add `REDIS_URL` to each service's environment. Starting values are conservative: `global_max=30`, `write_ceiling=20`.

- [ ] **Step 2: Verify REDIS_URL is in .env**

Run: `grep -q REDIS_URL .env && echo "REDIS_URL exists" || echo "REDIS_URL MISSING — add it"`

If missing, coordinate with the team to add it to `.env`.

- [ ] **Step 3: Commit**

```
chore(docker): add Milvus concurrency guard env vars to all 6 database services

Conservative starting values: global_max=30, write_ceiling=20
Tier 1: database-recherche (search)
Tier 2: product-database, di-database (high-priority writes)
Tier 3: website-database, echange-database, document-database (low-priority writes)
```

---

## Task 10: Final Verification

- [ ] **Step 1: Run all guard unit tests**

Run: `cd libs/common-utils && python -m pytest tests/test_milvus_concurrency_guard.py tests/test_milvus_concurrency_guard_sync.py tests/test_concurrency_integration.py -v`
Expected: All tests PASS

- [ ] **Step 2: Verify each service starts locally (syntax check)**

For each service, verify the Python module can be imported without errors:

```bash
cd libs/common-utils && pip install -e .
python -c "from common_utils.concurrency import MilvusConcurrencyGuard, MilvusConcurrencyGuardSync, GuardConfig; print('OK')"
```

- [ ] **Step 3: Verify docker-compose syntax**

Run: `docker compose config --profiles app > /dev/null && echo "docker-compose OK"`
Expected: No errors

- [ ] **Step 4: Final commit (if any fixes needed)**

```
chore: final verification fixes for Milvus concurrency guard
```