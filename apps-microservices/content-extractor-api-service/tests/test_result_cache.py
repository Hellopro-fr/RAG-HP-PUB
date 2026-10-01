import asyncio

from common_utils.redis import cache_service
from app.core import result_cache


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v
        return True


def test_clean_key_deterministic_and_format_sensitive():
    a = result_cache.clean_key("<p>x</p>", "text")
    b = result_cache.clean_key("<p>x</p>", "text")
    c = result_cache.clean_key("<p>x</p>", "html")
    assert a == b
    assert a != c


def test_hf_key_order_insensitive_when_not_debug():
    k1 = result_cache.header_footer_key("M", ["A", "B"], debug=False)
    k2 = result_cache.header_footer_key("M", ["B", "A"], debug=False)
    assert k1 == k2


def test_hf_key_order_sensitive_when_debug():
    k1 = result_cache.header_footer_key("M", ["A", "B"], debug=True)
    k2 = result_cache.header_footer_key("M", ["B", "A"], debug=True)
    assert k1 != k2


def test_get_set_never_raise_without_client(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert asyncio.run(result_cache.get("k")) is None
    asyncio.run(result_cache.set("k", {"content": "x"}))  # must not raise


def test_roundtrip_with_fake_client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    key = result_cache.clean_key("<p>y</p>", "text")
    asyncio.run(result_cache.set(key, {"content": "y", "format": "text", "content_length": 1}))
    got = asyncio.run(result_cache.get(key))
    assert got == {"content": "y", "format": "text", "content_length": 1}
