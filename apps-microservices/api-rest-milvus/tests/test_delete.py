"""Tests for delete.py — verifies concurrency guard wraps collection.delete() calls."""

import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import FakeGuard


class TestDeleteGuardIntegration:
    """Verify that delete operations acquire individual guard slots."""

    @pytest.mark.asyncio
    async def test_guard_slot_acquired_for_main_delete(self, fake_guard, mock_collection):
        """Main collection delete should acquire exactly one slot."""
        mock_result = MagicMock(delete_count=1, primary_keys=[123])
        mock_collection.delete.return_value = mock_result

        with patch("app.router.delete._connect_to_milvus"), \
             patch("app.router.delete.utility") as mock_util, \
             patch("app.router.delete.get_loaded_collection", return_value=mock_collection):
            mock_util.has_collection.return_value = True

            from app.router.delete import delete_ressource_rest

            result = await delete_ressource_rest(
                guard=fake_guard,
                collection_name="test_collection",
                ids=123,
            )

        assert fake_guard.acquire_count == 1
        assert fake_guard.release_count == 1
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_guard_separate_slots_for_cascade(self, fake_guard, mock_collection):
        """Cascade delete should acquire a separate slot from the main delete."""
        mock_result = MagicMock(delete_count=1, primary_keys=[123])
        mock_collection.delete.return_value = mock_result

        with patch("app.router.delete._connect_to_milvus"), \
             patch("app.router.delete.utility") as mock_util, \
             patch("app.router.delete.get_loaded_collection", return_value=mock_collection), \
             patch("app.router.delete.MILVUS_COLLECTIONS_CASCADE_MAPPING", {"test_collection": "test_correspondance"}):
            mock_util.has_collection.return_value = True

            from app.router.delete import delete_ressource_rest

            result = await delete_ressource_rest(
                guard=fake_guard,
                collection_name="test_collection",
                filters={"field": "value"},
                cascade_enabled=True,
            )

        # Main delete + cascade delete = 2 slots
        assert fake_guard.acquire_count == 2
        assert fake_guard.release_count == 2
