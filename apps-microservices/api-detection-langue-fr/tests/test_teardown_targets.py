"""Liveness guards on browser teardown (2026-08-03).

On a failed scrape the page/context/browser are usually already gone, so every
teardown op raises TargetClosedError. Each one burned up to TEARDOWN_TIMEOUT_S,
and `unroute_all` on a dead page is what made Playwright schedule its internal
_update_interceptor_patterns task — the giant repeated traceback in prod logs.
"""
import pytest

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
async def test_all_live_closes_everything():
    page, context, browser = _StubPage(), _StubContext(), _StubBrowser()
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert page.unroute_calls == 1
    assert context.close_calls == 1
    assert browser.close_calls == 1


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


@pytest.mark.asyncio
async def test_exception_inside_teardown_never_propagates():
    class _Exploding(_StubContext):
        async def close(self):
            raise RuntimeError("boom during teardown")

    browser = _StubBrowser()
    # Must not raise: this helper runs inside a `finally`, so propagating
    # would mask whatever error the scrape was already unwinding.
    await _teardown_targets(_StubPage(), _Exploding(), browser, "https://example.fr")


@pytest.mark.asyncio
async def test_single_definition_in_source():
    """The teardown block must exist once, not duplicated per scrape function."""
    import inspect
    import app.services.scraper as scraper
    src = inspect.getsource(scraper)
    assert src.count("unroute_all(behavior='ignoreErrors')") == 1, (
        "teardown is still duplicated across the two scrape functions"
    )
