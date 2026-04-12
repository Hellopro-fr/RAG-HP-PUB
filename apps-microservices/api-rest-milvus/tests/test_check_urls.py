"""Tests for check_urls.py — verifies guard wraps each batch query."""

import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import FakeGuard


class TestCheckUrlsGuardIntegration:
    """Verify that check_urls batch loop acquires a slot per query."""

    @pytest.mark.asyncio
    async def test_guard_slot_per_batch_in_check(self, fake_guard, mock_collection):
        """Each batch query in _check_urls_batch should get its own slot."""
        mock_collection.query.return_value = [
            {"url": "https://example.com/page1", "page_type": "content"},
        ]

        from app.router.check_urls import _check_urls_batch

        result = await _check_urls_batch(
            guard=fake_guard,
            collection=mock_collection,
            urls_to_check=["https://example.com/page1"],
        )

        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1
        assert "https://example.com/page1" in result["found_urls"]
