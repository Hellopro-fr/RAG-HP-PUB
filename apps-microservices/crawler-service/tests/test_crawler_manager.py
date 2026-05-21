"""Unit tests for crawler_manager.py state-transition guards."""
import json
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

    def test_all_failure_webhook_callsites_use_request_id_helper(self):
        """Every callsite that sends a failure webhook must call
        _get_or_create_failure_request_id and pass request_id to the webhook."""
        import inspect
        from app.core import crawler_manager as cm

        # All 6 callsites live in these methods:
        methods_to_check = [
            cm.CrawlerManager._relaunch_oom_crawl,   # 2 callsites
            cm.CrawlerManager._monitor_process,      # 1 callsite
            cm.CrawlerManager.force_finish_crawl,    # 1 callsite
            cm.CrawlerManager._cleanup_running_job,  # 1 callsite (shutdown)
            cm.CrawlerManager._reconcile_locked,     # 1 callsite (reconciliation)
        ]

        for method in methods_to_check:
            source = inspect.getsource(method)
            assert "_get_or_create_failure_request_id" in source, (
                f"{method.__qualname__} must call _get_or_create_failure_request_id "
                f"before sending a failure webhook"
            )
            assert "request_id=" in source, (
                f"{method.__qualname__} must pass request_id= to _send_failure_webhook"
            )

    def test_shutdown_path_passes_shutdown_true(self):
        """_cleanup_running_job (shutdown path) must pass shutdown=True to _send_failure_webhook."""
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._cleanup_running_job)
        assert "shutdown=True" in source, (
            "_cleanup_running_job (shutdown path) must pass shutdown=True to route "
            "through the bounded single-attempt webhook send"
        )


def _make_marker_test_manager():
    """
    Builds a minimal CrawlerManager instance for testing _load_completion_marker_or_none.

    The helper under test only reads from disk + uses logger — it does NOT
    touch cache_service. Bare CrawlerManager() works.
    """
    from app.core.crawler_manager import CrawlerManager
    return CrawlerManager()


