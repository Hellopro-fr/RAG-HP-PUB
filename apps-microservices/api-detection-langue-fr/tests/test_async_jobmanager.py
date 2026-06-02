import asyncio
import types
import pytest

from app.core.async_jobs import JobManager, JobStore, _JobCapacityExceeded, _JobsDisabled
from app.models.schemas import BatchItem, BatchCounts, DetectionResponse, DetectionMode
from tests.test_async_jobs import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None):
    return types.SimpleNamespace(
        items=[BatchItem(url=u) for u in items], mode=DetectionMode.COMPLETE,
        proxy_url=None, use_nlp_detection=True, force_refresh=False,
        max_concurrency=10, homepage_fallback=True, client_job_id=client_job_id,
    )


async def _instant_runner(items, mode, opts, cb):
    cb(len(items))
    results = [DetectionResponse(ok=True, url=i.url, method="test") for i in items]
    return results, BatchCounts(success_count=len(items), failed_count=0, error_count=0)


@pytest.mark.asyncio
async def test_submit_completes_with_authoritative_counts():
    jm = JobManager(JobStore(None, client=FakeRedis()), _instant_runner, _settings())
    job_id, code = await jm.submit(_req(["https://a.fr", "https://b.fr"]))
    assert code == 202
    await asyncio.gather(*list(jm._job_tasks.values()))
    rec = await jm.get_record(job_id)
    assert rec["status"] == "completed" and rec["success_count"] == 2 and rec["done"] == 2


@pytest.mark.asyncio
async def test_idempotent_concurrent_submit_spawns_once():
    store = JobStore(None, client=FakeRedis())
    spawns = {"n": 0}
    async def counting_runner(items, mode, opts, cb):
        spawns["n"] += 1
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(store, counting_runner, _settings())
    (id1, _), (id2, _) = await asyncio.gather(
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
    )
    assert id1 == id2
    await asyncio.gather(*list(jm._job_tasks.values()))
    assert spawns["n"] == 1


@pytest.mark.asyncio
async def test_capacity_rejected():
    async def slow_runner(items, mode, opts, cb):
        await asyncio.sleep(0.2)
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(JobStore(None, client=FakeRedis()), slow_runner, _settings(MAX_ACTIVE_JOBS=1))
    await jm.submit(_req(["https://a.fr"]))
    with pytest.raises(_JobCapacityExceeded):
        await jm.submit(_req(["https://b.fr"]))
    await asyncio.gather(*list(jm._job_tasks.values()))


@pytest.mark.asyncio
async def test_disabled():
    jm = JobManager(JobStore(None, client=FakeRedis()), _instant_runner, _settings(ASYNC_JOBS_ENABLED=False))
    with pytest.raises(_JobsDisabled):
        await jm.submit(_req(["https://a.fr"]))


@pytest.mark.asyncio
async def test_shutdown_marks_running_failed():
    started = asyncio.Event()
    async def hang_runner(items, mode, opts, cb):
        started.set()
        await asyncio.sleep(60)
    jm = JobManager(JobStore(None, client=FakeRedis()), hang_runner, _settings())
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    await started.wait()
    await jm.shutdown()
    rec = await jm.get_record(job_id)
    assert rec["status"] == "failed" and rec["error"] == "service_shutdown"
