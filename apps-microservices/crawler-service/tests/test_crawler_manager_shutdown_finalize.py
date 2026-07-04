"""Unit tests for the shutdown finalization-window guard in crawler_manager.py.

Incident 2026-07-03, crawl 4296-362-1782907272: the Node crawler wrote
_exit_reason.json with reason="COMPLETED" then was killed mid-flush by a
service restart. _cleanup_running_job unconditionally marked it failed and
sent a FAILURE webhook, even though the crawl's work was actually done.

These tests cover the fix: _cleanup_running_job must check the exit-reason
sidecar before deciding failed vs. finished.
"""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


@pytest.fixture
def mock_cache_service(monkeypatch):
    """Mock common_utils.redis.cache_service used by crawler_manager."""
    mock = MagicMock()
    mock.redis_client = AsyncMock()
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    mock.delete_key = AsyncMock()
    mock.safe_decrement_key = AsyncMock(return_value=0)
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return mock


@pytest.fixture
def cm_instance(mock_cache_service):
    return CrawlerManager()


@pytest.fixture
def fake_process():
    proc = MagicMock()
    proc.pid = 123
    proc.returncode = None
    return proc


@pytest.fixture
def running_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    return {
        "crawl_id": "4296-362-1782907272",
        "status": "running",
        "storage_path": str(storage),
        "domain": "example.com",
        "callback_url": "http://php.test/callback",
        "failure_callback_url": "http://php.test/failure",
    }


def _write_exit_reason(storage_path: str, reason: str):
    with open(os.path.join(storage_path, "_exit_reason.json"), "w") as f:
        json.dump({"reason": reason, "timestamp": "2026-07-03T23:28:27Z"}, f)


@pytest.mark.asyncio
async def test_shutdown_finalizes_completed_crawl_as_finished(
    cm_instance, mock_cache_service, running_job_info, fake_process
):
    _write_exit_reason(running_job_info["storage_path"], "COMPLETED")
    mock_cache_service.get_json.return_value = dict(running_job_info)

    with patch.object(cm_instance, "_kill_process_group") as mock_kill, \
         patch.object(cm_instance, "_publish_update", new_callable=AsyncMock) as mock_publish, \
         patch.object(cm_instance, "_send_stop_webhook", new_callable=AsyncMock) as mock_stop, \
         patch.object(cm_instance, "_send_failure_webhook", new_callable=AsyncMock) as mock_failure:
        await cm_instance._cleanup_running_job(running_job_info["crawl_id"], fake_process)

    mock_kill.assert_called_once_with(fake_process.pid)

    # Persisted blob reflects "finished", not "failed".
    persisted = mock_cache_service.set_json.call_args_list[-1].args[1]
    assert persisted["status"] == "finished"

    mock_stop.assert_awaited_once()
    stop_args, stop_kwargs = mock_stop.call_args
    assert stop_args[1] == "finished" or stop_kwargs.get("reason") == "finished"
    assert stop_kwargs.get("shutdown") is True or (len(stop_args) > 2 and stop_args[2] is True)

    mock_failure.assert_not_awaited()
    mock_publish.assert_awaited_once_with(running_job_info["crawl_id"], "finished")
    mock_cache_service.safe_decrement_key.assert_awaited_once_with(cm_module.CRAWL_RUNNING_COUNT_KEY)

    marker_path = os.path.join(running_job_info["storage_path"], "_completion_marker.json")
    assert os.path.isfile(marker_path)
    with open(marker_path) as f:
        marker = json.load(f)
    assert marker["final_status"] == "finished"
    assert marker["healed_from_exit_reason"] is True


@pytest.mark.asyncio
async def test_shutdown_still_fails_crawl_without_exit_reason(
    cm_instance, mock_cache_service, running_job_info, fake_process
):
    # No _exit_reason.json written in storage_path.
    mock_cache_service.get_json.return_value = dict(running_job_info)

    with patch.object(cm_instance, "_kill_process_group"), \
         patch.object(cm_instance, "_publish_update", new_callable=AsyncMock), \
         patch.object(cm_instance, "_send_stop_webhook", new_callable=AsyncMock) as mock_stop, \
         patch.object(cm_instance, "_send_failure_webhook", new_callable=AsyncMock) as mock_failure:
        await cm_instance._cleanup_running_job(running_job_info["crawl_id"], fake_process)

    persisted = mock_cache_service.set_json.call_args_list[-1].args[1]
    assert persisted["status"] == "failed"
    assert persisted["failure_cause"] == "service_shutdown"
    mock_failure.assert_awaited_once()
    mock_stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_still_fails_crawl_with_non_completed_reason(
    cm_instance, mock_cache_service, running_job_info, fake_process
):
    _write_exit_reason(running_job_info["storage_path"], "limitQuestionMark")
    mock_cache_service.get_json.return_value = dict(running_job_info)

    with patch.object(cm_instance, "_kill_process_group"), \
         patch.object(cm_instance, "_publish_update", new_callable=AsyncMock), \
         patch.object(cm_instance, "_send_stop_webhook", new_callable=AsyncMock) as mock_stop, \
         patch.object(cm_instance, "_send_failure_webhook", new_callable=AsyncMock) as mock_failure:
        await cm_instance._cleanup_running_job(running_job_info["crawl_id"], fake_process)

    persisted = mock_cache_service.set_json.call_args_list[-1].args[1]
    assert persisted["status"] == "failed"
    mock_failure.assert_awaited_once()
    mock_stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_relaunch_cleanup_removes_stale_exit_reason(tmp_path):
    """A relaunched crawl must not inherit the prior run's COMPLETED sidecar:
    if the service shuts down before the new run writes its own
    _exit_reason.json, the shutdown guard would wrongly finalize it as
    finished. _cleanup_stale_state_for_relaunch must purge BOTH sidecars."""
    (tmp_path / "_completion_marker.json").write_text(json.dumps({"final_status": "finished"}))
    _write_exit_reason(str(tmp_path), "COMPLETED")

    manager = CrawlerManager()
    await manager._cleanup_stale_state_for_relaunch("4296-362-1782907272", str(tmp_path))

    assert not (tmp_path / "_completion_marker.json").exists()
    assert not (tmp_path / "_exit_reason.json").exists()


class TestReadExitReasonOrNone:
    """Unit tests for CrawlerManager._read_exit_reason_or_none."""

    @pytest.mark.asyncio
    async def test_missing_file_returns_none(self, tmp_path):
        manager = CrawlerManager()
        result = await manager._read_exit_reason_or_none(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none(self, tmp_path):
        (tmp_path / "_exit_reason.json").write_text("not json {")
        manager = CrawlerManager()
        result = await manager._read_exit_reason_or_none(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_completed_reason_returned(self, tmp_path):
        (tmp_path / "_exit_reason.json").write_text(json.dumps({"reason": "COMPLETED"}))
        manager = CrawlerManager()
        result = await manager._read_exit_reason_or_none(str(tmp_path))
        assert result == "COMPLETED"

    @pytest.mark.asyncio
    async def test_non_string_reason_returns_none(self, tmp_path):
        (tmp_path / "_exit_reason.json").write_text(json.dumps({"reason": 42}))
        manager = CrawlerManager()
        result = await manager._read_exit_reason_or_none(str(tmp_path))
        assert result is None
