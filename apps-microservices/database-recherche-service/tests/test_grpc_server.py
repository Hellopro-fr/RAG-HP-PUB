"""Tests for database-recherche-service gRPC server concurrency guard integration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_use_case():
    """Create a mock SearchUseCase."""
    use_case = MagicMock()
    use_case.execute_search_batch = MagicMock(return_value=[[]])
    use_case.execute_hybrid_search_batch = MagicMock(return_value=[[]])
    return use_case


@pytest.fixture
def mock_guard():
    """Create a mock MilvusConcurrencyGuard with async context manager slot()."""
    guard = MagicMock()
    slot_cm = AsyncMock()
    slot_cm.__aenter__ = AsyncMock(return_value="test-lease-id")
    slot_cm.__aexit__ = AsyncMock(return_value=False)
    guard.slot.return_value = slot_cm
    return guard


class TestConcurrencyGuardIntegration:
    """Verify that the global concurrency guard replaced the local Zilliz semaphore."""

    def test_servicer_has_concurrency_guard(self, mock_use_case):
        """Servicer must expose _concurrency_guard, not _zilliz_limiter."""
        with patch.dict("os.environ", {"REDIS_URL": "mock-redis-for-test"}, clear=False):
            with patch("infrastructure.grpc_server.aioredis") as mock_aioredis:
                mock_aioredis.from_url.return_value = MagicMock()
                from infrastructure.grpc_server import DatabaseSearchServiceImpl

                servicer = DatabaseSearchServiceImpl(mock_use_case)
                assert hasattr(servicer, "_concurrency_guard"), (
                    "_concurrency_guard attribute must exist"
                )
                assert not hasattr(servicer, "_zilliz_limiter") or servicer._zilliz_limiter is None, (
                    "_zilliz_limiter must no longer be used"
                )

    def test_process_queue_batch_signature_no_limiter(self):
        """_process_queue_batch must not accept a 'limiter' parameter."""
        from infrastructure.grpc_server import DatabaseSearchServiceImpl
        import inspect

        sig = inspect.signature(DatabaseSearchServiceImpl._process_queue_batch)
        param_names = list(sig.parameters.keys())
        assert "limiter" not in param_names, (
            "_process_queue_batch should no longer accept a 'limiter' parameter"
        )

    def test_execute_task_signature_no_limiter(self):
        """_execute_task must not accept a 'limiter' parameter."""
        from infrastructure.grpc_server import DatabaseSearchServiceImpl
        import inspect

        sig = inspect.signature(DatabaseSearchServiceImpl._execute_task)
        param_names = list(sig.parameters.keys())
        assert "limiter" not in param_names, (
            "_execute_task should no longer accept a 'limiter' parameter"
        )

    @pytest.mark.asyncio
    async def test_process_queue_batch_acquires_guard_slot(self, mock_use_case, mock_guard):
        """_process_queue_batch must acquire a slot from the concurrency guard."""
        with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
            from infrastructure.grpc_server import DatabaseSearchServiceImpl

            servicer = DatabaseSearchServiceImpl(mock_use_case)
            servicer._concurrency_guard = mock_guard

            # Create a fake batch with a search action
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            batch = [("search", ("coll", 10, None, (), ()), {"vector": [0.1], "kwargs": {}}, future)]

            from concurrent.futures import ThreadPoolExecutor

            servicer._default_executor = ThreadPoolExecutor(max_workers=1)

            mock_use_case.execute_search_batch.return_value = [["result"]]

            await servicer._process_queue_batch(batch, executor=servicer._default_executor)

            # Verify the guard's slot() was called
            mock_guard.slot.assert_called_once()

    @pytest.mark.asyncio
    async def test_guard_fallback_without_redis(self, mock_use_case):
        """Guard must initialize with fallback when REDIS_URL is not set."""
        with patch.dict("os.environ", {"REDIS_URL": ""}, clear=False):
            from infrastructure.grpc_server import DatabaseSearchServiceImpl

            servicer = DatabaseSearchServiceImpl(mock_use_case)
            assert hasattr(servicer, "_concurrency_guard"), (
                "_concurrency_guard must exist even without Redis"
            )
