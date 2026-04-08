import asyncio
import time

import fakeredis.aioredis
import pytest
import pytest_asyncio
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.metrics import GuardMetrics


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


class TestGuardMetrics:
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

    def test_record_release(self):
        metrics = GuardMetrics()
        metrics.record_release(tier="2", service="test-svc")

    def test_record_timeout(self):
        metrics = GuardMetrics()
        metrics.record_timeout(tier="2", service="test-svc")

    def test_set_config_gauges(self):
        metrics = GuardMetrics()
        metrics.set_config_gauges(global_max=50, write_ceiling=30)

    def test_set_fallback(self):
        metrics = GuardMetrics()
        metrics.set_fallback(service="test-svc", active=True)
        metrics.set_fallback(service="test-svc", active=False)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MILVUS_GLOBAL_MAX_CONCURRENT", "200")
        monkeypatch.setenv("MILVUS_WRITE_CEILING", "80")
        monkeypatch.setenv("MILVUS_CONCURRENCY_TIER", "2")
        config = GuardConfig()
        assert config.global_max == 200
        assert config.write_ceiling == 80
        assert config.tier == 2


@pytest_asyncio.fixture
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
        from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
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
        t2_guard = make_guard(tier=2)
        leases = []
        for _ in range(3):
            leases.append(await t2_guard.acquire())
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert writes == 3
        t1_guard = make_guard(tier=1)
        lease = await t1_guard.acquire()
        assert lease is not None
        await t1_guard.release(lease)
        for l in leases:
            await t2_guard.release(l)

    @pytest.mark.asyncio
    async def test_writers_blocked_at_ceiling(self, make_guard):
        """Tier 2/3 denied when write ceiling reached."""
        t2_guard = make_guard(tier=2)
        leases = []
        for _ in range(3):
            leases.append(await t2_guard.acquire())
        t2_blocked = make_guard(tier=2, service_name="blocked")
        with pytest.raises(TimeoutError):
            await t2_blocked.acquire()
        for l in leases:
            await t2_guard.release(l)

    @pytest.mark.asyncio
    async def test_tier3_blocked_when_tier2_waiting(self, make_guard, redis_client):
        """Tier 3 cannot acquire while tier 2 has waiters."""
        t2_guard = make_guard(tier=2)
        l1 = await t2_guard.acquire()
        l2 = await t2_guard.acquire()
        await redis_client.set("milvus:slots:tier2_waiters", "1")
        t3_guard = make_guard(tier=3, service_name="t3")
        with pytest.raises(TimeoutError):
            await t3_guard.acquire()
        await redis_client.set("milvus:slots:tier2_waiters", "0")
        await t2_guard.release(l1)
        await t2_guard.release(l2)

    @pytest.mark.asyncio
    async def test_global_max_blocks_all_tiers(self, make_guard):
        """Even search is denied when global max is reached."""
        t1_guard = make_guard(tier=1)
        leases = []
        for _ in range(5):
            leases.append(await t1_guard.acquire())
        t1_blocked = make_guard(tier=1, service_name="blocked")
        with pytest.raises(TimeoutError):
            await t1_blocked.acquire()
        for l in leases:
            await t1_guard.release(l)

    @pytest.mark.asyncio
    async def test_context_manager_releases_on_exception(self, make_guard, redis_client):
        """slot() context manager releases even if wrapped code raises."""
        guard = make_guard(tier=2)
        with pytest.raises(ValueError):
            async with guard.slot():
                total = int(await redis_client.get("milvus:slots:total") or 0)
                assert total == 1
                raise ValueError("simulated CRUD failure")
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 0

    @pytest.mark.asyncio
    async def test_double_release_is_idempotent(self, make_guard, redis_client):
        """Releasing the same lease twice should not cause negative counters."""
        guard = make_guard(tier=2)
        lease_id = await guard.acquire()
        await guard.release(lease_id)
        await guard.release(lease_id)
        total = int(await redis_client.get("milvus:slots:total") or 0)
        assert total == 0
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert writes == 0

    @pytest.mark.asyncio
    async def test_fallback_when_redis_none(self):
        """When Redis client is None, guard falls back to local semaphore."""
        config = GuardConfig(
            global_max=5, write_ceiling=3, tier=2,
            service_name="fallback-test", lease_ttl=10,
            acquire_timeout=2, retry_interval=0.1, fallback_limit=2,
        )
        from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
        guard = MilvusConcurrencyGuard(None, config)
        lease_id = await guard.acquire()
        assert lease_id.startswith("fallback:")
        await guard.release(lease_id)
