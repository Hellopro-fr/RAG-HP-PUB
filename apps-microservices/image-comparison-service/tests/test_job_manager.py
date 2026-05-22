"""Tests for app/core/job_manager.py JobManager Redis wiring against the
shared async pool from common_utils.cache_service."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVICE_ROOT)

# Stub heavy native deps so tests don't require cv2 / skimage / imagehash / PIL
# in the test environment — they are only used by ImageProcessor, which
# JobManager imports but the Redis-wiring tests don't exercise.
for _heavy in (
    "cv2", "numpy", "imagehash",
    "skimage", "skimage.metrics",
    "PIL", "PIL.Image",
    "httpx",
    "app.core.image_processor",
):
    sys.modules.setdefault(_heavy, MagicMock())


@pytest.mark.asyncio
async def test_connect_redis_attaches_to_shared_pool():
    """JobManager.connect_redis() initializes the shared pool and stores the
    resulting client on self.redis instead of opening its own from_url."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("app.core.job_manager.init_redis_pool", new_callable=AsyncMock) as mock_init, \
         patch("app.core.job_manager.cache_service") as mock_cs:
        mock_cs.redis_client = mock_client

        from app.core.job_manager import JobManager
        mgr = JobManager()
        await mgr.connect_redis()

        mock_init.assert_awaited_once()
        assert mgr.redis is mock_client


@pytest.mark.asyncio
async def test_close_redis_delegates_to_common_utils():
    """JobManager.close_redis() delegates to close_redis_pool() so the
    shared pool's cleanup runs."""
    with patch("app.core.job_manager.init_redis_pool", new_callable=AsyncMock), \
         patch("app.core.job_manager.close_redis_pool", new_callable=AsyncMock) as mock_close, \
         patch("app.core.job_manager.cache_service") as mock_cs:
        mock_cs.redis_client = AsyncMock()

        from app.core.job_manager import JobManager
        mgr = JobManager()
        await mgr.connect_redis()
        await mgr.close_redis()

        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_redis_handles_init_failure():
    """If common_utils returns None (REDIS_URL unset), self.redis stays None
    and operations that depend on Redis degrade gracefully."""
    with patch("app.core.job_manager.init_redis_pool", new_callable=AsyncMock), \
         patch("app.core.job_manager.cache_service") as mock_cs:
        mock_cs.redis_client = None

        from app.core.job_manager import JobManager
        mgr = JobManager()
        await mgr.connect_redis()

        assert mgr.redis is None
