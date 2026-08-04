"""Liveness guards on browser teardown (2026-08-03).

On a failed scrape the page/context/browser are usually already gone, so every
teardown op raises TargetClosedError. Each one burned up to TEARDOWN_TIMEOUT_S,
and `unroute_all` on a dead page is what made Playwright schedule its internal
_update_interceptor_patterns task — the giant repeated traceback in prod logs.
"""
import re

import pytest

import app.services.scraper as scraper
from app.services.scraper import _teardown_targets


class _StubPage:
    def __init__(self, closed=False):
        self._closed = closed
        self.unroute_calls = 0

    def is_closed(self):
        return self._closed

    async def unroute_all(self, behavior=None):
        self.unroute_calls += 1


class _StubContext:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class _StubBrowser:
    def __init__(self, connected=True):
        self._connected = connected
        self.close_calls = 0

    def is_connected(self):
        return self._connected

    async def close(self):
        self.close_calls += 1


@pytest.mark.asyncio
async def test_all_live_closes_everything(monkeypatch):
    calls = []

    async def recorder(coro, timeout, what=""):
        # Passthrough: still awaits the coroutine so the call-count
        # assertions below keep working, but pins that every teardown op
        # actually goes through _close_or_abandon (the abandon-on-timeout
        # bound), not a bare await that would silently drop it.
        calls.append(what)
        await coro

    monkeypatch.setattr(scraper, "_close_or_abandon", recorder)

    page, context, browser = _StubPage(), _StubContext(), _StubBrowser()
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert page.unroute_calls == 1
    assert context.close_calls == 1
    assert browser.close_calls == 1
    assert len(calls) == 3, "_close_or_abandon must wrap all three teardown ops"


@pytest.mark.asyncio
async def test_closed_page_skips_unroute():
    page, context, browser = _StubPage(closed=True), _StubContext(), _StubBrowser()
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert page.unroute_calls == 0, "unroute_all on a closed page is the flood trigger"
    assert context.close_calls == 1
    assert browser.close_calls == 1


@pytest.mark.asyncio
async def test_disconnected_browser_skips_both_closes():
    page, context, browser = _StubPage(), _StubContext(), _StubBrowser(connected=False)
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert context.close_calls == 0
    assert browser.close_calls == 0


@pytest.mark.asyncio
async def test_none_page_and_context_are_tolerated():
    browser = _StubBrowser()
    await _teardown_targets(None, None, browser, "https://example.fr")
    assert browser.close_calls == 1


class _BadBrowser(_StubBrowser):
    def is_connected(self):
        raise RuntimeError("connection object already torn down")


@pytest.mark.asyncio
async def test_sync_exception_inside_teardown_never_propagates():
    """A raising liveness predicate must not escape: the helper runs inside a
    `finally`, so propagating would mask the scrape's original error.
    NB the raise must be SYNCHRONOUS — an exception from a coroutine handed to
    _close_or_abandon is drained there and never reaches the helper's body."""
    await _teardown_targets(_StubPage(), _StubContext(), _BadBrowser(), "https://example.fr")


@pytest.mark.asyncio
async def test_single_definition_in_source():
    """The teardown block must exist once, not duplicated per scrape function."""
    import inspect
    src = inspect.getsource(scraper)
    assert len(re.findall(r"\.unroute_all\(", src)) == 1, (
        "teardown is still duplicated across the two scrape functions"
    )
