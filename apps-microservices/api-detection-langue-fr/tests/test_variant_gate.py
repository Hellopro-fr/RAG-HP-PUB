"""Phase-2 URL variants are skipped for failures they cannot fix (2026-08-03).

A hopeless domain cost 3 retries (~140s) PLUS up to 3 variants (~135s) =
~275s, close to the 300s per-item ceiling in _run_batch_core. The item could
be cancelled in flight, and that cancellation orphaned the futures behind
the asyncio flood.

The gate is a DENYLIST on purpose: _VARIANT_ELIGIBLE_ERRORS holds only
Chromium codes while prod runs Camoufox (Firefox), so an allowlist would be
false for every real failure and would skip Phase 2 unconditionally.

The gate also requires that NO attempt failed in a repairable way
(saw_repairable): the _VARIANT_ELIGIBLE_ERRORS break is dead on Camoufox, so
a repairable Gecko failure (SSL/DNS) on an earlier attempt can be followed by
a Timeout on the last attempt — last_error alone would then wrongly hide the
repairable failure and skip variants that could have fixed the domain.
"""
import asyncio

import pytest

import app.services.redirect_tracker as rt


async def _no_sleep(_seconds):
    return None


@pytest.fixture(autouse=True)
def _fast_and_offline(monkeypatch):
    monkeypatch.setattr(rt, "build_proxy_url", lambda *a, **k: "http://proxy:8000")
    monkeypatch.setattr(rt.asyncio, "sleep", _no_sleep)


def _counting_raiser(message, calls):
    async def fake_scrape(target, proxy=None):
        calls.append(target)
        raise RuntimeError(message)
    return fake_scrape


@pytest.mark.asyncio
async def test_timeout_skips_variants(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(
        rt, "scrape_html", _counting_raiser("Timeout 30000ms exceeded.", calls)
    )

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 3, f"variants were still tried: {calls}"
    assert any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_gecko_dns_error_still_tries_variants(monkeypatch):
    """Over-gating guard: Camoufox/Firefox emits NS_ERROR_*, not ERR_*."""
    calls = []
    monkeypatch.setattr(
        rt, "scrape_html", _counting_raiser("NS_ERROR_UNKNOWN_HOST", calls)
    )

    result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 6, (
        "a DNS failure must still reach Phase 2 AND try every variant — the "
        "gate must not be an allowlist keyed on Chromium error codes"
    )


@pytest.mark.asyncio
async def test_empty_content_skips_variants(monkeypatch, caplog):
    calls = []

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        return None  # drives the "Contenu vide ou trop court" branch

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 3, f"variants were still tried: {calls}"
    assert any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_success_on_first_attempt_makes_one_call(monkeypatch, caplog):
    calls = []
    sentinel = object()

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        return sentinel

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is sentinel
    assert len(calls) == 1
    assert not any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_empty_message_timeout_error_skips_variants(monkeypatch, caplog):
    """Regression guard for Important-1: asyncio.TimeoutError()/TimeoutError()
    raised with no args has str(e) == '' (e.g. the un-caught wait_for around
    the Chromium fallback launch in scraper.py). Without the
    `or type(e).__name__` fallback in fetch_html, `last_error and ...` would
    short-circuit false and all 3 variants would run pointlessly."""
    calls = []

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        raise asyncio.TimeoutError()  # empty message: str(e) == ''

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 3, f"variants were still tried: {calls}"
    assert any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_gecko_ssl_then_timeout_still_tries_variants(monkeypatch, caplog):
    """Regression guard for Important-2: a repairable Gecko SSL failure on
    attempts 1-2 followed by a Timeout on attempt 3 must still reach Phase 2
    — saw_repairable must not let the final Timeout mask the earlier
    repairable failure."""
    calls = []

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        if len(calls) <= 2:
            raise RuntimeError("SEC_ERROR_EXPIRED_CERTIFICATE")
        raise RuntimeError("Timeout 30000ms exceeded.")

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 6, f"variants were skipped: {calls}"
    assert not any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_existing_tuples_untouched():
    assert rt._VARIANT_ELIGIBLE_ERRORS == (
        'ERR_NAME_NOT_RESOLVED',
        'ERR_CERT_DATE_INVALID',
        'ERR_SSL_PROTOCOL_ERROR',
    )
    assert rt._NON_RETRYABLE_ERRORS == rt._VARIANT_ELIGIBLE_ERRORS + rt._FATAL_ERRORS
