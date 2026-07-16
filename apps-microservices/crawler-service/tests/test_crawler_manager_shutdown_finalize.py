"""Unit tests for the shutdown finalization-window guard in crawler_manager.py,
plus its recovery-side twin in the reconcile stale-detection branch.

Incident 2026-07-03, crawl 4296-362-1782907272: the Node crawler wrote
_exit_reason.json with reason="COMPLETED" then was killed mid-flush by a
service restart. _cleanup_running_job unconditionally marked it failed and
sent a FAILURE webhook, even though the crawl's work was actually done.

These tests cover:
  - _cleanup_running_job checking the exit-reason sidecar before deciding
    failed vs. finished (shutdown guard).
  - _exit_reason_completed_and_fresh, the freshness-aware predicate shared
    by the shutdown guard and the reconcile crash-window heal: a stale
    sidecar left over from a PREVIOUS run of the same crawl_id must never
    qualify a half-done run as finished.
  - _finalize_completed_job, the finished-finalization extracted so both
    call sites share it.
"""
import inspect
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
        # Older than any sidecar timestamp written by _write_exit_reason's
        # default, so the freshness check passes for the "healed" tests.
        "start_time": "2020-01-01 00:00:00",
    }


def _write_exit_reason(storage_path: str, reason: str, timestamp: str = "2026-07-03T23:28:27Z"):
    with open(os.path.join(storage_path, "_exit_reason.json"), "w") as f:
        json.dump({"reason": reason, "timestamp": timestamp}, f)


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
async def test_shutdown_ignores_stale_completed_sidecar(
    cm_instance, mock_cache_service, running_job_info, fake_process
):
    """A COMPLETED sidecar left over from a PREVIOUS run (timestamp BEFORE
    this run's start_time) must not heal the job — this run genuinely
    crashed without completing. Falls through to the failed path."""
    job_info = dict(running_job_info)
    job_info["start_time"] = "2026-07-04 00:00:00"
    _write_exit_reason(job_info["storage_path"], "COMPLETED", timestamp="2020-01-01T00:00:00Z")
    mock_cache_service.get_json.return_value = dict(job_info)

    with patch.object(cm_instance, "_kill_process_group"), \
         patch.object(cm_instance, "_publish_update", new_callable=AsyncMock), \
         patch.object(cm_instance, "_send_stop_webhook", new_callable=AsyncMock) as mock_stop, \
         patch.object(cm_instance, "_send_failure_webhook", new_callable=AsyncMock) as mock_failure:
        await cm_instance._cleanup_running_job(job_info["crawl_id"], fake_process)

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


class TestExitReasonCompletedAndFresh:
    """Unit tests for CrawlerManager._exit_reason_completed_and_fresh."""

    OLD_START = "2020-01-01 00:00:00"

    @pytest.mark.asyncio
    async def test_missing_file_returns_false(self, tmp_path):
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), self.OLD_START)
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_json_returns_false(self, tmp_path):
        (tmp_path / "_exit_reason.json").write_text("not json {")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), self.OLD_START)
        assert result is False

    @pytest.mark.asyncio
    async def test_non_completed_reason_returns_false(self, tmp_path):
        _write_exit_reason(str(tmp_path), "SIGTERM")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), self.OLD_START)
        assert result is False

    @pytest.mark.asyncio
    async def test_completed_after_start_returns_true(self, tmp_path):
        _write_exit_reason(str(tmp_path), "COMPLETED", timestamp="2026-07-03T23:28:27Z")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), self.OLD_START)
        assert result is True

    @pytest.mark.asyncio
    async def test_completed_before_start_returns_false(self, tmp_path):
        """Stale sidecar from a previous run — must not qualify a fresh crash as finished."""
        _write_exit_reason(str(tmp_path), "COMPLETED", timestamp="2020-01-01T00:00:00Z")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), "2026-07-04 00:00:00")
        assert result is False

    @pytest.mark.asyncio
    async def test_completed_missing_timestamp_returns_false(self, tmp_path):
        (tmp_path / "_exit_reason.json").write_text(json.dumps({"reason": "COMPLETED"}))
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), self.OLD_START)
        assert result is False

    @pytest.mark.asyncio
    async def test_missing_job_start_time_returns_false(self, tmp_path):
        _write_exit_reason(str(tmp_path), "COMPLETED", timestamp="2026-07-03T23:28:27Z")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(str(tmp_path), None)
        assert result is False

    @pytest.mark.asyncio
    async def test_prod_timestamp_formats_z_suffix_vs_space_separated(self, tmp_path):
        """Real prod formats: Node writes Z-suffixed ISO, Python start_time is
        space-separated naive UTC (str(datetime.utcnow()))."""
        _write_exit_reason(str(tmp_path), "COMPLETED", timestamp="2026-07-04T19:53:38.639Z")
        manager = CrawlerManager()
        result = await manager._exit_reason_completed_and_fresh(
            str(tmp_path), "2026-07-04 18:44:57.769734")
        assert result is True


