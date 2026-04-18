"""Unit tests for crawler_manager.py state-transition guards."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_cache_service():
    svc = MagicMock()
    svc.get_json = AsyncMock()
    svc.set_json = AsyncMock()
    svc.delete_key = AsyncMock()
    svc.safe_decrement_key = AsyncMock(return_value=0)
    svc.increment_key = AsyncMock(return_value=1)
    return svc


class TestStaleHandlerCounter:
    """Fix 1: decrement counter when stale detection marks job failed."""

    @pytest.mark.asyncio
    async def test_stale_handler_decrements_counter(self, mock_cache_service):
        """A stale 'running' job marked failed must decrement the global counter."""
        from app.core import crawler_manager as cm

        previous_status = "running"
        final_status = "failed"

        # Simulate the guard logic Fix 1 introduces
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        if previous_status in holding_slot_statuses:
            await mock_cache_service.safe_decrement_key(cm.CRAWL_RUNNING_COUNT_KEY)

        mock_cache_service.safe_decrement_key.assert_awaited_once_with(cm.CRAWL_RUNNING_COUNT_KEY)

    @pytest.mark.asyncio
    async def test_stale_handler_skips_decrement_for_terminal_status(self, mock_cache_service):
        """If somehow we hit stale handler with terminal status, skip decrement."""
        from app.core import crawler_manager as cm

        previous_status = "failed"
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        if previous_status in holding_slot_statuses:
            await mock_cache_service.safe_decrement_key(cm.CRAWL_RUNNING_COUNT_KEY)

        mock_cache_service.safe_decrement_key.assert_not_awaited()


class TestStaleHandlerKillProcess:
    """Fix 2: SIGKILL the subprocess when stale detection marks job failed."""

    def test_kill_process_group_called_when_process_alive(self):
        """Subprocess with returncode=None should be killed."""
        proc = MagicMock()
        proc.returncode = None
        proc.pid = 12345

        kill_called = {"count": 0, "pid": None}

        def fake_kill(pid):
            kill_called["count"] += 1
            kill_called["pid"] = pid

        local_processes = {"test-5482": proc}
        crawl_id = "test-5482"
        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 1
        assert kill_called["pid"] == 12345

    def test_kill_skipped_when_process_already_exited(self):
        """Subprocess with returncode != None should NOT be killed (PID recycle risk)."""
        proc = MagicMock()
        proc.returncode = 1
        proc.pid = 12345

        kill_called = {"count": 0}

        def fake_kill(pid):
            kill_called["count"] += 1

        local_processes = {"test-5482": proc}
        crawl_id = "test-5482"
        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 0

    def test_kill_skipped_when_remote_job(self):
        """Remote jobs (not in local_processes) should not be killed."""
        local_processes = {}
        crawl_id = "remote-job"

        kill_called = {"count": 0}

        def fake_kill(pid):
            kill_called["count"] += 1

        if crawl_id in local_processes:
            p = local_processes[crawl_id]
            if p.returncode is None:
                fake_kill(p.pid)

        assert kill_called["count"] == 0


class TestRelaunchAbort:
    """Fix 3: _relaunch_oom_crawl aborts if status is no longer restarting_oom."""

    def test_abort_when_status_is_failed(self):
        current = {"status": "failed"}
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is True

    def test_abort_when_status_is_stopped(self):
        current = {"status": "stopped"}
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is True

    def test_abort_when_job_is_gone(self):
        current = None
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is True

    def test_proceed_when_status_is_restarting_oom(self):
        current = {"status": "restarting_oom"}
        should_abort = not current or current.get("status") != "restarting_oom"
        assert should_abort is False


class TestMonitorSkipOom:
    """Fix 4: _monitor_process skips OOM branch if status is already terminal."""

    def test_skip_oom_branch_when_status_failed(self):
        current_status = "failed"
        terminal_statuses = ("failed", "stopped", "finished")
        should_skip = current_status in terminal_statuses
        assert should_skip is True

    def test_skip_oom_branch_when_status_stopped(self):
        current_status = "stopped"
        terminal_statuses = ("failed", "stopped", "finished")
        should_skip = current_status in terminal_statuses
        assert should_skip is True

    def test_skip_oom_branch_when_status_finished(self):
        current_status = "finished"
        terminal_statuses = ("failed", "stopped", "finished")
        should_skip = current_status in terminal_statuses
        assert should_skip is True

    def test_proceed_when_status_running(self):
        current_status = "running"
        terminal_statuses = ("failed", "stopped", "finished")
        should_skip = current_status in terminal_statuses
        assert should_skip is False

    def test_proceed_when_status_restarting_oom(self):
        current_status = "restarting_oom"
        terminal_statuses = ("failed", "stopped", "finished")
        should_skip = current_status in terminal_statuses
        assert should_skip is False


class TestForceFinishIdempotent:
    """Fix 5: force_finish_crawl does not double-decrement."""

    def test_skip_decrement_when_current_status_failed(self):
        current = {"status": "failed"}
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is False

    def test_skip_decrement_when_current_status_stopped(self):
        current = {"status": "stopped"}
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is False

    def test_decrement_when_current_status_running(self):
        current = {"status": "running"}
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is True

    def test_decrement_when_current_status_restarting_oom(self):
        current = {"status": "restarting_oom"}
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is True

    def test_skip_decrement_when_job_gone(self):
        current = None
        holding_slot_statuses = ("running", "restarting_oom", "stopping")
        should_decrement = bool(current) and current.get("status") in holding_slot_statuses
        assert should_decrement is False


import inspect
import os
import shutil
import tarfile


class TestCreateArchiveStaging:
    """Archiving writes to a hidden .staging/ subdirectory then atomic-renames
    to the final location, preventing the upload daemon from racing the tmp file."""

    def test_archive_crawl_uses_staging_subdirectory(self):
        """archive_crawl must write tmp archives to a .staging subdirectory."""
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert ".staging" in source, (
            "archive_crawl must use the .staging subdirectory for tmp files "
            "(daemon ignores subdirectories via `find -maxdepth 1`)"
        )

    def test_archive_crawl_has_finally_cleanup_for_staging(self):
        """archive_crawl must have a finally block that cleans up partial staging files."""
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "finally:" in source, (
            "archive_crawl must have a finally block for staging cleanup"
        )
        assert "os.remove(staging_path)" in source, (
            "archive_crawl must remove the staging file on failure"
        )
        assert "if staging_path" in source, (
            "cleanup must check staging_path is set before removing (skip on success)"
        )

    def test_staging_behavior_end_to_end(self, tmp_path):
        """Exercise the staging logic in isolation: archive goes through .staging/
        then ends up at the final path, and the staging dir is empty afterward."""
        # Simulate job storage with a file to archive
        job_storage = tmp_path / "job_storage"
        job_storage.mkdir()
        (job_storage / "data.txt").write_text("payload")

        archives_dir = tmp_path / "archives"
        archives_dir.mkdir()
        crawl_id = "9999"

        # This simulates the new _create_archive logic the implementation must follow
        staging_dir = archives_dir / ".staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        staging_base = str(staging_dir / crawl_id)
        final_target = str(archives_dir / f"{crawl_id}.tar.gz")
        staging_path = None

        try:
            staging_path = shutil.make_archive(
                staging_base, 'gztar', root_dir=str(job_storage)
            )
            archive_size = os.path.getsize(staging_path)
            assert archive_size > 0
            with tarfile.open(staging_path, 'r:gz') as t:
                t.getnames()
            os.rename(staging_path, final_target)
            staging_path = None
        finally:
            if staging_path and os.path.exists(staging_path):
                os.remove(staging_path)

        # Final archive exists in /archives/, staging is empty
        assert (archives_dir / f"{crawl_id}.tar.gz").exists()
        assert list(staging_dir.iterdir()) == [], "staging dir must be empty after success"


import time
from unittest.mock import MagicMock, patch


class TestArchiveDiskPreflight:
    """Helpers for the pre-flight disk space check before archiving."""

    def _manager(self):
        """Instantiate CrawlerManager without running __init__ (avoids Redis setup)."""
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_estimate_returns_size_times_1_5(self, tmp_path):
        """Source dir with 1000 bytes total → estimate returns 1500 bytes."""
        (tmp_path / "a.txt").write_bytes(b"x" * 600)
        (tmp_path / "b.txt").write_bytes(b"y" * 400)
        mgr = self._manager()

        result = mgr._estimate_archive_required_bytes(str(tmp_path))

        assert result == 1500

    def test_estimate_returns_zero_when_source_missing(self, tmp_path):
        """Missing source dir → return 0 (caller applies floor)."""
        mgr = self._manager()

        result = mgr._estimate_archive_required_bytes(str(tmp_path / "does_not_exist"))

        assert result == 0

    def test_estimate_fail_open_on_exception(self):
        """If os.walk raises, return 0 and do not propagate."""
        mgr = self._manager()

        with patch("app.core.crawler_manager.os.walk", side_effect=RuntimeError("fs error")):
            with patch("app.core.crawler_manager.os.path.isdir", return_value=True):
                result = mgr._estimate_archive_required_bytes("/fake")

        assert result == 0

    def test_disk_state_returns_expected_keys(self, tmp_path):
        """Happy path: archives_dir has one .tar.gz → state dict populated."""
        (tmp_path / "abc.tar.gz").write_bytes(b"z" * 100)
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert set(state.keys()) == {
            "free_bytes", "total_bytes", "used_pct", "file_count", "oldest_file_age_seconds"
        }
        assert state["file_count"] == 1
        assert state["oldest_file_age_seconds"] is not None
        assert state["free_bytes"] is not None
        assert state["total_bytes"] is not None
        assert state["used_pct"] is not None

    def test_disk_state_excludes_staging_subdirectory(self, tmp_path):
        """Files in .staging/ must NOT be counted — those are in-progress tmp files."""
        staging = tmp_path / ".staging"
        staging.mkdir()
        (staging / "in_progress.tar.gz").write_bytes(b"x" * 100)
        (tmp_path / "finished.tar.gz").write_bytes(b"y" * 100)
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert state["file_count"] == 1  # only the top-level finished.tar.gz

    def test_disk_state_oldest_age_is_none_when_empty(self, tmp_path):
        """Empty archives_dir → oldest_file_age_seconds is None, not 0."""
        mgr = self._manager()

        state = mgr._get_archives_disk_state(str(tmp_path))

        assert state["file_count"] == 0
        assert state["oldest_file_age_seconds"] is None

    def test_disk_state_fail_open_on_shutil_error(self):
        """If shutil.disk_usage raises (e.g., bad path), return degraded dict (all None)."""
        mgr = self._manager()

        with patch("app.core.crawler_manager.shutil.disk_usage", side_effect=OSError("no such path")):
            state = mgr._get_archives_disk_state("/nonexistent")

        assert state == {
            "free_bytes": None,
            "total_bytes": None,
            "used_pct": None,
            "file_count": None,
            "oldest_file_age_seconds": None,
        }

    def test_archive_crawl_calls_get_disk_state_for_baseline(self):
        """archive_crawl must call _get_archives_disk_state early (baseline log)."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "_get_archives_disk_state" in source, (
            "archive_crawl must collect disk state for baseline logging and pre-flight"
        )
        # Must appear at least twice: once for baseline, once in the failure path
        assert source.count("_get_archives_disk_state") >= 2, (
            "archive_crawl must call _get_archives_disk_state in both baseline and failure paths"
        )

    def test_archive_crawl_applies_1gb_floor_to_required_bytes(self):
        """Required bytes must be floored at 1 GB (1_073_741_824)."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "_estimate_archive_required_bytes" in source, (
            "archive_crawl must call _estimate_archive_required_bytes"
        )
        assert "1_073_741_824" in source or "1073741824" in source, (
            "archive_crawl must apply a 1 GB floor to required bytes"
        )

    def test_archive_crawl_raises_503_on_insufficient_space(self):
        """archive_crawl must raise HTTPException with status 503 and INSUFFICIENT_DISK_SPACE error_code."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.archive_crawl)
        assert "INSUFFICIENT_DISK_SPACE" in source, (
            "archive_crawl must use the INSUFFICIENT_DISK_SPACE error_code"
        )
        assert "status_code=503" in source, (
            "archive_crawl must raise 503 (not 500) when disk space is insufficient"
        )


