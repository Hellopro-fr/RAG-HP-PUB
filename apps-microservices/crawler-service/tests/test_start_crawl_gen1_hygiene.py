"""F3 (incident 2026-06-10): gen-1 state hygiene on fresh start_crawl.

The gen-1 stashed_at carry + resume-on-start unstash apply ONLY when the prior
blob's status is "stopped" (deliberate stop -> operator relaunch = the designed
continuation case). A prior finished/failed blob being re-crawled is a NEW
generation: inheriting its stashed_at would route a future /results through the
unstash of a stale GCS tar that OVERWRITES the fresh data (blobs 6430/6690,
tars of 2026-05-23). The orphaned GCS tar is left to the sweep/lifecycle.

Also pins that _cleanup_stale_state_for_relaunch removes a stale
_completion_marker.json from a reused storage dir on every start.

Setup mirrors tests/test_auto_stash_resume_on_start.py: drives start_crawl past
the capacity probes + lock, then a stubbed (or wrapped, for the marker test)
_cleanup_stale_state_for_relaunch raises _Sentinel to stop before a real
subprocess spawns.
"""
from collections import namedtuple
from unittest.mock import AsyncMock
import os as _os

import pytest

from app.core import crawler_manager
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


class _Sentinel(Exception):
    """Raised by a stubbed step AFTER the unstash point to stop start_crawl early."""


STASHED_AT = "2026-06-01T00:00:00"


def _prior_record(status, crawl_id="900"):
    return {"crawl_id": crawl_id, "status": status, "domain": "x.fr",
            "storage_path": f"/app/storage/{crawl_id}", "stashed_at": STASHED_AT}


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

    # Capacity probes: max=10, running=1 -> room. INCR returns 2 (within limit).
    cache_mocks["get_key"].side_effect = ["10", "1"]
    cache_mocks["increment_key"].return_value = 2

    manager = CrawlerManager()
    manager.local_processes = {}
    return manager, cache_mocks


async def _call_start(manager):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None, params={},
        is_restart=False,
    )


def _written_job_data(cache_mocks):
    return [c.args[1] for c in cache_mocks["set_json"].await_args_list if len(c.args) > 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_status", ["finished", "failed"])
async def test_fresh_start_drops_gen1_stashed_at_for_non_stopped_prior(
        monkeypatch, tmp_path, prior_status):
    """Prior blob finished/failed (incident class): stashed_at must NOT be
    carried into the fresh record, and the resume-on-start unstash must NOT run."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record(prior_status))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_not_called()
    written = _written_job_data(cache_mocks)
    assert written, "start_crawl must have written the fresh job_data"
    assert all("stashed_at" not in d for d in written), \
        f"gen-1 stashed_at must be dropped when prior status is '{prior_status}'"


@pytest.mark.asyncio
async def test_fresh_start_carries_stashed_at_and_unstashes_for_stopped_prior(
        monkeypatch, tmp_path):
    """Prior blob stopped (deliberate stop -> relaunch): stashed_at carried into
    the fresh record AND the resume-on-start unstash path is invoked."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record("stopped"))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_awaited_once()
    written = _written_job_data(cache_mocks)
    assert any(d.get("stashed_at") == STASHED_AT for d in written), \
        "fresh job_data write must preserve stashed_at for a stopped prior"


@pytest.mark.asyncio
async def test_fresh_start_removes_stale_completion_marker(monkeypatch, tmp_path):
    """Marker pin: a reused storage dir containing _completion_marker.json is
    cleaned by the REAL _cleanup_stale_state_for_relaunch on every start (the
    wrapper only stops start_crawl AFTER the real cleanup ran)."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)  # fresh crawl, no prior record
    manager.unstash_crawl = AsyncMock()

    job_storage = tmp_path / "900"
    job_storage.mkdir()
    marker = job_storage / "_completion_marker.json"
    marker.write_text('{"final_status": "finished"}')

    real_cleanup = manager._cleanup_stale_state_for_relaunch

    async def _real_cleanup_then_stop(crawl_id, storage_path):
        await real_cleanup(crawl_id, storage_path)
        raise _Sentinel()

    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch", _real_cleanup_then_stop)
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    assert not marker.exists(), \
        "_cleanup_stale_state_for_relaunch must remove the stale completion marker"
