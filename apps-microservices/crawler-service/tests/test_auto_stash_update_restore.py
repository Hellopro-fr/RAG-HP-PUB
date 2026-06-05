"""Unit tests for update-mode stashed-previous-crawl restore (auto-stash P1, Task 4)."""
from collections import namedtuple
from unittest.mock import AsyncMock, patch
import pytest

from fastapi import HTTPException

from app.core.crawler_manager import CrawlerManager


@pytest.mark.asyncio
async def test_restore_previous_routes_stashed_to_unstash():
    mgr = CrawlerManager()
    mgr.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    mgr._restore_archived_crawl = AsyncMock()
    prev = {"crawl_id": "100", "status": "finished", "stashed_at": "2026-01-01T00:00:00"}
    await mgr._restore_previous_crawl(prev, has_local_data=False)
    mgr.unstash_crawl.assert_awaited_once_with(prev)
    mgr._restore_archived_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_restore_previous_routes_archived_to_archive_restore():
    mgr = CrawlerManager()
    mgr.unstash_crawl = AsyncMock()
    mgr._restore_archived_crawl = AsyncMock()
    prev = {"crawl_id": "101", "status": "archived"}
    await mgr._restore_previous_crawl(prev, has_local_data=False)
    mgr._restore_archived_crawl.assert_awaited_once_with("101")
    mgr.unstash_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_restore_previous_noop_when_local_data_present():
    mgr = CrawlerManager()
    mgr.unstash_crawl = AsyncMock()
    mgr._restore_archived_crawl = AsyncMock()
    prev = {"crawl_id": "102", "status": "archived"}
    await mgr._restore_previous_crawl(prev, has_local_data=True)
    mgr.unstash_crawl.assert_not_called()
    mgr._restore_archived_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_start_crawl_rollback_on_restore_failure(monkeypatch, tmp_path):
    """update-mode: non-HTTPException from _restore_previous_crawl → rollback + 503."""
    import os as _os
    from app.core import crawler_manager
    from app.core.crawler_manager import CrawlerManager
    from app.core.config import settings

    # --- stub os.uname (POSIX-only; not available on Windows) ---
    _UnameStub = namedtuple(
        "uname_result", ["sysname", "nodename", "release", "version", "machine"]
    )
    monkeypatch.setattr(
        _os,
        "uname",
        lambda: _UnameStub("Linux", "test-replica", "5.0", "#1", "x86_64"),
        raising=False,
    )

    # --- use tmp_path as storage root so os.makedirs succeeds ---
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))

    # --- mock every cache_service.* method start_crawl touches ---
    cache_mocks = {
        "get_key": AsyncMock(),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
        "get_json": AsyncMock(),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(crawler_manager.cache_service, name, mock)

    # --- lock SET NX → acquired ---
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)

    # --- capacity probes: max=10, running=1 → plenty of room ---
    cache_mocks["get_key"].side_effect = [
        "10",  # CRAWL_MAX_GLOBAL_KEY
        "1",   # CRAWL_RUNNING_COUNT_KEY
    ]
    # INCR returns 2 (well within limit)
    cache_mocks["increment_key"].return_value = 2

    # --- get_json returns stashed prev-crawl for "crawl_job:100", None otherwise ---
    stashed_prev = {
        "crawl_id": "100",
        "status": "finished",
        "stashed_at": "2026-01-01T00:00:00",
    }

    def _get_json_side_effect(key):
        if key == "crawl_job:100":
            return stashed_prev
        return None

    cache_mocks["get_json"].side_effect = _get_json_side_effect

    # --- force no local dataset files → triggers restore branch ---
    # os.path.isdir must return False for the prev_datasets_dir check (line 541)
    # but True isn't needed elsewhere for this path; patch at module level.
    monkeypatch.setattr(_os.path, "isdir", lambda path: False)

    # --- build manager ---
    manager = CrawlerManager()
    manager.local_processes = {}

    # --- stub _cleanup_stale_state_for_relaunch (async, touches filesystem) ---
    manager._cleanup_stale_state_for_relaunch = AsyncMock()

    # --- _restore_previous_crawl raises a non-HTTPException ---
    manager._restore_previous_crawl = AsyncMock(side_effect=RuntimeError("gcs down"))

    # --- exercise ---
    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="200",
            domain="example.com",
            start_url="https://example.com/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={"crawlMode": "update", "previousCrawlId": "100"},
        )

    # --- assertions ---
    assert exc_info.value.status_code == 503

    # _rollback_claim(decrement_counter=True) must have decremented the global counter
    cache_mocks["safe_decrement_key"].assert_awaited_once()
