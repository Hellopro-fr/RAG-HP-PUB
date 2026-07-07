"""Fix A: resume-on-start inline unstash (auto-stash follow-up).

Self-contained setup (mirrors test_auto_stash_update_restore.py): drives
start_crawl past the capacity probes + lock to the resume-on-start unstash,
then a stubbed _cleanup_stale_state_for_relaunch raises _Sentinel to stop
before a real subprocess spawns.
"""
from collections import namedtuple
from unittest.mock import AsyncMock, Mock
import os as _os
import asyncio
import copy

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
    so this guards the preservation independently). Snapshot writes at write-time:
    the resume path now pops stashed_at from the in-memory job_data right after the
    unstash, so a live await_args_list reference would no longer reflect the earlier
    write that DID carry it."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    written = []

    async def _record_set_json(key, value, *a, **k):
        written.append(copy.deepcopy(value))
    cache_mocks["set_json"].side_effect = _record_set_json
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    assert any(d.get("stashed_at") == "2026-06-01T00:00:00" for d in written), \
        "fresh job_data write must preserve stashed_at for unstash re-validation"


@pytest.mark.asyncio
async def test_start_real_unstash_passes_toctou_with_carried_stashed_at(monkeypatch, tmp_path):
    """End-to-end wiring (unstash_crawl NOT mocked): start_crawl carries stashed_at
    into the fresh record so the REAL unstash_crawl TOCTOU re-read (get_json #2)
    passes — proving the carry-forward connects across the two methods. Stops at
    _verify_bind_mount (controlled 503) right after re-validation. A carry-forward
    regression would surface here as 409 NOT_STASHED instead of 503."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)
    stashed = _stashed_record()
    fresh_carried = {**stashed, "status": "starting"}  # carry-forward keeps stashed_at
    # get_json #1 = prior-record capture in start_crawl; #2 = unstash_crawl TOCTOU re-read.
    cache_mocks["get_json"].side_effect = [stashed, fresh_carried]
    crawler_manager.cache_service.redis_client.exists = AsyncMock(return_value=False)  # no stash in progress
    # Real unstash_crawl runs; mock only the lock primitives + the bind-mount stop-point.
    manager._acquire_ownership_lock = AsyncMock(return_value="lockval")
    manager._release_ownership_lock = AsyncMock()
    manager._verify_bind_mount = Mock(
        side_effect=HTTPException(status_code=503, detail={"error_code": "BIND_MOUNT_MISSING"}))
    with pytest.raises(HTTPException) as exc:
        await _call_start(manager)
    detail = exc.value.detail
    code = detail.get("error_code") if isinstance(detail, dict) else None
    assert code == "BIND_MOUNT_MISSING"  # reached bind-mount → TOCTOU stashed_at gate passed
    assert code != "NOT_STASHED"          # carry-forward did NOT regress


@pytest.mark.asyncio
async def test_start_does_not_repersist_stashed_at_into_running_blob(monkeypatch, tmp_path):
    """Regression (incident crawl 2992-160-1780994316): after the resume-on-start
    unstash clears stashed_at in Redis, start_crawl must NOT re-persist a phantom
    stashed_at into the gen-2 'running' blob via the pid/status patch (set_json).
    A surviving stashed_at makes /results on a sibling replica re-unstash an
    already-deleted GCS stash tar → 502.

    Drives start_crawl all the way to the 'running' write (subprocess + monitor +
    publish stubbed), then asserts the persisted running blob carries no stashed_at.
    Pre-fix this FAILS (job_data still holds the carried stashed_at at the write).
    """
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _stashed_record())

    # unstash_crawl clears stashed_at in REDIS only (on a re-fetched blob), exactly
    # like the real impl — it does NOT mutate start_crawl's in-memory job_data.
    # Faithful to the bug: job_data still carries stashed_at after this returns.
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})

    # Let start_crawl run PAST the unstash to the spawn + running write.
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch", AsyncMock())
    manager._publish_update = AsyncMock()

    async def _noop_monitor(*a, **k):
        return None
    monkeypatch.setattr(manager, "_monitor_process", _noop_monitor)

    fake_proc = Mock()
    fake_proc.pid = 12345
    monkeypatch.setattr(crawler_manager.asyncio, "create_subprocess_exec",
                        AsyncMock(return_value=fake_proc))

    # Snapshot every job-blob write (deepcopy: job_data is mutated in place after the
    # first write, so a live reference would not reflect per-write state).
    writes = []

    async def _record_set_json(key, value, *a, **k):
        writes.append((key, copy.deepcopy(value)))
    cache_mocks["set_json"].side_effect = _record_set_json

    crawl_id = await _call_start(manager)
    await asyncio.sleep(0)  # let the no-op monitor task drain (avoids pending-task warning)

    assert crawl_id == "900"
    manager.unstash_crawl.assert_awaited_once()

    job_key = f"{crawler_manager.CRAWL_JOB_PREFIX}900"
    running_writes = [v for k, v in writes if k == job_key and v.get("status") == "running"]
    assert running_writes, "expected a 'running' blob write at the pid/status patch (L680)"
    assert all("stashed_at" not in v for v in running_writes), \
        "running blob must NOT carry stashed_at after the resume unstash cleared it in Redis"
