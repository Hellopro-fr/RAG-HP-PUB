"""archive_crawl stashed-branch move (auto-stash P3, Task 12)."""
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mgr(monkeypatch, tmp_path):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value={"crawl_id": "70", "stashed_at": "t"})
    cache.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", cache)
    m = CrawlerManager()
    m._mark_as_archived = AsyncMock()
    return m, cache, tmp_path


@pytest.mark.asyncio
async def test_archive_stashed_routes_to_move(mgr):
    m, cache, _ = mgr
    m._move_stash_to_archive = AsyncMock()
    job = {"crawl_id": "70", "status": "finished", "stashed_at": "2026-01-01T00:00:00"}
    result = await m.archive_crawl(job)
    m._move_stash_to_archive.assert_awaited_once_with(job)
    assert result["archive_status"] == "pending_upload"


@pytest.mark.asyncio
async def test_archive_stashed_but_failed_does_not_move(mgr):
    """A stashed FAILED crawl must NOT take the move path; it falls through to
    the finished-only 400 guard (archive is for finished crawls only)."""
    m, cache, _ = mgr
    m._move_stash_to_archive = AsyncMock()
    job = {"crawl_id": "70", "status": "failed", "stashed_at": "2026-01-01T00:00:00"}
    with pytest.raises(HTTPException) as exc:
        await m.archive_crawl(job)
    assert exc.value.status_code == 400
    m._move_stash_to_archive.assert_not_called()


@pytest.mark.asyncio
async def test_move_success_marks_archived(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        open(os.path.join(s.MOVE_RESULTS_PATH, "70.move-done"), "w").close()
        await m._move_stash_to_archive({"crawl_id": "70"})
    m._mark_as_archived.assert_awaited_once_with("70")


@pytest.mark.asyncio
async def test_move_error_raises_502(mgr):
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 5
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        open(os.path.join(s.MOVE_RESULTS_PATH, "70.move-error"), "w").close()
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 502
        # 502 path removes BOTH the error marker and the request (no stale request).
        assert not os.path.exists(os.path.join(s.MOVE_RESULTS_PATH, "70.move-error"))
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))


@pytest.mark.asyncio
async def test_move_timeout_raises_504_and_removes_request(mgr):
    """No .move-done/.move-error within MOVE_TIMEOUT_SECONDS -> 504, and the
    stale .move-request is removed so the daemon won't later process it."""
    m, cache, tmp = mgr
    with patch("app.core.crawler_manager.settings") as s:
        s.MOVE_REQUESTS_PATH = str(tmp / "req"); s.MOVE_RESULTS_PATH = str(tmp / "res")
        s.MOVE_TIMEOUT_SECONDS = 1  # one poll tick then timeout
        os.makedirs(s.MOVE_REQUESTS_PATH); os.makedirs(s.MOVE_RESULTS_PATH)
        with pytest.raises(HTTPException) as exc:
            await m._move_stash_to_archive({"crawl_id": "70"})
        assert exc.value.status_code == 504
        assert not os.path.exists(os.path.join(s.MOVE_REQUESTS_PATH, "70.move-request"))