class TestFinalizeCompletedJob:
    """Isolated state assertions for _finalize_completed_job — the shared
    finished-finalization used by both the shutdown guard and the reconcile
    crash-window heal. Does NOT send the stop webhook (callers do, each with
    different delivery semantics); asserted here by absence of any webhook
    call on the manager."""

    @pytest.mark.asyncio
    async def test_finalizes_state_without_sending_webhook(
        self, cm_instance, mock_cache_service, running_job_info
    ):
        job_key = f"{cm_module.CRAWL_JOB_PREFIX}{running_job_info['crawl_id']}"
        job_info = dict(running_job_info)

        with patch.object(cm_instance, "_publish_update", new_callable=AsyncMock) as mock_publish, \
             patch.object(cm_instance, "_send_stop_webhook", new_callable=AsyncMock) as mock_stop:
            await cm_instance._finalize_completed_job(
                job_info["crawl_id"], job_key, job_info, healed_by="test heal reason")

        assert job_info["status"] == "finished"
        assert job_info["shutdown_reason"] == "test heal reason"
        assert "last_heartbeat" not in job_info

        mock_cache_service.set_json.assert_awaited_once_with(job_key, job_info)
        mock_cache_service.delete_key.assert_awaited_once_with(
            f"{cm_module.CRAWL_LOCK_PREFIX}{job_info['crawl_id']}")
        mock_cache_service.safe_decrement_key.assert_awaited_once_with(cm_module.CRAWL_RUNNING_COUNT_KEY)
        mock_publish.assert_awaited_once_with(job_info["crawl_id"], "finished")
        mock_stop.assert_not_awaited()

        marker_path = os.path.join(job_info["storage_path"], "_completion_marker.json")
        with open(marker_path) as f:
            marker = json.load(f)
        assert marker["final_status"] == "finished"
        assert marker["healed_from_exit_reason"] is True

    @pytest.mark.asyncio
    async def test_drops_stale_last_heartbeat(
        self, cm_instance, mock_cache_service, running_job_info
    ):
        job_info = dict(running_job_info)
        job_info["last_heartbeat"] = "2020-01-01T00:00:00"

        with patch.object(cm_instance, "_publish_update", new_callable=AsyncMock):
            await cm_instance._finalize_completed_job(
                job_info["crawl_id"], "any_key", job_info, healed_by="x")

        assert "last_heartbeat" not in job_info


class TestReconcileStaleHealWiring:
    """The reconcile crash-window heal cannot be exercised end-to-end here:
    _reconcile_locked calls os.uname() (POSIX-only — fails on this Windows
    dev box) and drives a real redis pipeline (get/execute chain), and no
    fixture for either exists in this test suite yet (same gap noted by
    TestStaleHandlerCompletionMarker above _reconcile_locked's other guard).
    These are honest source-inspection checks that the wiring exists and is
    positioned/ordered/guarded correctly — NOT a substitute for a real
    invocation test.
    """

    def test_heal_check_present_and_ordered_before_failure_marking(self):
        source = inspect.getsource(cm_module.CrawlerManager._reconcile_locked)
        heal_idx = source.find("_exit_reason_completed_and_fresh")
        finalize_idx = source.find("_finalize_completed_job")
        failure_marking_idx = source.find('Marking as failed')

        assert heal_idx != -1, "_reconcile_locked must call _exit_reason_completed_and_fresh"
        assert finalize_idx != -1, "_reconcile_locked must call _finalize_completed_job on heal"
        assert failure_marking_idx != -1, "expected failure-marking log line not found (source drifted)"
        assert heal_idx < failure_marking_idx, (
            "heal check must run BEFORE the stale job is marked failed"
        )
        assert finalize_idx < failure_marking_idx

    def test_heal_scoped_to_non_stopping_and_continues(self):
        source = inspect.getsource(cm_module.CrawlerManager._reconcile_locked)
        assert "not is_stopping and await self._exit_reason_completed_and_fresh" in source, (
            "heal must be gated on 'not is_stopping' — a stopping job's webhook "
            "was already sent by the stop request"
        )
        # The heal branch must `continue` so the stale branch's own
        # decrement/webhook (further down) never double-fires.
        heal_pos = source.find("not is_stopping and await self._exit_reason_completed_and_fresh")
        next_continue_pos = source.find("continue", heal_pos)
        next_marking_pos = source.find("Marking as failed", heal_pos)
        assert next_continue_pos != -1 and next_continue_pos < next_marking_pos, (
            "heal branch must continue before reaching the failed-marking code"
        )

    def test_heal_dispatches_stop_webhook_via_create_task_not_shutdown(self):
        source = inspect.getsource(cm_module.CrawlerManager._reconcile_locked)
        assert 'asyncio.create_task(self._send_stop_webhook(job_data, "finished", shutdown=False))' in source, (
            "reconcile must NOT await _send_stop_webhook inline (durable retry path "
            "can take up to ~155s and must not hold the reconcile leader lock) — "
            "mirror how the stale branch dispatches its own failure webhook via "
            "asyncio.create_task"
        )
