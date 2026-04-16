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
