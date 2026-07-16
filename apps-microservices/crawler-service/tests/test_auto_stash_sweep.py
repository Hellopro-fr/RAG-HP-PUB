"""Auto-stash sweep selection + dispatch (P2, Task 8)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import pytest

from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


@pytest.fixture
def mgr():
    return CrawlerManager()


def _old_download():
    return (datetime.utcnow() - timedelta(seconds=settings.STASH_GRACE_SECONDS + 10)).isoformat()


@pytest.mark.asyncio
async def test_auto_stash_one_swallows_409(mgr):
    from fastapi import HTTPException
    mgr.stash_crawl = AsyncMock(side_effect=HTTPException(status_code=409, detail={"error_code": "ALREADY_STASHED"}))
    await mgr._auto_stash_one({"crawl_id": "1", "status": "finished"}, "grace")  # must not raise


@pytest.mark.asyncio
async def test_auto_stash_one_releases_inflight_on_success(mgr):
    mgr._auto_stash_inflight.add("5")
    mgr.stash_crawl = AsyncMock(return_value={})
    await mgr._auto_stash_one({"crawl_id": "5", "status": "finished"}, "grace")
    assert "5" not in mgr._auto_stash_inflight  # released in finally


@pytest.mark.asyncio
async def test_auto_stash_one_releases_inflight_on_failure(mgr):
    from fastapi import HTTPException
    mgr._auto_stash_inflight.add("6")
    mgr.stash_crawl = AsyncMock(side_effect=HTTPException(status_code=409, detail={}))
    await mgr._auto_stash_one({"crawl_id": "6", "status": "finished"}, "grace")
    assert "6" not in mgr._auto_stash_inflight  # released even on 409


@pytest.mark.asyncio
async def test_select_respects_cap_and_eligibility(mgr):
    jobs = [{"crawl_id": str(i), "status": "finished", "downloaded_at": _old_download(),
             "size_bytes": i} for i in range(10)]
    with patch.object(mgr, "_disk_used_pct", return_value=0):  # no pressure
        selected = mgr._select_stash_candidates(jobs, datetime.utcnow())
    assert len(selected) == settings.STASH_MAX_PER_SWEEP
    assert all(reason == "grace" for _job, reason in selected)


@pytest.mark.asyncio
async def test_disk_pressure_selects_largest(mgr):
    # None grace/timeout-eligible (fresh), but disk pressure forces top-N by size.
    jobs = [{"crawl_id": str(i), "status": "finished", "size_bytes": i,
             "downloaded_at": datetime.utcnow().isoformat()} for i in range(10)]
    with patch.object(mgr, "_disk_used_pct", return_value=99):
        selected = mgr._select_stash_candidates(jobs, datetime.utcnow())
    ids = [j["crawl_id"] for j, _r in selected]
    assert ids == ["9", "8", "7", "6", "5"]  # largest first, capped at 5
    assert all(reason == "disk_pressure" for _j, reason in selected)
