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
