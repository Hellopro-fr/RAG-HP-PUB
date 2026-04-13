"""
Multi-tier contention tests simulating 6 services competing for slots.
Uses fakeredis — no real Redis needed.
"""

import asyncio

import fakeredis.aioredis
import pytest
import pytest_asyncio

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard


@pytest_asyncio.fixture
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
        """With write ceiling full, search (tier 1) should still acquire."""
        t2 = make_guard(redis_client, tier=2, service_name="product-db")
        t2_leases = []
        for _ in range(6):
            t2_leases.append(await t2.acquire())

        search = make_guard(redis_client, tier=1, service_name="db-recherche")
        lease = await search.acquire()
        assert lease is not None

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
        for _ in range(3):
            leases.append(("product", await product.acquire()))
        for _ in range(2):
            leases.append(("devis", await devis.acquire()))
        leases.append(("website", await website.acquire()))

        # 6 writes = ceiling. Next should timeout.
        echange = make_guard(
            redis_client, tier=3, service_name="echange-db",
            global_max=10, write_ceiling=6,
        )
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
        """When tier 2 is waiting, tier 3 cannot acquire."""
        t2 = make_guard(redis_client, tier=2, service_name="product-db")
        t3 = make_guard(redis_client, tier=3, service_name="website-db")

        t2_leases = []
        for _ in range(5):
            t2_leases.append(await t2.acquire())

        await redis_client.set("milvus:slots:tier2_waiters", "1")

        t3._config.acquire_timeout = 1
        with pytest.raises(TimeoutError):
            await t3.acquire()

        await redis_client.set("milvus:slots:tier2_waiters", "0")
        for l in t2_leases:
            await t2.release(l)

    @pytest.mark.asyncio
    async def test_rapid_acquire_release_accuracy(self, redis_client):
        """After many rapid cycles, counters should be zero."""
        guards = [
            make_guard(redis_client, tier=1, service_name="search"),
            make_guard(redis_client, tier=2, service_name="product"),
            make_guard(redis_client, tier=3, service_name="website"),
        ]

        async def hammer(guard, count):
            for _ in range(count):
                lease = await guard.acquire()
                await asyncio.sleep(0.001)
                await guard.release(lease)

        await asyncio.gather(
            hammer(guards[0], 50),
            hammer(guards[1], 50),
            hammer(guards[2], 50),
        )

        total = int(await redis_client.get("milvus:slots:total") or 0)
        writes = int(await redis_client.get("milvus:slots:writes") or 0)
        assert total == 0, f"Expected total=0, got {total}"
        assert writes == 0, f"Expected writes=0, got {writes}"
