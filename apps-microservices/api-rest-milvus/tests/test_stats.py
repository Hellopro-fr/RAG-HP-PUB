"""Tests for stats.py — verifies guard wraps each collection.query() in the loop."""

import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import FakeGuard


class TestStatsGuardIntegration:
    """Verify that stats loop acquires a slot per batch query."""

    @pytest.mark.asyncio
    async def test_guard_slot_per_batch_in_analysis(self, fake_guard, mock_collection):
        """Each batch query in the stats loop should get its own slot."""
        # First batch returns results, second batch returns empty (end of loop)
        mock_collection.query.side_effect = [
            [{"url": "https://example.com", "id": 1, "page_type": "content", "domaine": "example.com"}],
            [],
        ]

        with patch("app.router.stats.utility") as mock_util, \
             patch("app.router.stats.get_loaded_collection", return_value=mock_collection):
            mock_util.has_collection.return_value = True

            from app.router.stats import _run_global_analysis

            result = await _run_global_analysis(guard=fake_guard, domains_filter=None)

        # 2 batches = 2 slot acquisitions
        assert fake_guard.acquire_count == 2
        assert fake_guard.release_count == 2
