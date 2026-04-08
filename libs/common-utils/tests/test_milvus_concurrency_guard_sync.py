import pytest
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
        leases = [guard.acquire() for _ in range(3)]
        blocked = make_guard(tier=2, service_name="blocked")
        with pytest.raises(TimeoutError):
            blocked.acquire()
        for l in leases:
            guard.release(l)

    def test_fallback_on_redis_none(self):
        config = GuardConfig(
            global_max=5,
            write_ceiling=3,
            tier=2,
            service_name="fallback-test",
            lease_ttl=10,
            acquire_timeout=2,
            retry_interval=0.1,
            fallback_limit=2,
        )
        guard = MilvusConcurrencyGuardSync(None, config)
        lease_id = guard.acquire()
        assert lease_id.startswith("fallback:")
        guard.release(lease_id)

    def test_double_release_idempotent(self, make_guard, redis_client):
        guard = make_guard(tier=2)
        lease_id = guard.acquire()
        guard.release(lease_id)
        guard.release(lease_id)
        total = int(redis_client.get("milvus:slots:total") or 0)
        assert total == 0
