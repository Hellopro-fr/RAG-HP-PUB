import pytest
from app.core.async_jobs import JobStore, poll_status


class FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.kv = {}

    async def ping(self):
        if self.fail:
            raise ConnectionError("down")
        return True

    async def set(self, key, val, nx=False, ex=None):
        if self.fail:
            raise ConnectionError("down")
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    async def get(self, key):
        if self.fail:
            raise ConnectionError("down")
        return self.kv.get(key)

    async def setex(self, key, ttl, val):
        if self.fail:
            raise ConnectionError("down")
        self.kv[key] = val

    async def delete(self, key):
        self.kv.pop(key, None)

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_claim_index_atomic():
    store = JobStore(redis_url=None, client=FakeRedis())
    assert await store.claim_index("c1", "job-A", 100) is True
    assert await store.claim_index("c1", "job-B", 100) is False   # already claimed
    assert await store.get_index("c1") == "job-A"


@pytest.mark.asyncio
async def test_write_raises_on_failure():
    store = JobStore(redis_url=None, client=FakeRedis(fail=True))
    with pytest.raises(Exception):
        await store.write({"job_id": "x"}, 100)


@pytest.mark.asyncio
async def test_get_degrades_to_none():
    store = JobStore(redis_url=None, client=FakeRedis(fail=True))
    assert await store.get("x") is None


@pytest.mark.asyncio
async def test_ping():
    assert await JobStore(None, client=FakeRedis()).ping() is True
    assert await JobStore(None, client=FakeRedis(fail=True)).ping() is False


def test_poll_status_stale():
    rec = {"status": "running", "created_at": 0.0, "last_activity": 0.0}
    assert poll_status(rec, now=1000.0, stale_threshold_s=120) == "stale"
    assert poll_status({**rec, "last_activity": 990.0}, now=1000.0, stale_threshold_s=120) == "running"
    assert poll_status({"status": "completed"}, now=1e9, stale_threshold_s=120) == "completed"
