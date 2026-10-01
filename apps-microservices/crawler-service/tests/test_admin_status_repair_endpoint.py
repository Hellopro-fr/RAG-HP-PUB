# tests/test_admin_status_repair_endpoint.py
"""GET /admin/archived-status-repair — the dry-run for the repair pass.

Read-only by construction. The four existing /admin/* routes that take
Depends(get_job_or_recover) can write through its recovery path; this one must
not, so the contract is asserted rather than assumed.
"""
import json
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

BLOBS = {
    # candidate: finished, not stashed, in the list, snapshot newer than log
    "crawl_job:6712": {"crawl_id": "6712", "status": "finished",
                       "storage_path": "/app/storage/6712"},
    # rejected by condition 1
    "crawl_job:6713": {"crawl_id": "6713", "status": "archived",
                       "storage_path": "/app/storage/6713"},
    # rejected by condition 2
    "crawl_job:6714": {"crawl_id": "6714", "status": "finished",
                       "stashed_at": "2026-08-01T00:00:00",
                       "storage_path": "/app/storage/6714"},
    # rejected by condition 3 -> also the stash_only_hint population
    "crawl_job:6715": {"crawl_id": "6715", "status": "finished",
                       "storage_path": "/app/storage/6715"},
}


def _getmtime(path):
    if path.endswith("_status_snapshot.json"):
        return 200.0
    if path.endswith("crawler.log"):
        return 100.0
    raise FileNotFoundError(path)


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    fake = MagicMock()

    async def _scan_iter(match=None, count=None):
        for k in BLOBS:
            yield k

    fake.scan_iter = _scan_iter
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = AsyncMock(return_value=[json.dumps(b) for b in BLOBS.values()])
    fake.pipeline = MagicMock(return_value=pipe)
    fake.exists = AsyncMock(return_value=0)

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    return TestClient(app)


def test_reports_candidates_and_buckets(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712", "6713", "6714"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair").json()

    assert body["verified_list_present"] is True
    assert body["verified_ids_count"] == 3
    assert body["scanned"] == 4
    assert body["candidates"] == ["6712"]
    assert body["candidates_count"] == 1
    assert body["rejected"]["not_finished"] == 1      # 6713
    assert body["rejected"]["stashed"] == 1           # 6714
    assert body["rejected"]["not_in_gcs_list"] == 1   # 6715
    assert body["stash_only_hint"] == 1               # 6715 fails only condition 3


def test_no_allowlist_yields_no_candidates(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value=None), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair").json()
    assert body["verified_list_present"] is False
    assert body["candidates_count"] == 0


def test_stash_only_hint_disabled_without_allowlist(client):
    """With no allowlist at all, every finished/non-stashed blob fails
    condition 3 (verified_ids=set()) — stash_only_hint would otherwise count
    ALL of them, a meaningless "hint" indistinguishable from "we have zero
    evidence about anything". It must fire only once a real (possibly empty)
    allowlist was actually loaded. The rejected["not_in_gcs_list"] bucket
    itself stays an accurate classification either way, so it is NOT gated
    the same way — gating it too would silently drop those blobs from the
    scanned/rejected/skipped reconciliation."""
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value=None), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair").json()
    assert body["stash_only_hint"] == 0
    assert body["rejected"]["not_in_gcs_list"] == 2  # 6712 + 6715


def test_limit_truncates(client):
    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = client.get("/admin/archived-status-repair?limit=2").json()
    assert body["scanned"] == 2
    assert body["truncated"] is True


def test_endpoint_writes_nothing(client):
    from app.core.crawler_manager import crawler_manager
    from common_utils.redis import cache_service
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime), \
         patch.object(cache_service, "set_json", AsyncMock()) as sj, \
         patch.object(type(crawler_manager), "_mark_as_archived", AsyncMock()) as mark:
        client.get("/admin/archived-status-repair")
    sj.assert_not_awaited()
    mark.assert_not_awaited()


