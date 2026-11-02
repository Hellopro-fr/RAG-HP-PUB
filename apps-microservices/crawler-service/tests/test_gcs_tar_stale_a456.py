"""A456 (spec 2026-10-31 section 4.9, test spec T26): the GCS tar of a previous
generation must not be taken for the tar of a crawl relaunched with dropData.

archive_crawl's "GCS fallback" finds crawls/<id>.tar.gz (uploaded before the
domain went to status 14), marks the crawl archived and answers already_in_gcs
WITHOUT re-tarring; the BO then cleans its Ecritel copy. A dropData start now
flags the blob (gcs_tar_stale), archive_crawl skips the fallback for a flagged
crawl and tars the new data (the upload daemon's `gcloud storage cp` overwrites
crawls/<id>.tar.gz), and _mark_as_archived clears the flag.
"""
import os as _os
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import crawler_manager
from app.core.crawler_manager import CrawlerManager
from app.core.config import settings


class _Sentinel(Exception):
    """Raised by a stubbed step to stop a flow right after the point under test."""


class _NoHeartbeat:
    """Stand-in for _LockHeartbeat: no background task, no Redis."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _archive_manager(monkeypatch, tmp_path):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value=None)
    cache.set_json = AsyncMock()
    cache.redis_client = AsyncMock()
    monkeypatch.setattr(crawler_manager, "cache_service", cache)
    monkeypatch.setattr(crawler_manager, "_LockHeartbeat", _NoHeartbeat)
    archives = tmp_path / "archives"
    archives.mkdir()
    monkeypatch.setattr(settings, "ARCHIVES_SHARED_PATH", str(archives))
    m = CrawlerManager()
    m._acquire_ownership_lock = AsyncMock(return_value="replica")
    m._release_ownership_lock = AsyncMock(return_value=True)
    m._mark_as_archived = AsyncMock()
    m.cleanup_temp_download = MagicMock()
    m._retrieve_from_gcs_daemon = AsyncMock(return_value=str(tmp_path / "dl.tar.gz"))
    m._get_archives_disk_state = MagicMock(side_effect=_Sentinel())
    return m


def _finished_job(tmp_path, **extra):
    job = {"crawl_id": "900", "status": "finished", "domain": "x.fr",
           "storage_path": str(tmp_path / "storage")}
    job.update(extra)
    return job


@pytest.mark.asyncio
async def test_archive_stale_skips_gcs_fallback(monkeypatch, tmp_path):
    """Flagged crawl: no GCS lookup, no already_in_gcs, the flow reaches the
    fresh-archive pre-flight (the sentinel)."""
    m = _archive_manager(monkeypatch, tmp_path)
    with pytest.raises(_Sentinel):
        await m.archive_crawl(_finished_job(tmp_path, gcs_tar_stale=True))
    m._retrieve_from_gcs_daemon.assert_not_awaited()
    m._mark_as_archived.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_without_flag_still_uses_gcs_fallback(monkeypatch, tmp_path):
    """Witness (passes before and after the change): a crawl without the flag
    keeps the legacy fallback, so legacy crawls stuck at finished still heal."""
    m = _archive_manager(monkeypatch, tmp_path)
    result = await m.archive_crawl(_finished_job(tmp_path))
    assert result["archive_status"] == "already_in_gcs"
    m._retrieve_from_gcs_daemon.assert_awaited_once_with("900")
    m._mark_as_archived.assert_awaited_once_with("900")


def _setup(monkeypatch, tmp_path, get_json_return):
    """Copied from tests/test_start_crawl_gen1_hygiene.py: a CrawlerManager whose
    cache_service is mocked so start_crawl passes capacity + lock."""
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
    redis_mock.set = AsyncMock(return_value=True)
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)
    cache_mocks["get_key"].side_effect = ["10", "1"]
    cache_mocks["increment_key"].return_value = 2
    manager = CrawlerManager()
    manager.local_processes = {}
    monkeypatch.setattr(manager, "_cleanup_stale_state_for_relaunch",
                        AsyncMock(side_effect=_Sentinel()))
    return manager, cache_mocks


async def _call_start(manager, params):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None,
        params=params, is_restart=False,
    )


def _written_job_data(cache_mocks):
    return [c.args[1] for c in cache_mocks["set_json"].await_args_list if len(c.args) > 1]


@pytest.mark.asyncio
async def test_start_dropdata_flags_gcs_tar_stale(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)
    with pytest.raises(_Sentinel):
        await _call_start(manager, {"dropdata": True})
    written = _written_job_data(cache_mocks)
    assert written, "start_crawl must have written the fresh job_data"
    assert any(d.get("gcs_tar_stale") is True for d in written)


@pytest.mark.asyncio
async def test_start_without_dropdata_does_not_flag(monkeypatch, tmp_path):
    """Witness (passes before and after): a start that keeps its data (resume,
    update mode) never flags the blob."""
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)
    with pytest.raises(_Sentinel):
        await _call_start(manager, {})
    written = _written_job_data(cache_mocks)
    assert written, "start_crawl must have written the fresh job_data"
    assert all("gcs_tar_stale" not in d for d in written)


@pytest.mark.asyncio
async def test_mark_as_archived_clears_flag(monkeypatch, tmp_path):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value={
        "crawl_id": "900", "status": "finished", "gcs_tar_stale": True})
    cache.set_json = AsyncMock()
    monkeypatch.setattr(crawler_manager, "cache_service", cache)
    m = CrawlerManager()
    m._publish_update = AsyncMock()
    await m._mark_as_archived("900")
    written = cache.set_json.await_args.args[1]
    assert written["status"] == "archived"
    assert "gcs_tar_stale" not in written


def _relaunch_manager(monkeypatch, job_info):
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value=dict(job_info, status="restarting_oom"))
    monkeypatch.setattr(crawler_manager, "cache_service", cache)
    monkeypatch.setattr(crawler_manager.asyncio, "sleep", AsyncMock())
    m = CrawlerManager()
    m.start_crawl = AsyncMock()
    return m


def _oom_job(**extra):
    job = {"crawl_id": "900", "status": "restarting_oom", "domain": "x.fr",
           "start_url": "https://x.fr/", "callback_url": "https://cb",
           "oom_restart_count": 0, "params": {"dropdata": True}}
    job.update(extra)
    return job


@pytest.mark.asyncio
async def test_oom_relaunch_carries_gcs_tar_stale(monkeypatch):
    job = _oom_job(gcs_tar_stale=True)
    m = _relaunch_manager(monkeypatch, job)
    await m._relaunch_oom_crawl(job)
    kwargs = m.start_crawl.await_args.kwargs
    assert kwargs["params"]["dropdata"] is False
    assert kwargs["carry_gcs_tar_stale"] is True


@pytest.mark.asyncio
async def test_oom_relaunch_without_flag_does_not_carry(monkeypatch):
    """Negative control: a relaunch of a job never flagged carries nothing."""
    job = _oom_job()
    m = _relaunch_manager(monkeypatch, job)
    await m._relaunch_oom_crawl(job)
    assert m.start_crawl.await_args.kwargs["carry_gcs_tar_stale"] is False


@pytest.mark.asyncio
async def test_start_restart_with_carry_writes_flag(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)
    with pytest.raises(_Sentinel):
        await manager.start_crawl(
            domain="x.fr", start_url="https://x.fr/", crawl_id="900",
            callback_url="https://cb", failure_callback_url=None,
            params={"dropdata": False}, is_restart=True,
            oom_restart_count=1, carry_gcs_tar_stale=True)
    written = _written_job_data(cache_mocks)
    assert written
    assert any(d.get("gcs_tar_stale") is True for d in written)


@pytest.mark.asyncio
async def test_start_restart_without_carry_writes_no_flag(monkeypatch, tmp_path):
    manager, cache_mocks = _setup(monkeypatch, tmp_path, None)
    with pytest.raises(_Sentinel):
        await manager.start_crawl(
            domain="x.fr", start_url="https://x.fr/", crawl_id="900",
            callback_url="https://cb", failure_callback_url=None,
            params={"dropdata": False}, is_restart=True, oom_restart_count=1)
    written = _written_job_data(cache_mocks)
    assert written
    assert all("gcs_tar_stale" not in d for d in written)
