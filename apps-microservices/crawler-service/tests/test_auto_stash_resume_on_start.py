"""Fix A: resume-on-start inline unstash (auto-stash follow-up).

Self-contained setup (mirrors test_auto_stash_update_restore.py): drives
start_crawl past the capacity probes + lock to the resume-on-start unstash,
then a stubbed _cleanup_stale_state_for_relaunch raises _Sentinel to stop
before a real subprocess spawns.
"""
from collections import namedtuple
from unittest.mock import AsyncMock
import os as _os

import pytest
from fastapi import HTTPException

from app.core import crawler_manager
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


class _Sentinel(Exception):
    """Raised by a stubbed step AFTER the unstash point to stop start_crawl early."""


def _stashed_record(crawl_id="900"):
    return {"crawl_id": crawl_id, "status": "stopped", "domain": "x.fr",
            "storage_path": f"/app/storage/{crawl_id}", "stashed_at": "2026-06-01T00:00:00"}


def _setup(monkeypatch, tmp_path, get_json_return):
    """Build a CrawlerManager with cache_service mocked so start_crawl passes
    capacity + lock. Returns (manager, cache_mocks). get_json_return is what
    cache_service.get_json yields for the started crawl's key."""
    _UnameStub = namedtuple("uname_result", ["sysname", "nodename", "release", "version", "machine"])
    monkeypatch.setattr(_os, "uname",
                        lambda: _UnameStub("Linux", "test-replica", "5.0", "#1", "x86_64"),
                        raising=False)
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))

    cache_mocks = {
        "get_key": AsyncMock(),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
        "get_json": AsyncMock(return_value=get_json_return),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(crawler_manager.cache_service, name, mock, raising=False)

    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)  # lock acquired
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)

    # Capacity probes: max=10, running=1 → room. INCR returns 2 (within limit).
    cache_mocks["get_key"].side_effect = ["10", "1"]
    cache_mocks["increment_key"].return_value = 2

    manager = CrawlerManager()
    manager.local_processes = {}
    return manager, cache_mocks


async def _call_start(manager, is_restart=False):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None, params={},
        is_restart=is_restart,
    )


@pytest.mark.asyncio
async def test_start_unstashes_stashed_id(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_unstash_failure_rolls_back(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())
    manager.unstash_crawl = AsyncMock(
        side_effect=HTTPException(status_code=502, detail={"error_code": "GCS_DOWNLOAD_FAILED"}))
    with pytest.raises(HTTPException) as exc:
        await _call_start(manager)
    assert exc.value.status_code == 502           # HTTPException propagates as-is
    cache_mocks["safe_decrement_key"].assert_awaited()  # rollback decremented the slot


@pytest.mark.asyncio
async def test_start_skips_unstash_when_not_stashed(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)  # fresh crawl, no prior record
    manager.unstash_crawl = AsyncMock()
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_start_skips_unstash_on_restart(monkeypatch, tmp_path):
    # is_restart skips the prior-record read entirely, so even a stashed record is ignored.
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())
    manager.unstash_crawl = AsyncMock()
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager, is_restart=True)
    manager.unstash_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_start_preserves_stashed_at_for_revalidation(monkeypatch, tmp_path):
    """The fresh job_data write must keep stashed_at so the real unstash_crawl's
    TOCTOU re-read of Redis doesn't 409 NOT_STASHED (unstash_crawl is mocked here,
    so this guards the preservation independently)."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    written = [c.args[1] for c in cache_mocks["set_json"].await_args_list if len(c.args) > 1]
    assert any(d.get("stashed_at") == "2026-06-01T00:00:00" for d in written), \
        "fresh job_data write must preserve stashed_at for unstash re-validation"