def test_503_when_redis_down(client, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert client.get("/admin/archived-status-repair").status_code == 503


def test_503_when_scan_iter_fails(monkeypatch):
    """A mid-request Redis drop during the scan must be a 503 with a clean
    detail, matching the endpoint's own stated contract (it justifies NOT
    using scan_keys_by_prefix precisely because that helper swallows errors
    into a false zero instead of a 503) — not an unwrapped 500."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    fake = MagicMock()

    async def _broken_scan_iter(match=None, count=None):
        raise ConnectionError("redis gone")
        yield  # pragma: no cover - makes this an async generator

    fake.scan_iter = _broken_scan_iter
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    resp = TestClient(app).get("/admin/archived-status-repair")
    assert resp.status_code == 503


def test_503_when_pipeline_execute_fails(monkeypatch):
    """Same contract, for the failure window between listing keys and
    reading their values."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    fake = MagicMock()

    async def _scan_iter(match=None, count=None):
        yield "crawl_job:6712"

    fake.scan_iter = _scan_iter
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = AsyncMock(side_effect=ConnectionError("redis gone"))
    fake.pipeline = MagicMock(return_value=pipe)
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    resp = TestClient(app).get("/admin/archived-status-repair")
    assert resp.status_code == 503


def test_skipped_counter_reconciles_scanned(monkeypatch):
    """Blobs that fail to parse or lack crawl_id must not be dropped
    silently — the operator does arithmetic on these counts before
    authorising a destructive campaign, so scanned must equal
    candidates_count + sum(rejected.values()) + unreadable_sidecars +
    skipped."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    raws = [
        json.dumps({"crawl_id": "6712", "status": "finished",
                    "storage_path": "/app/storage/6712"}),
        "not-json{{{",                      # unparsable
        json.dumps({"status": "finished"}),  # missing crawl_id
        None,                                 # vanished between scan and get
    ]

    fake = MagicMock()

    async def _scan_iter(match=None, count=None):
        for i in range(len(raws)):
            yield f"crawl_job:{i}"

    fake.scan_iter = _scan_iter
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = AsyncMock(return_value=raws)
    fake.pipeline = MagicMock(return_value=pipe)
    fake.exists = AsyncMock(return_value=0)

    from app.core.crawler_manager import crawler_manager
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"6712"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime):
        body = TestClient(app).get("/admin/archived-status-repair").json()

    assert body["scanned"] == len(raws)
    assert body["skipped"] == 3  # unparsable + missing crawl_id + vanished
    total = (body["candidates_count"] + sum(body["rejected"].values())
             + body["unreadable_sidecars"] + body["skipped"])
    assert total == body["scanned"]


def test_recent_snapshot_lands_in_snapshot_too_recent_bucket(monkeypatch):
    """SNAPSHOT_TOO_RECENT (condition 6), end to end through the endpoint: a
    snapshot rewritten within ARCHIVED_RECLEAN_MIN_AGE_SECONDS (default
    86400s) means an archive is in flight or just failed mid-tar, so the blob
    must land in rejected['snapshot_too_recent'] and NOT in candidates.
    Self-contained (own app/fake redis) rather than the shared BLOBS/client
    fixture, so the module-level _getmtime's fixed 200.0/100.0 pair — ~1.8e9
    seconds old, clearing the age gate by accident — isn't reused here; the
    mtimes are built relative to time.time() instead."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)

    now = time.time()
    blob = {"crawl_id": "9001", "status": "finished", "storage_path": "/app/storage/9001"}

    def _getmtime_recent(path):
        if path.endswith("_status_snapshot.json"):
            return now - 3600  # 1h old, well under the 86400s default
        if path.endswith("crawler.log"):
            return now - 7200  # older than the snapshot
        raise FileNotFoundError(path)

    fake = MagicMock()

    async def _scan_iter(match=None, count=None):
        yield "crawl_job:9001"

    fake.scan_iter = _scan_iter
    pipe = MagicMock()
    pipe.get = MagicMock()
    pipe.execute = AsyncMock(return_value=[json.dumps(blob)])
    fake.pipeline = MagicMock(return_value=pipe)
    fake.exists = AsyncMock(return_value=0)

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    from app.core.crawler_manager import crawler_manager
    with patch.object(type(crawler_manager), "_load_reclean_allowlist",
                      return_value={"9001"}), \
         patch("app.router.admin.os.path.getmtime", side_effect=_getmtime_recent):
        body = TestClient(app).get("/admin/archived-status-repair").json()

    assert body["candidates"] == []
    assert body["candidates_count"] == 0
    assert body["rejected"]["snapshot_too_recent"] == 1


def test_does_not_depend_on_get_job_or_recover():
    import inspect
    from app.router import admin
    src = inspect.getsource(admin.archived_status_repair_dry_run)
    assert "get_job_or_recover" not in src, (
        "the dry-run must not route through the dependency whose recovery path "
        "writes — that is the very bug being repaired"
    )
