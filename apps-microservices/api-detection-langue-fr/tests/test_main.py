import asyncio
import types
import pytest
import httpx

from main import app
from app.core.async_jobs import JobManager, JobStore
from app.models.schemas import BatchCounts, DetectionResponse
from tests.test_async_jobs import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2, ASYNC_SUBMIT_RETRY_AFTER_S=15, ASYNC_POLL_HINT_MAX_S=30)
    base.update(over)
    return types.SimpleNamespace(**base)


async def _runner(items, mode, opts, cb):
    cb(len(items))
    return ([DetectionResponse(ok=True, url=i.url, method="test") for i in items],
            BatchCounts(len(items), 0, 0))


@pytest.mark.asyncio
async def test_submit_then_poll_completed():
    jm = JobManager(JobStore(None, client=FakeRedis()), _runner, _settings())
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        await asyncio.gather(*list(jm._job_tasks.values()))
        p = await c.get(f"/api/v1/detect-batch-async/{job_id}")
        assert p.status_code == 200 and p.json()["status"] == "completed"
        assert p.json()["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_poll_unknown_404():
    jm = JobManager(JobStore(None, client=FakeRedis()), _runner, _settings())
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/api/v1/detect-batch-async/nope")).status_code == 404


@pytest.mark.asyncio
async def test_capacity_503_has_retry_after():
    async def slow(items, mode, opts, cb):
        await asyncio.sleep(0.3)
        return ([], BatchCounts(0, 0, 0))
    jm = JobManager(JobStore(None, client=FakeRedis()), slow, _settings(MAX_ACTIVE_JOBS=1))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://b.fr"}]})
        assert r.status_code == 503 and "retry-after" in {k.lower() for k in r.headers}
    await asyncio.gather(*list(jm._job_tasks.values()))


@pytest.mark.asyncio
async def test_disabled_503_no_retry_after():
    jm = JobManager(JobStore(None, client=FakeRedis()), _runner, _settings(ASYNC_JOBS_ENABLED=False))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 503 and "retry-after" not in {k.lower() for k in r.headers}
