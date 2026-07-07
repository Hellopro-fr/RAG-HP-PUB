# tests/test_admin_job_dump.py
"""Tests for GET /admin/job/{crawl_id} (raw blob + locks + node stats)."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


JOB = {
    "crawl_id": "42", "status": "failed", "failure_cause": "progress_stalled",
    "oom_restart_count": 1, "replica_id": "r-abc", "pid": 123,
    "callback_url": "http://bo/webhook", "failure_callback_url": "http://bo/fail",
    "params": {"crawlMode": "update", "proxyapify": "http://user:pass@proxy"},
}


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)

    async def fake_dep(crawl_id: str):
        return dict(JOB)

    app.dependency_overrides[get_job_or_recover] = fake_dep

    fake = AsyncMock()

    async def fake_get(key):
        return {"stash_lock:42": "r-abc", "reconcile_leader_lock": "r-xyz"}.get(key)

    fake.get = AsyncMock(side_effect=fake_get)
    fake.ttl = AsyncMock(return_value=1543)
    fake.hgetall = AsyncMock(return_value={"filtered_qm": "12", "processed": "300"})
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    return TestClient(app)


def test_dump_exposes_failure_fields_and_redacts_secrets(client):
    body = client.get("/admin/job/42").json()
    assert body["job"]["failure_cause"] == "progress_stalled"
    assert body["job"]["oom_restart_count"] == 1
    assert body["job"]["callback_url"] == "<redacted>"
    assert body["job"]["failure_callback_url"] == "<redacted>"
    assert body["job"]["params"]["proxyapify"] == "<redacted>"
    assert body["job"]["params"]["crawlMode"] == "update"


def test_dump_lists_held_locks_with_ttl(client):
    body = client.get("/admin/job/42").json()
    assert body["locks"] == {"stash_lock:42": {"value": "r-abc", "ttl_seconds": 1543}}
    assert body["reconcile_leader"] == "r-xyz"
    assert body["node_stats"]["filtered_qm"] == "12"


def test_503_when_redis_down(client, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert client.get("/admin/job/42").status_code == 503