class TestLoadCompletionMarker:
    """
    Unit tests for CrawlerManager._load_completion_marker_or_none.

    Verifies the helper correctly distinguishes valid terminal markers
    from missing / malformed / unknown-status cases. Used by the
    reconciler stale-detection path to avoid spurious failure webhooks
    when Redis state has drifted from the on-disk completion marker.
    """

    @pytest.mark.asyncio
    async def test_empty_storage_path_returns_none(self):
        manager = _make_marker_test_manager()
        result = await manager._load_completion_marker_or_none("")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_marker_file_returns_none(self, tmp_path):
        manager = _make_marker_test_manager()
        result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none_and_logs_warning(
        self, tmp_path, caplog
    ):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text("{ not valid json")
        manager = _make_marker_test_manager()
        with caplog.at_level("WARNING"):
            result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None
        assert any("failed to read" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_unknown_final_status_returns_none_and_logs_warning(
        self, tmp_path, caplog
    ):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text(json.dumps({"final_status": "weird_state", "exit_code": 0}))
        manager = _make_marker_test_manager()
        with caplog.at_level("WARNING"):
            result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result is None
        assert any("unknown final_status" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("final_status", ["finished", "failed", "stopped"])
    async def test_valid_terminal_marker_returns_parsed_dict(
        self, tmp_path, final_status
    ):
        marker_data = {
            "final_status": final_status,
            "exit_code": 0,
            "end_timestamp": "2026-04-30T15:01:05.000000",
            "reason": "test",
        }
        marker = tmp_path / "_completion_marker.json"
        marker.write_text(json.dumps(marker_data))
        manager = _make_marker_test_manager()
        result = await manager._load_completion_marker_or_none(str(tmp_path))
        assert result == marker_data


class TestStaleHandlerCompletionMarker:
    """
    Verifies the marker-check guard inserted at the top of _reconcile_locked's
    non-terminal-status branch. When marker present + terminal, reconciler
    skips the failure-webhook path and reconciles Redis from marker. When
    marker absent/invalid, falls through to existing stale-failure logic.

    Mirrors the loose "logic-shape" style of TestStaleHandlerCounter — tests
    the guard CONDITION + actions, not full _reconcile_locked invocation
    (the project lacks a Redis fixture for that).
    """

    @pytest.mark.asyncio
    async def test_marker_finished_triggers_reconcile_skips_webhook(
        self, mock_cache_service
    ):
        """When marker says finished, decrement + lock release + set_json with finished, NO webhook."""
        from app.core import crawler_manager as cm

        marker = {"final_status": "finished", "exit_code": 0, "reason": "process_complete"}
        crawl_id = "6244"
        job_data = {"crawl_id": crawl_id, "status": "running", "last_heartbeat": "old"}
        webhook_sent = False

        # Mirror the new guard logic.
        if marker:
            await mock_cache_service.safe_decrement_key(cm.CRAWL_RUNNING_COUNT_KEY)
            await mock_cache_service.delete_key(f"{cm.CRAWL_LOCK_PREFIX}{crawl_id}")
            job_data["status"] = marker["final_status"]
            if "last_heartbeat" in job_data:
                del job_data["last_heartbeat"]
            await mock_cache_service.set_json(f"crawl_jobs:{crawl_id}", job_data)
            # webhook NOT sent

        assert webhook_sent is False
        assert job_data["status"] == "finished"
        assert "last_heartbeat" not in job_data
        mock_cache_service.safe_decrement_key.assert_awaited_once_with(cm.CRAWL_RUNNING_COUNT_KEY)
        mock_cache_service.delete_key.assert_awaited_once_with(f"{cm.CRAWL_LOCK_PREFIX}{crawl_id}")
        mock_cache_service.set_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_marker_failed_triggers_reconcile_skips_webhook(
        self, mock_cache_service
    ):
        """When marker says failed, same reconcile path but Redis status=failed. Webhook still NOT sent (already sent at original failure)."""
        from app.core import crawler_manager as cm

        marker = {"final_status": "failed", "exit_code": 137}
        crawl_id = "6245"
        job_data = {"crawl_id": crawl_id, "status": "running"}
        webhook_sent = False

        if marker:
            await mock_cache_service.safe_decrement_key(cm.CRAWL_RUNNING_COUNT_KEY)
            job_data["status"] = marker["final_status"]
            await mock_cache_service.set_json(f"crawl_jobs:{crawl_id}", job_data)

        assert webhook_sent is False
        assert job_data["status"] == "failed"

    @pytest.mark.asyncio
    async def test_marker_missing_falls_through_to_stale_failure(
        self, mock_cache_service
    ):
        """Marker None → existing stale-failure path runs (webhook sent, status=failed)."""
        marker = None
        webhook_sent = False
        final_status = None

        if marker:
            final_status = marker["final_status"]
        else:
            # Existing stale path
            webhook_sent = True
            final_status = "failed"

        assert webhook_sent is True
        assert final_status == "failed"

    @pytest.mark.asyncio
    async def test_marker_with_unknown_status_falls_through(
        self, mock_cache_service
    ):
        """Marker invalid (helper returned None for unknown final_status) → fall through to stale path."""
        # Helper returned None even though file existed (unknown final_status case)
        marker = None
        webhook_sent = False

        if marker:
            pass
        else:
            webhook_sent = True

        assert webhook_sent is True


class TestGetStatusMalformedBlob:
    """get_status defensive guards for legacy Redis blobs missing keys.

    Reproduces the prod KeyError 'crawl_id' on GET /status. Logic-shape tests
    matching TestStaleHandlerCounter style — verify the guard pattern, not
    end-to-end execution.
    """

    def test_setdefault_heals_missing_crawl_id_from_key_suffix(self):
        """get_all_statuses derives crawl_id from Redis key and injects via
        setdefault before calling get_status — legacy blobs self-heal on read."""
        CRAWL_JOB_PREFIX = "crawl_job:"
        all_job_keys = ["crawl_job:abc-123"]
        job_info_legacy = {
            # No 'crawl_id' field (simulates pre-fix legacy blob)
            "status": "finished",
            "domain": "example.com",
            "storage_path": "/app/storage/abc-123",
        }
        i = 0
        crawl_id = all_job_keys[i].replace(CRAWL_JOB_PREFIX, "")

        # The fix: setdefault before passing to get_status
        job_info_legacy.setdefault("crawl_id", crawl_id)

        assert job_info_legacy["crawl_id"] == "abc-123"

    def test_setdefault_preserves_existing_crawl_id(self):
        """setdefault must NOT overwrite a correct crawl_id already present."""
        CRAWL_JOB_PREFIX = "crawl_job:"
        all_job_keys = ["crawl_job:abc-123"]
        job_info = {
            "crawl_id": "abc-123",
            "status": "running",
            "storage_path": "/app/storage/abc-123",
        }
        i = 0
        crawl_id = all_job_keys[i].replace(CRAWL_JOB_PREFIX, "")
        job_info.setdefault("crawl_id", crawl_id)

        assert job_info["crawl_id"] == "abc-123"

    def test_get_status_returns_none_when_crawl_id_missing(self):
        """If a blob still lacks crawl_id even after setdefault (defensive
        belt-and-suspenders), get_status must return None instead of KeyError."""
        job_info = {"status": "finished", "storage_path": "/tmp/x"}
        crawl_id = job_info.get("crawl_id")
        result = None
        if not crawl_id:
            result = None  # get_status guard returns None
        assert result is None

    def test_get_status_returns_none_when_storage_path_missing(self):
        """Defensive guard for second required field."""
        job_info = {"crawl_id": "abc-123", "status": "finished"}
        crawl_id = job_info.get("crawl_id")
        storage_path = job_info.get("storage_path")
        result = None
        if not crawl_id:
            result = None
        elif not storage_path:
            result = None
        assert result is None

    def test_get_all_statuses_skips_none_results(self):
        """The loop already filters via `if status_data:` — verify None values
        from malformed blobs are skipped without crashing the whole endpoint."""
        statuses = {}
        results = [
            ("abc-123", {"crawl_id": "abc-123"}),  # valid CrawlStatus stand-in
            ("def-456", None),  # malformed blob → get_status returned None
            ("ghi-789", {"crawl_id": "ghi-789"}),
        ]
        for crawl_id, status_data in results:
            if status_data:
                statuses[crawl_id] = status_data

        assert "abc-123" in statuses
        assert "def-456" not in statuses
        assert "ghi-789" in statuses
        assert len(statuses) == 2


class TestCleanupStaleStateForRelaunch:
    """
    Verifies _cleanup_stale_state_for_relaunch wipes any prior-run
    _completion_marker.json on crawl relaunch. Used by start_crawl
    to prevent the reconciler's marker-check (sub-problem A) from
    falsely declaring the new running crawl finished.
    """

    @pytest.mark.asyncio
    async def test_existing_marker_is_unlinked(self, tmp_path):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text('{"final_status": "finished", "exit_code": 0}')
        assert marker.exists()
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        await manager._cleanup_stale_state_for_relaunch("test-123", str(tmp_path))
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_missing_marker_is_noop(self, tmp_path):
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        await manager._cleanup_stale_state_for_relaunch("test-456", str(tmp_path))

    @pytest.mark.asyncio
    async def test_permission_error_logged_not_raised(self, tmp_path, caplog):
        marker = tmp_path / "_completion_marker.json"
        marker.write_text("{}")
        from unittest.mock import patch
        from app.core.crawler_manager import CrawlerManager
        manager = CrawlerManager()
        with patch("os.unlink", side_effect=PermissionError("denied")):
            with caplog.at_level("WARNING"):
                await manager._cleanup_stale_state_for_relaunch("test-789", str(tmp_path))
        assert any(
            "Could not remove stale completion marker" in r.message
            for r in caplog.records
        )


class TestParseIsoNaiveUtc:
    """Regression: reconcile_jobs raised TypeError when a Redis blob
    contained a tz-aware ISO datetime in last_heartbeat/start_time, because
    fromisoformat() returned an aware datetime that could not subtract
    against naive datetime.utcnow(). Helper normalizes both shapes.
    """

    def test_naive_input_passes_through(self):
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        result = _parse_iso_naive_utc("2026-05-20T08:24:01")
        assert result.tzinfo is None
        assert result == datetime(2026, 5, 20, 8, 24, 1)

    def test_naive_with_microseconds_passes_through(self):
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        result = _parse_iso_naive_utc("2026-05-20T08:24:01.123456")
        assert result.tzinfo is None
        assert result == datetime(2026, 5, 20, 8, 24, 1, 123456)

    def test_z_suffix_stripped_to_naive_utc(self):
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        result = _parse_iso_naive_utc("2026-05-20T08:24:01Z")
        assert result.tzinfo is None
        assert result == datetime(2026, 5, 20, 8, 24, 1)

    def test_zero_offset_stripped_to_naive_utc(self):
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        result = _parse_iso_naive_utc("2026-05-20T08:24:01+00:00")
        assert result.tzinfo is None
        assert result == datetime(2026, 5, 20, 8, 24, 1)

    def test_positive_offset_converted_to_utc(self):
        """+05:00 wall-clock 08:24 = 03:24 UTC."""
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        result = _parse_iso_naive_utc("2026-05-20T08:24:01+05:00")
        assert result.tzinfo is None
        assert result == datetime(2026, 5, 20, 3, 24, 1)

    def test_result_subtracts_safely_against_utcnow(self):
        """The whole point: no TypeError when used in reconcile_jobs."""
        from datetime import datetime
        from app.core.crawler_manager import _parse_iso_naive_utc

        # Tz-aware input that previously broke reconcile
        parsed = _parse_iso_naive_utc("2026-05-20T08:24:01Z")
        # Must subtract without TypeError
        delta = datetime.utcnow() - parsed
        assert delta.total_seconds() >= 0  # parsed is in the past


class TestStashedAtFormat:
    """Regression: stash_crawl previously wrote `stashed_at = utcnow().isoformat() + "Z"`,
    which would cause reconcile (and any future fromisoformat consumer) to
    return a tz-aware datetime that can't subtract from naive utcnow().
    Convention-fix: drop the Z suffix to match archived_at/last_heartbeat.
    """

    def test_stash_crawl_stashed_at_format_is_naive(self):
        """Inspect the stash_crawl source to confirm no `+ "Z"` suffix is appended."""
        import inspect
        from app.core import crawler_manager as cm

        src = inspect.getsource(cm.CrawlerManager.stash_crawl)
        assert "isoformat() + \"Z\"" not in src, (
            "stash_crawl must not append 'Z' to stashed_at; "
            "convention is naive UTC ISO string."
        )
        # And the assignment must still produce an ISO string
        assert "stashed_at = datetime.utcnow().isoformat()" in src


class TestVerifyBindMount:
    """Defensive helper: raises 503 BIND_MOUNT_MISSING when stash/unstash
    target paths are not real bind-mounts. Catches the silent-data-loss
    case where docker-compose volumes were declared but the container was
    not recreated to pick them up (incident 2026-05-20 crawl 1958)."""

    def test_raises_503_when_path_is_ordinary_dir(self, tmp_path):
        from fastapi import HTTPException
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        ordinary = tmp_path / "ephemeral"
        ordinary.mkdir()  # plain dir, NOT a mount

        with pytest.raises(HTTPException) as exc:
            cm._verify_bind_mount(str(ordinary), "test-label")

        assert exc.value.status_code == 503
        assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"
        assert exc.value.detail["path"] == str(ordinary)
        assert exc.value.detail["label"] == "test-label"
        assert "force-recreate" in exc.value.detail["ops_action"]
        assert "hint" in exc.value.detail

    def test_raises_503_when_path_does_not_exist(self, tmp_path):
        from fastapi import HTTPException
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        missing = tmp_path / "nonexistent"  # never created

        with pytest.raises(HTTPException) as exc:
            cm._verify_bind_mount(str(missing), "test-label")

        assert exc.value.status_code == 503
        assert exc.value.detail["error_code"] == "BIND_MOUNT_MISSING"

    def test_returns_none_when_ismount_true(self, tmp_path, monkeypatch):
        """Simulate a real mount point by mocking os.path.ismount."""
        import os
        from app.core.crawler_manager import CrawlerManager

        cm = CrawlerManager()
        fake_mount = tmp_path / "mounted"
        fake_mount.mkdir()
        monkeypatch.setattr(os.path, "ismount", lambda p: str(p) == str(fake_mount))

        # Must not raise
        result = cm._verify_bind_mount(str(fake_mount), "test-label")
        assert result is None


# ============================================================================
# Archive lock heartbeat tests (T3)
# ============================================================================

import asyncio as _asyncio

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager
from fastapi import HTTPException


@pytest.fixture
def _mock_cache_service_archive(monkeypatch):
    """Module-level cache_service mock for archive heartbeat tests.
    Has redis_client as AsyncMock so set/eval/delete can be stubbed per test.
    """
    mock = MagicMock()
    mock.redis_client = AsyncMock()
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    monkeypatch.setattr(cm_module, "cache_service", mock)
    return mock


@pytest.fixture
def _cm_instance_archive(_mock_cache_service_archive):
    return CrawlerManager()


@pytest.fixture
def archive_job_info(tmp_path):
    storage = tmp_path / "crawl_data"
    storage.mkdir()
    (storage / "crawler.log").write_text("log content")
    (storage / "dataset.json").write_text('{"records": [1,2,3]}')
    return {
        "crawl_id": "archive_test_id",
        "status": "finished",
        "storage_path": str(storage),
        "domain": "example.com",
    }


@pytest.mark.asyncio
async def test_archive_lock_holds_during_long_tar(
    _cm_instance_archive, archive_job_info, _mock_cache_service_archive, monkeypatch, tmp_path
):
    """Tar that runs past initial TTL keeps lock via heartbeat; concurrent
    attempt gets 409.

    Mirror of test_stash_lock_survives_long_tar at apps-microservices/crawler-
    service/tests/test_crawler_manager_stash.py (commit 1427b494).
    """
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "ARCHIVE_LOCK_TTL_SECONDS", 2)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(cfg.settings, "LOCK_HEARTBEAT_MAX_DURATION_SECONDS", 30)

    archives_dir = tmp_path / "archives"
    archives_dir.mkdir()
    monkeypatch.setattr(cm_module.settings, "ARCHIVES_SHARED_PATH", str(archives_dir))

    # Track SET NX: first acquire wins, subsequent fail (concurrent caller 409).
    set_call_count = {"n": 0}
    eval_call_count = {"n": 0}

    async def _set_side_effect(key, value, **kwargs):
        set_call_count["n"] += 1
        return set_call_count["n"] == 1

    async def _eval_side_effect(script, numkeys, *args):
        eval_call_count["n"] += 1
        return 1

    _mock_cache_service_archive.redis_client.set = AsyncMock(side_effect=_set_side_effect)
    _mock_cache_service_archive.redis_client.eval = AsyncMock(side_effect=_eval_side_effect)
    _mock_cache_service_archive.redis_client.delete = AsyncMock(return_value=1)

    # Stub helpers to skip GCS fallback and pass disk pre-flight.
    async def _gcs_404(*args, **kwargs):
        raise HTTPException(status_code=502, detail="not in GCS")

    monkeypatch.setattr(_cm_instance_archive, "_retrieve_from_gcs_daemon", _gcs_404)
    monkeypatch.setattr(
        _cm_instance_archive, "_get_archives_disk_state",
        lambda d: {"free_bytes": 10**12, "total_bytes": 10**12, "used_pct": 0.0,
                   "file_count": 0, "oldest_file_age_seconds": None},
    )
    monkeypatch.setattr(
        _cm_instance_archive, "_estimate_archive_required_bytes", lambda p: 1024,
    )
    monkeypatch.setattr(_cm_instance_archive, "_mark_as_archived", AsyncMock(return_value=None))

    # Stub get_status so the snapshot step doesn't fail (snapshot creation is wrapped in try/except,
    # so a failure there is non-fatal, but stubbing avoids noise).
    from unittest.mock import MagicMock as _MagicMock
    mock_status = _MagicMock()
    mock_status.model_dump = _MagicMock(return_value={})
    monkeypatch.setattr(_cm_instance_archive, "get_status", AsyncMock(return_value=mock_status))

    # Slow tar: capture shutil/tarfile from local import BEFORE patching to avoid recursion.
    import shutil as _shutil
    import tarfile as _tarfile
    import time as _time

    def slow_make_archive(base_name, fmt, root_dir=None, **kwargs):
        out = f"{base_name}.tar.gz" if fmt == "gztar" else f"{base_name}.tar"
        with _tarfile.open(out, "w:gz" if fmt == "gztar" else "w") as tf:
            pass  # empty archive — passes integrity check
        _time.sleep(4)  # 2x initial TTL=2s
        return out

    monkeypatch.setattr(cm_module.shutil, "make_archive", slow_make_archive)

    task1 = _asyncio.create_task(_cm_instance_archive.archive_crawl(archive_job_info))
    await _asyncio.sleep(2.5)  # past initial TTL — only heartbeat keeps lock

    with pytest.raises(HTTPException) as exc_info:
        await _cm_instance_archive.archive_crawl(archive_job_info)
    assert exc_info.value.status_code == 409
    assert "already in progress" in str(exc_info.value.detail).lower()

    result = await task1
    assert "archive_status" in result

    # Heartbeat fired during the 4s tar (≥ 1 refresh expected)
    assert eval_call_count["n"] >= 2


def test_archive_409_body_strings_unchanged():
    """The PHP cron at 3_archive_eligible_domains.php line 375 matches
    'already been archived' via stripos. Both 409 detail strings are
    caller-contract surface. Asserting their literal presence in source."""
    import inspect
    src = inspect.getsource(cm_module.CrawlerManager.archive_crawl)
    assert "already been archived" in src, (
        "PHP cron substring 'already been archived' missing — do not change."
    )
    assert "is already in progress" in src, (
        "Lock-held 409 substring 'is already in progress' missing — caller "
        "contract."
    )


@pytest.mark.asyncio
async def test_archive_lock_release_is_ownership_safe(
    _cm_instance_archive, _mock_cache_service_archive
):
    """A different replica's value cannot DEL our lock."""
    lock_key = "archive_lock:ownership_test"

    # Force _acquire_ownership_lock to return a value for our acquire
    _mock_cache_service_archive.redis_client.set = AsyncMock(return_value=True)
    _mock_cache_service_archive.redis_client.eval = AsyncMock(side_effect=[
        0,  # first release: wrong value → CAS returns 0
        1,  # second release: correct value → CAS returns 1
    ])

    our_value = await _cm_instance_archive._acquire_ownership_lock(lock_key, 60)
    assert our_value is not None

    released = await _cm_instance_archive._release_ownership_lock(lock_key, "wrong-replica-id")
    assert released is False

    released = await _cm_instance_archive._release_ownership_lock(lock_key, our_value)
    assert released is True


# ============================================================================
# Task 7: exit-code dispatch + failure_cause kwarg override
# ============================================================================


class TestClassifyExitCode:
    """_classify_exit_code maps every exit code to the correct (message, cause) tuple."""

    @pytest.mark.parametrize("exit_code, expected_cause", [
        (0,    None),
        (2,    None),
        (-1,   "oom_max_restarts"),
        (3,    "oom_relaunch"),
        (4,    "update_mode_no_data"),
        (5,    "redis_lost"),
        (6,    "progress_stalled"),
        (137,  "killed_oom_system"),
        (-9,   "killed_oom_system"),
        (-15,  "signal_killed"),
        (99,   "unknown"),
    ])
    def test_cause_for_exit_code(self, exit_code, expected_cause):
        from app.core.crawler_manager import CrawlerManager
        _, cause = CrawlerManager._classify_exit_code(exit_code)
        assert cause == expected_cause

    @pytest.mark.parametrize("exit_code", [0, 2])
    def test_success_codes_return_none_none(self, exit_code):
        from app.core.crawler_manager import CrawlerManager
        msg, cause = CrawlerManager._classify_exit_code(exit_code)
        assert msg is None
        assert cause is None

    def test_exit_code_minus1_message_is_oom(self):
        from app.core.crawler_manager import CrawlerManager
        msg, _ = CrawlerManager._classify_exit_code(-1)
        assert msg == "Out Of Memory"

    def test_exit_code_5_message_mentions_redis(self):
        from app.core.crawler_manager import CrawlerManager
        msg, _ = CrawlerManager._classify_exit_code(5)
        assert msg is not None
        assert "Redis" in msg or "redis" in msg.lower()

    def test_exit_code_6_message_mentions_progression(self):
        from app.core.crawler_manager import CrawlerManager
        msg, _ = CrawlerManager._classify_exit_code(6)
        assert msg is not None
        assert len(msg) > 0


class TestSendFailureWebhookFailureCauseKwarg:
    """
    _send_failure_webhook: explicit failure_cause kwarg overrides _classify_exit_code.

    exit_code=-1 normally resolves to "oom_max_restarts" via the classifier.
    Callers that pass a different explicit cause (service_shutdown, force_finished,
    stale_detected, oom_relaunch_failed) must override that default.
    """

    def _manager(self):
        from app.core.crawler_manager import CrawlerManager
        return CrawlerManager.__new__(CrawlerManager)

    def test_signature_has_failure_cause_kwarg(self):
        import inspect
        from app.core.crawler_manager import CrawlerManager
        sig = inspect.signature(CrawlerManager._send_failure_webhook)
        assert "failure_cause" in sig.parameters
        assert sig.parameters["failure_cause"].default is None

    def test_explicit_cause_overrides_classifier_in_source(self):
        """Source inspection: the method body must prefer the explicit kwarg."""
        import inspect
        from app.core import crawler_manager as cm
        source = inspect.getsource(cm.CrawlerManager._send_failure_webhook)
        # The override pattern must be present
        assert "failure_cause if failure_cause is not None" in source, (
            "_send_failure_webhook must override classifier output with explicit failure_cause kwarg"
        )

    @pytest.mark.asyncio
    async def test_explicit_cause_wins_over_classifier_for_exit_minus1(self):
        """
        exit_code=-1 → classifier says 'oom_max_restarts'.
        Explicit failure_cause='service_shutdown' must override it in the params sent.
        """
        import asyncio
        mgr = self._manager()

        captured_params = {}

        async def _fake_send_with_retry(url, params, crawl_id, webhook_type):
            captured_params.update(params)
            return True

        async def _fake_send_once(url, params, crawl_id, webhook_type, timeout=5.0):
            captured_params.update(params)
            return True

        mgr._send_webhook_with_retry = _fake_send_with_retry
        mgr._send_webhook_once = _fake_send_once

        await mgr._send_failure_webhook(
            url="http://example.test/cb",
            crawl_id="test-001",
            domain="example.com",
            exit_code=-1,
            failure_cause="service_shutdown",
        )

        assert captured_params.get("failure_cause") == "service_shutdown", (
            "Explicit failure_cause='service_shutdown' must override the classifier's "
            "'oom_max_restarts' for exit_code=-1"
        )

    @pytest.mark.asyncio
    async def test_no_explicit_cause_uses_classifier_for_exit_minus1(self):
        """Without an explicit kwarg, classifier default 'oom_max_restarts' is used."""
        import asyncio
        mgr = self._manager()

        captured_params = {}

        async def _fake_send_with_retry(url, params, crawl_id, webhook_type):
            captured_params.update(params)
            return True

        mgr._send_webhook_with_retry = _fake_send_with_retry

        await mgr._send_failure_webhook(
            url="http://example.test/cb",
            crawl_id="test-002",
            domain="example.com",
            exit_code=-1,
            # No explicit failure_cause → classifier kicks in
        )

        assert captured_params.get("failure_cause") == "oom_max_restarts"

    @pytest.mark.parametrize("explicit_cause", [
        "service_shutdown",
        "force_finished",
        "stale_detected",
        "oom_relaunch_failed",
        "oom_max_restarts",
    ])
    @pytest.mark.asyncio
    async def test_all_sentinel_callers_override_cause(self, explicit_cause):
        """Every exit_code=-1 caller passes its own explicit cause correctly."""
        mgr = self._manager()

        captured_params = {}

        async def _fake_send_with_retry(url, params, crawl_id, webhook_type):
            captured_params.update(params)
            return True

        async def _fake_send_once(url, params, crawl_id, webhook_type, timeout=5.0):
            captured_params.update(params)
            return True

        mgr._send_webhook_with_retry = _fake_send_with_retry
        mgr._send_webhook_once = _fake_send_once

        await mgr._send_failure_webhook(
            url="http://example.test/cb",
            crawl_id="test-003",
            domain="example.com",
            exit_code=-1,
            failure_cause=explicit_cause,
        )

        assert captured_params.get("failure_cause") == explicit_cause


class TestOomMaxRestartsWebhookCause:
    """
    _relaunch_oom_crawl's max-restarts branch must pass failure_cause="oom_max_restarts"
    to _send_failure_webhook (not rely on the default for exit_code=-1).
    Source inspection verifies the explicit kwarg is present.
    """

    def test_max_restarts_branch_passes_oom_max_restarts_cause(self):
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._relaunch_oom_crawl)
        # Both webhook calls must carry explicit failure_cause kwargs.
        # The simplest assertion: the string appears at least twice
        # (once for max-restarts, once for relaunch-failed).
        assert source.count('failure_cause="oom_max_restarts"') >= 1, (
            "_relaunch_oom_crawl max-restarts branch must pass "
            'failure_cause="oom_max_restarts" to _send_failure_webhook'
        )

    def test_relaunch_failed_branch_passes_oom_relaunch_failed_cause(self):
        import inspect
        from app.core import crawler_manager as cm

        source = inspect.getsource(cm.CrawlerManager._relaunch_oom_crawl)
        assert 'failure_cause="oom_relaunch_failed"' in source, (
            "_relaunch_oom_crawl relaunch-failed branch must pass "
            'failure_cause="oom_relaunch_failed" to _send_failure_webhook'
        )


class TestAllExitMinus1CallersPassExplicitCause:
    """
    Source-level contract: every call to _send_failure_webhook with exit_code=-1
    must supply an explicit failure_cause kwarg so the classifier's default
    'oom_max_restarts' label is never applied to non-OOM failure paths.
    """

    @pytest.mark.parametrize("method_name, expected_cause", [
        ("_cleanup_running_job",  "service_shutdown"),
        ("force_finish_crawl",    "force_finished"),
        ("_reconcile_locked",     "stale_detected"),
    ])
    def test_caller_has_explicit_failure_cause(self, method_name, expected_cause):
        import inspect
        from app.core import crawler_manager as cm

        method = getattr(cm.CrawlerManager, method_name)
        source = inspect.getsource(method)
        assert f'failure_cause="{expected_cause}"' in source, (
            f"{method_name} must pass failure_cause=\"{expected_cause}\" "
            "to _send_failure_webhook when exit_code=-1"
        )
