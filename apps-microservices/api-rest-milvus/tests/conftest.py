"""Shared fixtures for api-rest-milvus tests."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Stub heavy native deps so test_main.py can import `main` without pymilvus,
# waitress, etc. installed locally. These are only used by router code paths
# the unit tests don't exercise.
for _heavy in ("pymilvus", "uvloop", "waitress"):
    sys.modules.setdefault(_heavy, MagicMock())


class FakeGuard:
    """Fake concurrency guard that tracks slot acquisition/release."""

    def __init__(self):
        self.acquire_count = 0
        self.release_count = 0

    class _Slot:
        def __init__(self, guard):
            self._guard = guard

        async def __aenter__(self):
            self._guard.acquire_count += 1
            return "fake-lease-id"

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self._guard.release_count += 1
            return False

    def slot(self):
        return self._Slot(self)


@pytest.fixture
def fake_guard():
    """Return a FakeGuard that counts acquire/release calls."""
    return FakeGuard()


@pytest.fixture
def mock_collection():
    """Return a MagicMock mimicking a pymilvus Collection."""
    collection = MagicMock()
    collection.query.return_value = []
    collection.delete.return_value = MagicMock(delete_count=0, primary_keys=[])
    collection.schema.fields = []
    return collection
