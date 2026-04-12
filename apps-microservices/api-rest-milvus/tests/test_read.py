"""Tests for read.py — verifies concurrency guard wraps collection.query() calls."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import FakeGuard


class TestReadGuardIntegration:
    """Verify that get_ressource_rest acquires/releases a guard slot per query."""

    @pytest.mark.asyncio
    async def test_guard_slot_acquired_for_query_with_filter(self, fake_guard, mock_collection):
        """When a filtered query runs, exactly one slot should be acquired and released."""
        mock_collection.query.return_value = [{"id": 1, "name": "test"}]

        with patch("app.router.read._connect_to_milvus"), \
             patch("app.router.read.utility") as mock_util, \
             patch("app.router.read.get_loaded_collection", return_value=mock_collection):
            mock_util.has_collection.return_value = True

            from app.router.read import get_ressource_rest

            result = await get_ressource_rest(
                guard=fake_guard,
                collection_name="test_collection",
                id_milvus="42",
                metadata={},
                limit=10,
                offset=0,
            )

        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_guard_slot_acquired_for_query_no_filter(self, fake_guard, mock_collection):
        """When querying without filters, one slot should still be acquired."""
        mock_collection.query.return_value = []

        with patch("app.router.read._connect_to_milvus"), \
             patch("app.router.read.utility") as mock_util, \
             patch("app.router.read.get_loaded_collection", return_value=mock_collection):
            mock_util.has_collection.return_value = True

            from app.router.read import get_ressource_rest

            result = await get_ressource_rest(
                guard=fake_guard,
                collection_name="test_collection",
                metadata={},
                limit=10,
                offset=0,
            )

        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1
