"""F3 (décision produit 2026-06-12): gen-1 stash carry + resume-on-start.

Decided rule: the gen-1 stashed_at carry + resume-on-start unstash apply for
ANY prior status (stopped, finished, failed, ...) — operators commonly continue
a FINISHED crawl (e.g. post-webhook treatment broke). The ONLY exception is an
explicit clean-restart intent: params["dropdata"] truthy (operator dropData=1),
where unstash-then-drop would waste a GCS download — there the gen-1 stashed_at
is dropped (warning logged) and the unstash is skipped.

Safety: the stale-tar-overwrite hazard (incident 2026-06-10, blobs 6430/6690)
requires stashed_at to survive UNconsumed into the gen-2 terminal blob. The
unconditional resume CONSUMES it at start (unstash clears stashed_at + deletes
the GCS tar), so the hazard is closed by consumption, not by status gating.

Also pins that _cleanup_stale_state_for_relaunch removes a stale
_completion_marker.json from a reused storage dir on every start.

Setup mirrors tests/test_auto_stash_resume_on_start.py: drives start_crawl past
the capacity probes + lock, then a stubbed (or wrapped, for the marker test)
_cleanup_stale_state_for_relaunch raises _Sentinel to stop before a real
subprocess spawns.
"""
import logging
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


async def _call_start(manager, params=None):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None,
        params=params if params is not None else {},
        is_restart=False,
    )


