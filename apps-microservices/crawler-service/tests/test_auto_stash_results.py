"""Unit tests for /results transparent unstash (auto-stash P1, Task 2)."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager
from app.schemas.crawler import IncludeInArchive


@pytest.fixture
def manager(monkeypatch):
    mock = MagicMock()
    mock.get_json = AsyncMock()
    mock.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return CrawlerManager(), mock


@pytest.mark.asyncio
async def test_results_unstashes_then_serves(manager):
    mgr, cache = manager
    job = {"crawl_id": "7", "status": "finished", "stashed_at": "2026-01-01T00:00:00",
           "storage_path": "/app/storage/7", "domain": "x.fr"}
    cache.get_json.return_value = {**job, "stashed_at": None}
    mgr.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    with patch.object(mgr, "_generate_archive_sync", return_value="/tmp/7.tar.gz"):
        path, is_temp = await mgr.get_results_archive(job, [IncludeInArchive.DATASET])
    mgr.unstash_crawl.assert_awaited_once()
    # Re-read MUST happen with the correct key (proves the refresh fires).
    cache.get_json.assert_awaited_once_with(f"{cm_module.CRAWL_JOB_PREFIX}7")
    assert path == "/tmp/7.tar.gz" and is_temp is False


@pytest.mark.asyncio
async def test_results_502_when_job_vanishes_after_unstash(manager):
    mgr, cache = manager
    job = {"crawl_id": "7", "status": "finished", "stashed_at": "t", "storage_path": "/s", "domain": "x"}
    mgr.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    cache.get_json.return_value = None  # key vanished after unstash
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, [IncludeInArchive.DATASET])
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_results_propagates_unstash_failure(manager):
    mgr, cache = manager
    job = {"crawl_id": "7", "status": "finished", "stashed_at": "t", "storage_path": "/s", "domain": "x"}
    mgr.unstash_crawl = AsyncMock(side_effect=HTTPException(status_code=502, detail="x"))
    with pytest.raises(HTTPException) as exc:
        await mgr.get_results_archive(job, [IncludeInArchive.DATASET])
    assert exc.value.status_code == 502
