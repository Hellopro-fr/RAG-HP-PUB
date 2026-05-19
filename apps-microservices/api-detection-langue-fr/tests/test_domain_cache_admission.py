"""Cache must never persist `admission_rejected` results.

Service saturation is transient infrastructure state; persisting it would
poison the domain-keyed cache with a non-answer.
"""
import pytest

from app.core.domain_fr import DomainCache


def test_never_cache_methods_includes_admission_rejected():
    assert 'admission_rejected' in DomainCache._NEVER_CACHE_METHODS


def test_never_cache_methods_still_contains_existing_entries():
    assert 'error' in DomainCache._NEVER_CACHE_METHODS
    assert 'fetch_failed' in DomainCache._NEVER_CACHE_METHODS


@pytest.mark.asyncio
async def test_set_is_noop_for_admission_rejected(monkeypatch):
    """Even with a working Redis client, admission_rejected results must not
    be persisted. The early-return guard for _NEVER_CACHE_METHODS fires
    before any setex call."""
    cache = DomainCache()
    calls = []

    class FakeClient:
        async def setex(self, key, ttl, data):
            calls.append((key, ttl, data))

    async def fake_get_client(self):
        return FakeClient()

    monkeypatch.setattr(DomainCache, '_get_client', fake_get_client)

    await cache.set(
        input_url='https://example.com/path',
        result_url='https://example.com/path',
        result={'ok': False, 'method': 'admission_rejected',
                'url': 'https://example.com/path',
                'error': 'Service temporarily saturated'},
    )

    assert calls == []
