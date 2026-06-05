"""Tests for app/router/crawler.py.

Currently covers the auto-stash `downloaded_at` recording (P1, Task 3).
Named test_crawler.* so the TDD gate (.claude/hooks/tdd-gate.sh) associates
coverage with crawler.py.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

import app.router.crawler as crawler_router


@pytest.mark.asyncio
async def test_record_downloaded_at_persists_fresh_copy(monkeypatch):
    """Re-reads Redis and writes downloaded_at onto the FRESH copy (so a
    concurrent status change is preserved, not clobbered)."""
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value={"crawl_id": "9", "status": "finished"})
    cache.set_json = AsyncMock()
    monkeypatch.setattr(crawler_router, "cache_service", cache)

    await crawler_router._record_downloaded_at({"crawl_id": "9"})

    key, value = cache.set_json.await_args[0]
    assert key == f"{crawler_router.CRAWL_JOB_PREFIX}9"
    assert "downloaded_at" in value
    assert value["status"] == "finished"  # fresh field preserved, not clobbered


@pytest.mark.asyncio
async def test_record_downloaded_at_skips_when_job_gone(monkeypatch):
    """If the job vanished from Redis between fetch and write, do not recreate it."""
    cache = MagicMock()
    cache.get_json = AsyncMock(return_value=None)
    cache.set_json = AsyncMock()
    monkeypatch.setattr(crawler_router, "cache_service", cache)

    await crawler_router._record_downloaded_at({"crawl_id": "9"})

    cache.set_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_downloaded_at_swallows_errors(monkeypatch):
    """A Redis failure must never propagate out of a download."""
    cache = MagicMock()
    cache.get_json = AsyncMock(side_effect=RuntimeError("redis down"))
    cache.set_json = AsyncMock()
    monkeypatch.setattr(crawler_router, "cache_service", cache)

    await crawler_router._record_downloaded_at({"crawl_id": "9"})  # must not raise