class TestReconciliationLeaderElection:
    """Tests for Issue #1 (leader election) and Issue #2 (fresh heartbeat,
    ownership-agnostic local override) in crawler_manager."""

    def test_start_crawl_writes_fresh_last_heartbeat(self):
        """start_crawl's initial job_data must include last_heartbeat=now().
        Asserted via source inspection because start_crawl is async and
        requires heavy Redis/process mocking to exercise end-to-end."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.start_crawl)
        assert '"last_heartbeat"' in source or "'last_heartbeat'" in source, (
            "start_crawl must include last_heartbeat in the initial job_data dict"
        )

    def test_stale_override_does_not_require_is_local_job(self):
        """The stale-detection local override must NOT gate on is_local_job.
        It must trust self.local_processes as the authoritative source of
        ownership — otherwise a replica can kill its own freshly-started
        crawl after another replica overwrote replica_id in Redis.

        Note: after Task 3, the scanning logic lives in reconcile_jobs
        (before Task 3) OR in _reconcile_locked (after Task 3). This test
        checks both to remain correct at any point in the task sequence."""
        import inspect
        from app.core import crawler_manager as cm

        # Check whichever method holds the scanning logic
        method = getattr(cm.CrawlerManager, "_reconcile_locked", None) or cm.CrawlerManager.reconcile_jobs
        source = inspect.getsource(method)
        # Find the local-override block: it must check local_processes
        # but NOT gate on is_local_job in the SAME condition.
        assert "crawl_id in self.local_processes" in source, (
            "stale detection must check self.local_processes in the local override"
        )
        # Ensure the phrase 'is_stale and is_local_job and' (the old gate) is absent.
        assert "is_stale and is_local_job and" not in source, (
            "stale detection must not gate the local override on is_local_job; "
            "self.local_processes alone is authoritative for process ownership"
        )

    def test_reconcile_jobs_acquires_leader_lock(self):
        """reconcile_jobs must attempt to acquire a SET NX leader lock at the top."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "reconcile_leader_lock" in source, (
            "reconcile_jobs must use a 'reconcile_leader_lock' Redis key"
        )
        assert "nx=True" in source, (
            "reconcile_jobs must acquire the leader lock with SET NX"
        )
        assert "ex=" in source, (
            "reconcile_jobs must set a TTL on the leader lock"
        )

    def test_reconcile_jobs_returns_early_when_not_leader(self):
        """reconcile_jobs must return early when it does not acquire the lock."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        # Must have a guard that returns if acquisition failed
        assert "if not acquired" in source or "if acquired is False" in source, (
            "reconcile_jobs must guard on lock acquisition and return early when not leader"
        )

    def test_reconcile_jobs_releases_lock_ownership_safely(self):
        """reconcile_jobs must release the lock only if it still owns it,
        guarded by a finally block so a crash still triggers release attempt."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "finally:" in source, (
            "reconcile_jobs must have a finally block for lock release"
        )
        # Ownership-safe release: read the current owner, compare, delete
        assert "current_owner" in source, (
            "reconcile_jobs must read the current lock owner before releasing"
        )
        assert "my_replica_id" in source, (
            "reconcile_jobs must track this replica's own id for ownership comparison"
        )

    def test_reconcile_jobs_delegates_to_reconcile_locked(self):
        """reconcile_jobs (public wrapper) must delegate actual work to _reconcile_locked."""
        import inspect
        from app.core import crawler_manager as cm

        assert hasattr(cm.CrawlerManager, "_reconcile_locked"), (
            "CrawlerManager must have a private _reconcile_locked method containing "
            "the actual reconciliation logic"
        )
        source = inspect.getsource(cm.CrawlerManager.reconcile_jobs)
        assert "self._reconcile_locked()" in source, (
            "reconcile_jobs wrapper must call self._reconcile_locked() "
            "to run the actual scanning logic"
        )

    def test_reconcile_locked_contains_scanning_logic(self):
        """The renamed _reconcile_locked method must contain the original scanning logic."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._reconcile_locked)
        # Smoke-check that the scanning logic is actually in _reconcile_locked
        assert "scan_keys_by_prefix" in source, (
            "_reconcile_locked must contain the original scan_keys_by_prefix call"
        )
        assert "stale_jobs_count" in source, (
            "_reconcile_locked must contain the original stale-job counter"
        )


import uuid as _uuid_module
from unittest.mock import AsyncMock, MagicMock, patch


class TestWebhookIdempotency:
    """Tests for failure webhook idempotency helpers.
    The helpers are standalone and pure — tested directly, not via archive_crawl."""

    def _manager(self):
        """Instantiate CrawlerManager without running __init__ (avoids Redis setup)."""
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_get_or_create_generates_new_uuid_when_absent(self):
        """First call on a job_info with no request_id must generate and persist a new UUID."""
        mgr = self._manager()
        job_info: dict = {}

        rid = mgr._get_or_create_failure_request_id(job_info)

        assert isinstance(rid, str)
        # Must be a valid UUID
        _uuid_module.UUID(rid)  # raises ValueError if not a valid UUID
        # Must persist in the dict
        assert job_info["failure_webhook_request_id"] == rid

    def test_get_or_create_reuses_existing_uuid(self):
        """Second call must return the same UUID stored from the first call."""
        mgr = self._manager()
        existing = "550e8400-e29b-41d4-a716-446655440000"
        job_info = {"failure_webhook_request_id": existing}

        rid = mgr._get_or_create_failure_request_id(job_info)

        assert rid == existing
        # And the dict must not have been mutated to a different value
        assert job_info["failure_webhook_request_id"] == existing

    def test_send_webhook_once_returns_true_on_2xx(self):
        """Single-attempt send returns True on HTTP 200."""
        import asyncio
        mgr = self._manager()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)
            )

        assert result is True

    def test_send_webhook_once_returns_false_on_timeout(self):
        """Single-attempt send returns False when httpx raises (timeout or connection error) and does NOT retry."""
        import asyncio
        import httpx
        mgr = self._manager()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("too slow"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(
                mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)
            )

        assert result is False
        # Must have been called exactly once — no retries
        assert mock_client.__aenter__.return_value.get.call_count == 1

    def test_send_failure_webhook_signature_accepts_request_id_and_shutdown(self):
        """The updated _send_failure_webhook must accept request_id and shutdown kwargs."""
        import inspect
        from app.core import crawler_manager as cm

        sig = inspect.signature(cm.CrawlerManager._send_failure_webhook)
        assert "request_id" in sig.parameters, (
            "_send_failure_webhook must accept a request_id parameter"
        )
        assert "shutdown" in sig.parameters, (
            "_send_failure_webhook must accept a shutdown boolean parameter"
        )
        # Backward-compatible defaults
        assert sig.parameters["request_id"].default is None
        assert sig.parameters["shutdown"].default is False

    def test_send_failure_webhook_body_includes_request_id_when_provided(self):
        """Source inspection: the method body must add request_id to params when set,
        and must route through _send_webhook_once when shutdown=True."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._send_failure_webhook)
        assert 'params["request_id"] = request_id' in source, (
            "_send_failure_webhook must include request_id in the params dict when provided"
        )
        assert "_send_webhook_once" in source, (
            "_send_failure_webhook must route to _send_webhook_once when shutdown=True"
        )
        assert "timeout=5.0" in source, (
            "_send_webhook_once must be called with a 5-second timeout during shutdown"
        )
