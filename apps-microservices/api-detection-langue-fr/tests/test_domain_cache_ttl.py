import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.domain_fr import DomainCache


@pytest.fixture
def cache_with_mock_redis():
    cache = DomainCache()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.setex = AsyncMock()
    cache._client = mock_client
    cache._initialized = True
    return cache, mock_client


class TestTtlOverride:
    @pytest.mark.asyncio
    async def test_ttl_override_used_when_provided(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": False, "method": "http_error", "url": "https://example.com/page"}
        await cache.set(
            "https://example.com/page", "https://example.com/page",
            result, ttl_override=604800,
        )
        # First setex call: TTL must be 604800
        assert client.setex.await_count >= 1
        ttl_used = client.setex.await_args_list[0].args[1]
        assert ttl_used == 604800

    @pytest.mark.asyncio
    async def test_ttl_override_none_falls_back_to_existing_logic(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        await cache.set("https://example.com/", "https://example.com/", result, ttl_override=None)
        ttl_used = client.setex.await_args_list[0].args[1]
        assert ttl_used == cache.TTL_OK  # 30 days


class TestRequestedUrlField:
    @pytest.mark.asyncio
    async def test_requested_url_persisted_in_payload(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        await cache.set(
            "https://example.com/some/path", "https://example.com/", result,
        )
        # The serialized payload must carry requested_url == input_url
        payload_json = client.setex.await_args_list[0].args[2]
        payload = json.loads(payload_json)
        assert payload["requested_url"] == "https://example.com/some/path"

    @pytest.mark.asyncio
    async def test_old_payload_without_requested_url_reads_back(self):
        """Forward compat: an old entry lacking 'requested_url' should still be readable."""
        cache = DomainCache()
        mock_client = MagicMock()
        old_payload = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        mock_client.get = AsyncMock(return_value=json.dumps(old_payload))
        cache._client = mock_client
        cache._initialized = True

        loaded = await cache.get("https://example.com/")
        assert loaded == old_payload  # No KeyError; missing field gracefully absent
