"""Tests for the `max_not_eligible_rate` threshold mapping in
app/router/crawler.py::start_new_crawl (not_eligible circuit breaker, A8).

`start_new_crawl` builds `params` and hands it to `crawler_manager.start_crawl`,
which turns each non-None entry into a `--key=value` CLI flag for the Node
crawler. The tests call the endpoint function directly (no server) and capture
the `params` it passes on.
Named test_update_thresholds_* so the TDD gate associates it with crawler.py.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.router.crawler as crawler_router
from app.schemas.crawler import CrawlRequest


def _payload(update_thresholds):
    return CrawlRequest(
        id="domaine_1",
        domain="example.com",
        start_url="https://example.com",
        callback_url="https://api.example.com/done",
        crawl_mode="update",
        previous_crawl_id="domaine_0",
        update_thresholds=update_thresholds,
    )


async def _captured_params(monkeypatch, update_thresholds):
    manager = SimpleNamespace(start_crawl=AsyncMock(return_value="domaine_1"))
    monkeypatch.setattr(crawler_router, "crawler_manager", manager)
    monkeypatch.setattr(crawler_router, "settings", SimpleNamespace(APIFY_PROXY=None))

    await crawler_router.start_new_crawl(_payload(update_thresholds))

    return manager.start_crawl.await_args.kwargs["params"]


@pytest.mark.asyncio
async def test_max_not_eligible_rate_is_mapped_when_present(monkeypatch):
    params = await _captured_params(
        monkeypatch, {"max_error_rate": 0.15, "max_not_eligible_rate": 0.4}
    )

    assert params["maxNotEligibleRate"] == 0.4
    assert params["maxErrorRate"] == 0.15  # neighbour mapping untouched


@pytest.mark.asyncio
async def test_max_not_eligible_rate_zero_is_forwarded(monkeypatch):
    """0 is a value, not 'absent': Node reads it as 'decision 4 disabled'."""
    params = await _captured_params(monkeypatch, {"max_not_eligible_rate": 0.0})

    assert params["maxNotEligibleRate"] == 0.0


@pytest.mark.asyncio
async def test_max_not_eligible_rate_key_absent_when_not_given(monkeypatch):
    params = await _captured_params(monkeypatch, {"max_error_rate": 0.15})

    assert "maxNotEligibleRate" not in params
    assert params["maxErrorRate"] == 0.15
