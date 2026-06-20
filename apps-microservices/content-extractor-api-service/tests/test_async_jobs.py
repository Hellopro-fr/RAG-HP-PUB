import pytest
from pydantic import ValidationError

from app.schemas.async_jobs import (
    CleanAsyncRequest, HeaderFooterAsyncRequest, AsyncJobStatusResponse,
)


def test_clean_async_request_valid():
    req = CleanAsyncRequest(items=[{"html": "<p>x</p>", "format": "text"}])
    assert req.max_concurrency == 4
    assert req.items[0].html == "<p>x</p>"


def test_clean_async_request_rejects_empty():
    with pytest.raises(ValidationError):
        CleanAsyncRequest(items=[])


def test_hf_async_request_requires_two_refs():
    with pytest.raises(ValidationError):
        HeaderFooterAsyncRequest(items=[{"main_html": "<p>m</p>", "reference_htmls": ["<p>a</p>"]}])


def test_status_response_shape():
    r = AsyncJobStatusResponse(
        job_id="j", job_type="clean", status="completed", total=1, done=1,
        results=[{"content": "x"}], poll_after_seconds=2,
    )
    assert r.error is None


import asyncio
import types

from common_utils.redis import cache_service
from app.core.async_jobs import (
    JobStore, JobManager, poll_status,
    _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded,
)


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def ping(self):
        return True

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def setex(self, k, ttl, v):
        self.kv[k] = v
        return True

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, k):
        self.kv.pop(k, None)

    async def expire(self, k, ttl):
        return True


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=8, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=5)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None, max_concurrency=4, force_refresh=False):
    return types.SimpleNamespace(items=items, client_job_id=client_job_id,
                                 max_concurrency=max_concurrency, force_refresh=force_refresh)


async def _echo_runner(job_type, items, max_concurrency, force_refresh, progress_cb=None):
    out = [{"echo": i} for i in range(len(items))]
    if progress_cb:
        progress_cb(len(items))
    return out


def test_poll_status_stale():
    rec = {"status": "running", "created_at": 0, "last_activity": 0}
    assert poll_status(rec, now=1000, stale_threshold_s=120) == "stale"
    assert poll_status({"status": "completed"}, now=1000, stale_threshold_s=120) == "completed"


def test_submit_disabled(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings(ASYNC_JOBS_ENABLED=False))
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobsDisabled:
        pass


def test_submit_and_complete(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())

    async def scenario():
        job_id, code = await jm.submit("clean", _req([1, 2, 3]))
        assert code == 202
        for _ in range(50):
            rec = await jm.get_record(job_id)
            if rec and rec["status"] == "completed":
                return rec
            await asyncio.sleep(0.01)
        return await jm.get_record(job_id)

    rec = asyncio.run(scenario())
    assert rec["status"] == "completed"
    assert rec["done"] == 3
    assert len(rec["results"]) == 3


def test_idempotent_resubmit(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())

    async def scenario():
        a, ca = await jm.submit("clean", _req([1], client_job_id="K"))
        b, cb = await jm.submit("clean", _req([1], client_job_id="K"))
        return a, b, cb

    a, b, cb = asyncio.run(scenario())
    assert a == b and cb == 200


def test_capacity_exceeded(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings(MAX_ACTIVE_JOBS=0))
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobCapacityExceeded:
        pass


def test_unavailable_when_no_client(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobsUnavailable:
        pass
