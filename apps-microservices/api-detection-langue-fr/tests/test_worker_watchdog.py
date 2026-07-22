import asyncio
import pytest
from types import SimpleNamespace
from app.core.async_jobs import JobManager, JobStore


class _FakeRedis:
    def __init__(self): self.kv = {}
    async def ping(self): return True
    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv: return False
        self.kv[k] = v; return True
    async def get(self, k): return self.kv.get(k)
    async def delete(self, k): self.kv.pop(k, None)
    async def expire(self, k, ttl): return True
    async def setex(self, k, ttl, v): self.kv[k] = v; return True


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=8, JOB_WORKER_CONCURRENCY=1,
                JOB_TTL_ACTIVE_S=7200, JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120,
                HEARTBEAT_INTERVAL_S=1, ASYNC_SUBMIT_RETRY_AFTER_S=15, ASYNC_POLL_HINT_MAX_S=30,
                SHUTDOWN_GRACE_S=5, JOB_MAX_S=0.3)
    base.update(over); return SimpleNamespace(**base)


def _req(items, cjid):
    return SimpleNamespace(client_job_id=cjid, items=items, proxy_url=None,
                           use_nlp_detection=True, force_refresh=False, max_concurrency=10,
                           homepage_fallback=True, validate_alternatives=True, mode="complete")


@pytest.mark.asyncio
async def test_watchdog_abandons_wedged_job_and_frees_queue():
    from app.models.schemas import BatchItem
    store = JobStore(client=_FakeRedis())
    hang = asyncio.Event()
    ran2 = asyncio.Event()
    state = {"first": True}

    async def batch_runner(items, mode, opts, progress_cb):
        if state["first"]:
            state["first"] = False
            await hang.wait()            # job1 wedges forever
        ran2.set()                       # job2 runs
        return [], SimpleNamespace(success_count=0, failed_count=0, error_count=0)

    jm = JobManager(store, batch_runner, _settings())
    id1, _ = await jm.submit(_req([BatchItem(url="http://a.fr")], "c1"))
    id2, _ = await jm.submit(_req([BatchItem(url="http://b.fr")], "c2"))

    await asyncio.wait_for(ran2.wait(), timeout=5)     # queue must free up
    rec1 = await store.get(id1)
    assert rec1["status"] == "failed" and rec1["error"] == "job_timeout"
    assert jm._inflight >= 0
    hang.set()                                          # release zombie
    await asyncio.sleep(0.2)                            # must not crash / double-decrement
    await jm.shutdown()
