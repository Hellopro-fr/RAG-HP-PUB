import asyncio
import os
import types
import pytest
import httpx

import main as main_module
from main import app
from app.core.async_jobs import JobManager, JobStore
from app.models.schemas import BatchCounts, DetectionResponse
from tests.test_async_jobs import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2, ASYNC_SUBMIT_RETRY_AFTER_S=15, ASYNC_POLL_HINT_MAX_S=30,
                JOB_MAX_S=1500, TERMINAL_WRITE_BUDGET_S=60)
    base.update(over)
    return types.SimpleNamespace(**base)


async def _runner(items, mode, opts, cb):
    cb(len(items))
    return ([DetectionResponse(ok=True, url=i.url, method="test") for i in items],
            BatchCounts(len(items), 0, 0))


@pytest.mark.asyncio
async def test_submit_then_poll_completed():
    jm = JobManager(JobStore(client=FakeRedis()), _runner, _settings())
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
    jm = JobManager(JobStore(client=FakeRedis()), _runner, _settings())
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/api/v1/detect-batch-async/nope")).status_code == 404


@pytest.mark.asyncio
async def test_capacity_503_has_retry_after():
    async def slow(items, mode, opts, cb):
        await asyncio.sleep(0.3)
        return ([], BatchCounts(0, 0, 0))
    jm = JobManager(JobStore(client=FakeRedis()), slow, _settings(MAX_ACTIVE_JOBS=1))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://b.fr"}]})
        assert r.status_code == 503 and "retry-after" in {k.lower() for k in r.headers}
    await asyncio.gather(*list(jm._job_tasks.values()))


@pytest.mark.asyncio
async def test_disabled_503_no_retry_after():
    jm = JobManager(JobStore(client=FakeRedis()), _runner, _settings(ASYNC_JOBS_ENABLED=False))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 503 and "retry-after" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_unavailable_503_has_retry_after():
    """R1: Redis down at submit (ping fails -> _JobsUnavailable) must be
    retryable, same treatment as capacity — a 2s Redis restart is not the
    permanent kill-switch. _JobsDisabled (above) must stay the ONLY
    header-less 503, since the BO discriminates by header presence."""
    jm = JobManager(JobStore(client=FakeRedis(fail=True)), _runner, _settings())
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 503 and "retry-after" in {k.lower() for k in r.headers}
        assert r.json()["detail"]["retryable"] is True


@pytest.mark.asyncio
async def test_poll_redis_down_returns_503_not_404():
    """R2: poll must distinguish 'unknown job_id' (404, BO treats it as
    permanently stale) from 'Redis unreadable right now' (503+Retry-After,
    BO already retries this). JobStore.get() degrades both cases to the
    same None — submit while Redis is healthy, then fail it before polling."""
    fake = FakeRedis()
    jm = JobManager(JobStore(client=fake), _runner, _settings())
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        job_id = r.json()["job_id"]
        await asyncio.gather(*list(jm._job_tasks.values()))
        fake.fail = True  # simulate a Redis outage after the job completed
        p = await c.get(f"/api/v1/detect-batch-async/{job_id}")
        assert p.status_code == 503 and "retry-after" in {k.lower() for k in p.headers}


@pytest.mark.asyncio
async def test_lifespan_inits_shared_pool_and_bridges_redis_url(monkeypatch):
    """Lifespan must bridge settings.REDIS_URL into the process env (cache_service
    reads os.environ), init the shared pool at startup, and close it after the
    JobManager drain at shutdown."""
    calls = []

    async def fake_init():
        calls.append("init")

    async def fake_close():
        calls.append("close")

    monkeypatch.setattr(main_module, "init_redis_pool", fake_init)
    monkeypatch.setattr(main_module, "close_redis_pool", fake_close)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(main_module._settings, "REDIS_URL", "redis://from-settings:6379")

    async with main_module.lifespan(app):
        assert os.environ["REDIS_URL"] == "redis://from-settings:6379"
        assert os.environ.get("SERVICE_NAME")  # client-name default bridged too
        assert calls == ["init"]
        assert app.state.job_manager is not None
    assert calls == ["init", "close"]
