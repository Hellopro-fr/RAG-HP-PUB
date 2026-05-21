"""Tests for crawler_manager.start_crawl capacity short-circuit + Redis retry.

Spec: docs/superpowers/specs/2026-05-22-start-crawl-capacity-short-circuit-design.md
"""
import asyncio
import pytest
from unittest.mock import AsyncMock
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.mark.asyncio
async def test_with_retry_succeeds_after_one_retry():
    """Retries once on transient ConnectionError, then succeeds."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def flaky():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RedisConnectionError("transient")
        return "ok"

    result = await crawler_manager._with_retry(flaky)
    assert result == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_with_retry_exhausts_and_raises():
    """Exhausts all attempts (1 initial + 2 retries = 3) and re-raises."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def always_fail():
        call_count["n"] += 1
        raise RedisConnectionError("permanent")

    with pytest.raises(RedisConnectionError, match="permanent"):
        await crawler_manager._with_retry(always_fail)
    # Default: _REDIS_RETRY_ATTEMPTS = 2 → 1 initial + 2 retries = 3 total.
    assert call_count["n"] == 3
