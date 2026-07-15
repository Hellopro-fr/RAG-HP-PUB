"""Cache must never persist `admission_rejected` results.

Service saturation is transient infrastructure state; persisting it would
poison the domain-keyed cache with a non-answer.
"""
import pytest

from common_utils.redis import cache_service
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

    monkeypatch.setattr(cache_service, 'redis_client', FakeClient(), raising=False)

    # Control: a cacheable method DOES reach setex through this seam —
    # guards the test against passing vacuously if the client wiring breaks
    # (set() early-returns on a None/mis-patched client before the
    # _NEVER_CACHE_METHODS guard).
    await cache.set(
        input_url='https://example.com/path',
        result_url='https://example.com/path',
        result={'ok': True, 'method': 'langHtml',
                'url': 'https://example.com/path'},
    )
    assert len(calls) == 1
    calls.clear()

    await cache.set(
        input_url='https://example.com/path',
        result_url='https://example.com/path',
        result={'ok': False, 'method': 'admission_rejected',
                'url': 'https://example.com/path',
                'error': 'Service temporarily saturated'},
    )

    assert calls == []