def _written_job_data(cache_mocks):
    return [c.args[1] for c in cache_mocks["set_json"].await_args_list if len(c.args) > 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_status", ["finished", "failed", "stopped"])
async def test_fresh_start_carries_stashed_at_and_unstashes_for_any_prior_status(
        monkeypatch, tmp_path, prior_status):
    """Décision 2026-06-12: stashed_at carried + resume-on-start unstash invoked
    for ANY gen-1 status (continuing a finished crawl is a common operator move,
    e.g. post-webhook treatment broke). The stale-tar hazard is closed because
    the unstash CONSUMES the stash at start (clears stashed_at, deletes the tar)."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record(prior_status))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager)
    manager.unstash_crawl.assert_awaited_once()
    written = _written_job_data(cache_mocks)
    assert any(d.get("stashed_at") == STASHED_AT for d in written), \
        f"fresh job_data write must preserve stashed_at for a '{prior_status}' prior"


@pytest.mark.asyncio
@pytest.mark.parametrize("dropdata_value", [True, 1])
async def test_fresh_start_drops_gen1_stashed_at_on_explicit_dropdata(
        monkeypatch, tmp_path, caplog, dropdata_value):
    """Explicit dropData (clean-restart intent — BO sends 1): stashed_at must NOT
    be carried into the fresh record, the resume-on-start unstash must NOT run
    (unstash-then-drop would waste a GCS download), and a warning is logged."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record("finished"))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with caplog.at_level(logging.WARNING, logger="app.core.crawler_manager"):
        with pytest.raises(_Sentinel):
            await _call_start(manager, params={"dropdata": dropdata_value})
    manager.unstash_crawl.assert_not_called()
    written = _written_job_data(cache_mocks)
    assert written, "start_crawl must have written the fresh job_data"
    assert all("stashed_at" not in d for d in written), \
        "gen-1 stashed_at must be dropped on explicit dropdata"
    assert "dropping gen-1 stashed_at" in caplog.text and "dropdata" in caplog.text, \
        "the drop must be logged as a warning"


# --- F3 follow-up (décision 2026-06-12): dropData purge aussi le tar GCS gen-1 ---
# A dropData start over a stashed gen-1 must ALSO request deletion of the GCS
# stash tar (fresh start = no stale data anywhere). Redis is already clean (the
# fresh blob never carries stashed_at); the tar deletion reuses the unstash
# phase-2 primitive: write {id}.unstash-confirmed into
# STASH_DOWNLOAD_RESULTS_PATH — the host daemon (DELETE_AFTER_DOWNLOAD=true)
# scans for it independently of any .request, runs `gcloud storage rm` and
# writes {id}.unstash-cleanup-done. Fire-and-forget + fail-open: the start must
# NEVER block on (or fail because of) GCS cleanup.


@pytest.mark.asyncio
async def test_dropdata_over_stashed_gen1_requests_gcs_tar_deletion(monkeypatch, tmp_path):
    """dropData start over {finished, stashed_at}: the tar-deletion primitive is
    invoked for this crawl_id, the fresh writes still drop stashed_at, and the
    resume-on-start unstash is still skipped (no wasted GCS download)."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record("finished"))
    manager.unstash_crawl = AsyncMock(return_value={"status": "unstashed"})
    manager._request_stash_tar_deletion = AsyncMock(return_value=True)
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager, params={"dropdata": 1})
    manager._request_stash_tar_deletion.assert_awaited_once_with("900")
    manager.unstash_crawl.assert_not_called()
    written = _written_job_data(cache_mocks)
    assert written, "start_crawl must have written the fresh job_data"
    assert all("stashed_at" not in d for d in written), \
        "gen-1 stashed_at must still be dropped on explicit dropdata"


@pytest.mark.asyncio
async def test_dropdata_tar_deletion_failure_is_fail_open(monkeypatch, tmp_path, caplog):
    """The deletion primitive raising must NEVER block the start: the start
    proceeds (reaches the post-deletion Sentinel) and a warning is logged."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record("finished"))
    manager.unstash_crawl = AsyncMock()
    manager._request_stash_tar_deletion = AsyncMock(side_effect=RuntimeError("daemon dir gone"))
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with caplog.at_level(logging.WARNING, logger="app.core.crawler_manager"):
        with pytest.raises(_Sentinel):  # Sentinel == start ran PAST the deletion request
            await _call_start(manager, params={"dropdata": True})
    manager._request_stash_tar_deletion.assert_awaited_once()
    assert "deletion request raised" in caplog.text and "fail-open" in caplog.text, \
        "the swallowed deletion failure must be logged as a warning"


@pytest.mark.asyncio
async def test_dropdata_tar_deletion_skipped_when_unstash_lock_held(
        monkeypatch, tmp_path, caplog):
    """A stash/unstash in flight (lock key present) must skip the deletion
    (tar stays orphan-inert) with a warning — and the start still proceeds.
    Exercises the REAL helper: no .unstash-confirmed marker may be written."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, _prior_record("finished"))
    manager.unstash_crawl = AsyncMock()
    results_dir = tmp_path / "stash_results"
    results_dir.mkdir()
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_RESULTS_PATH", str(results_dir),
                        raising=False)
    crawler_manager.cache_service.redis_client.exists = AsyncMock(
        side_effect=lambda key: 1 if key == "unstash_lock:900" else 0)
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with caplog.at_level(logging.WARNING, logger="app.core.crawler_manager"):
        with pytest.raises(_Sentinel):
            await _call_start(manager, params={"dropdata": 1})
    assert not (results_dir / "900.unstash-confirmed").exists(), \
        "no deletion marker may be written while an unstash is in flight"
    assert "skipping GCS stash tar deletion" in caplog.text and "unstash" in caplog.text
    written = _written_job_data(cache_mocks)
    assert written and all("stashed_at" not in d for d in written)


@pytest.mark.asyncio
async def test_dropdata_without_prior_stash_does_not_request_deletion(monkeypatch, tmp_path):
    """dropData over a prior WITHOUT stashed_at: no tar exists, no deletion attempt."""
    prior = {"crawl_id": "900", "status": "finished", "domain": "x.fr",
             "storage_path": "/app/storage/900"}  # no stashed_at
    manager, cache_mocks = _setup(monkeypatch, tmp_path, prior)
    manager.unstash_crawl = AsyncMock()
    manager._request_stash_tar_deletion = AsyncMock()
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    with pytest.raises(_Sentinel):
        await _call_start(manager, params={"dropdata": 1})
    manager._request_stash_tar_deletion.assert_not_called()
    manager.unstash_crawl.assert_not_called()


@pytest.mark.asyncio
async def test_request_stash_tar_deletion_writes_confirm_marker_and_clears_stale_ack(
        monkeypatch, tmp_path):
    """Helper pin (real primitive): with no locks held it writes
    {id}.unstash-confirmed (content = crawl_id) into STASH_DOWNLOAD_RESULTS_PATH
    and pre-cleans a stale {id}.unstash-cleanup-done (a leftover daemon ack from
    a previous fire-and-forget would fool the NEXT unstash's phase-2 polling)."""
    manager, _ = _setup(monkeypatch, tmp_path, None)
    results_dir = tmp_path / "stash_results"
    results_dir.mkdir()
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_RESULTS_PATH", str(results_dir),
                        raising=False)
    monkeypatch.setattr(manager, "_verify_bind_mount", lambda path, label: None)
    crawler_manager.cache_service.redis_client.exists = AsyncMock(return_value=0)
    stale_ack = results_dir / "900.unstash-cleanup-done"
    stale_ack.write_text("stale")

    assert await manager._request_stash_tar_deletion("900") is True

    confirm = results_dir / "900.unstash-confirmed"
    assert confirm.exists() and confirm.read_text() == "900"
    assert not stale_ack.exists(), "stale daemon ack must be pre-cleaned"


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
