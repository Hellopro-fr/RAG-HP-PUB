"""Tests for webhook dead-letter durability (Fix A) and bounded auto-drain (Fix B).

Bug: shutdown-path webhooks (_send_webhook_once) were single-attempt with no
replay — on failure they were silently lost, stranding update-mode UCH rows
RUNNING after a rebuild+up. Fix A makes _send_webhook_once enqueue failures
into FAILED_CALLBACKS_KEY (the existing dead-letter, previously only written
by _send_webhook_with_retry's exhaustion path). Fix B has the reconcile
leader drain a bounded batch of that dead-letter each tick.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core import crawler_manager as cm_module
from app.core.crawler_manager import CrawlerManager


def _manager():
    """Instantiate CrawlerManager without running __init__ (avoids Redis setup)."""
    return CrawlerManager.__new__(CrawlerManager)


class TestSendWebhookOnceStoresOnFailure:
    """Fix A: the single-attempt shutdown-path send must enqueue to the
    dead-letter on failure instead of silently dropping."""

    @pytest.mark.asyncio
    async def test_send_webhook_once_stores_on_http_error(self):
        mgr = _manager()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client), \
             patch.object(mgr, "_store_failed_callback", new_callable=AsyncMock) as mock_store:
            result = await mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)

        assert result is False
        mock_store.assert_awaited_once()
        args = mock_store.call_args.args
        assert args[0] == "http://x.test"
        assert args[1] == {"a": 1}
        assert args[2] == "crawl-1"
        assert args[3] == "failure"

    @pytest.mark.asyncio
    async def test_send_webhook_once_stores_on_exception(self):
        mgr = _manager()
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("too slow"))
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client), \
             patch.object(mgr, "_store_failed_callback", new_callable=AsyncMock) as mock_store:
            result = await mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "stop", timeout=1.0)

        assert result is False
        mock_store.assert_awaited_once()
        args = mock_store.call_args.args
        assert args[2] == "crawl-1"
        assert args[3] == "stop"

    @pytest.mark.asyncio
    async def test_send_webhook_once_no_store_on_success(self):
        mgr = _manager()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.core.crawler_manager.httpx.AsyncClient", return_value=mock_client), \
             patch.object(mgr, "_store_failed_callback", new_callable=AsyncMock) as mock_store:
            result = await mgr._send_webhook_once("http://x.test", {"a": 1}, "crawl-1", "failure", timeout=1.0)

        assert result is True
        mock_store.assert_not_awaited()


class TestDeadLetterDrain:
    """Fix B: the reconcile leader drains a bounded batch of FAILED_CALLBACKS_KEY
    per tick, replaying through _send_webhook_with_retry (which re-enqueues on
    exhaustion, so a failed replay cycles back instead of being lost)."""

    @pytest.mark.asyncio
    async def test_deadletter_drain_replays_bounded(self, monkeypatch):
        mgr = _manager()

        entry1 = {"url": "http://x.test/1", "params": {"a": 1}, "crawl_id": "crawl-1", "webhook_type": "failure"}
        entry2 = {"url": "http://x.test/2", "params": {"b": 2}, "crawl_id": "crawl-2", "webhook_type": "stop"}

        mock_cache = MagicMock()
        mock_cache.redis_client = AsyncMock()
        mock_cache.redis_client.lpop = AsyncMock(side_effect=[
            json.dumps(entry1), json.dumps(entry2), None,
        ])
        monkeypatch.setattr(cm_module, "cache_service", mock_cache)

        with patch.object(mgr, "_send_webhook_with_retry", new_callable=AsyncMock) as mock_retry:
            replayed = await mgr._drain_failed_callbacks()
            await asyncio.sleep(0)  # let the fire-and-forget create_task tasks run

        assert replayed == 2
        assert mock_cache.redis_client.lpop.call_count == 3  # 2 entries + terminating None
        mock_retry.assert_any_call("http://x.test/1", {"a": 1}, "crawl-1", "failure")
        mock_retry.assert_any_call("http://x.test/2", {"b": 2}, "crawl-2", "stop")

    @pytest.mark.asyncio
    async def test_deadletter_drain_skips_bad_json(self, monkeypatch):
        mgr = _manager()

        mock_cache = MagicMock()
        mock_cache.redis_client = AsyncMock()
        mock_cache.redis_client.lpop = AsyncMock(side_effect=["not json", None])
        monkeypatch.setattr(cm_module, "cache_service", mock_cache)

        with patch.object(mgr, "_send_webhook_with_retry", new_callable=AsyncMock) as mock_retry:
            replayed = await mgr._drain_failed_callbacks()

        assert replayed == 0
        mock_retry.assert_not_awaited()
