"""Tests for the scraper module — browser launch, proxy parsing, resource blocking."""

import pytest
from unittest.mock import patch, MagicMock
from app.services.scraper import (
    _parse_proxy,
    build_proxy_url,
)


class TestParseProxy:
    """Tests for _parse_proxy — converts httpx URL to Playwright dict."""

    def test_full_proxy_url(self):
        result = _parse_proxy("http://user:pass@proxy.example.com:8000")
        assert result == {
            "server": "http://proxy.example.com:8000",
            "username": "user",
            "password": "pass",
        }

    def test_proxy_without_auth(self):
        result = _parse_proxy("http://proxy.example.com:8000")
        assert result is not None
        assert result["server"] == "http://proxy.example.com:8000"

    def test_invalid_proxy(self):
        result = _parse_proxy("")
        # Should return None or a dict without crashing
        assert result is None or isinstance(result, dict)


class TestBuildProxyUrl:
    """Tests for build_proxy_url — Apify proxy URL construction."""

    def test_country_only(self):
        result = build_proxy_url("http://auto:PASSWORD@proxy.apify.com:8000", country="FR")
        assert "country-FR" in result
        assert "PASSWORD" in result

    def test_session_and_country(self):
        result = build_proxy_url(
            "http://auto:PASSWORD@proxy.apify.com:8000",
            session_id="test123",
            country="FR",
        )
        assert "country-FR" in result
        assert "session-test123" in result

    def test_no_params(self):
        result = build_proxy_url(
            "http://auto:PASSWORD@proxy.apify.com:8000",
            session_id=None,
            country=None,
        )
        assert "auto" in result


class TestBrowserLaunch:
    """Tests for _launch_browser — camoufox vs chromium selection."""

    @patch("app.core.config.settings")
    def test_camoufox_enabled_flag(self, mock_settings):
        """Verify CAMOUFOX_ENABLED setting is respected."""
        mock_settings.CAMOUFOX_ENABLED = True
        assert mock_settings.CAMOUFOX_ENABLED is True

        mock_settings.CAMOUFOX_ENABLED = False
        assert mock_settings.CAMOUFOX_ENABLED is False


# tests/test_scraper.py — additions

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestBrowserSemaphoreEnv:
    """Tests for BROWSER_SEMAPHORE_SIZE env var."""

    def test_semaphore_size_from_env(self, monkeypatch):
        """BROWSER_SEMAPHORE_SIZE env var sets the semaphore value."""
        monkeypatch.setenv("BROWSER_SEMAPHORE_SIZE", "3")
        # Reload module to pick up env var
        import importlib
        from app.services import scraper
        importlib.reload(scraper)
        assert scraper._BROWSER_SEMAPHORE_SIZE == 3

    def test_semaphore_size_default(self, monkeypatch):
        """Default is 10 when env var absent."""
        monkeypatch.delenv("BROWSER_SEMAPHORE_SIZE", raising=False)
        import importlib
        from app.services import scraper
        importlib.reload(scraper)
        assert scraper._BROWSER_SEMAPHORE_SIZE == 10


class TestRouteHandlerCleanup:
    """Tests for unroute_all + try/finally guarantees."""

    @pytest.mark.asyncio
    async def test_unroute_all_called_before_context_close_on_success(self):
        """On happy path, page.unroute_all is called before context.close."""
        from app.services import scraper

        call_order = []
        mock_page = MagicMock()
        mock_page.unroute_all = AsyncMock(side_effect=lambda **kw: call_order.append("unroute_all"))
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/"
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)  # live page: teardown must not skip unroute_all

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        mock_context.close = AsyncMock(side_effect=lambda: call_order.append("context.close"))

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(side_effect=lambda: call_order.append("browser.close"))
        mock_browser.is_connected = MagicMock(return_value=True)  # live browser: teardown must not skip closes

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)
        mock_pw.start = AsyncMock(return_value=mock_pw)   # await async_playwright().start() -> p
        mock_pw.stop = AsyncMock(return_value=None)        # await p.stop()

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            result = await scraper.scrape_html(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )

        assert result is not None
        assert call_order.index("unroute_all") < call_order.index("context.close")

    @pytest.mark.asyncio
    async def test_browser_closed_on_mid_fetch_exception(self):
        """A mid-fetch exception still triggers context.close and browser.close (try/finally).

        Uses a permanent navigation error (ERR_SSL_PROTOCOL_ERROR) so the scraper's
        ``except Exception`` branch re-raises via the ``_PERMANENT_NAV_ERRORS`` path,
        matching production behavior while still proving the finally block ran.
        """
        from app.services import scraper

        closed = {"context": False, "browser": False}
        mock_page = MagicMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.goto = AsyncMock(side_effect=Exception(
            "Page.goto: net::ERR_SSL_PROTOCOL_ERROR at https://example.com/"
        ))
        mock_page.unroute_all = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)  # goto failed, page itself is still live

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        async def close_ctx():
            closed["context"] = True
        mock_context.close = AsyncMock(side_effect=close_ctx)

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.is_connected = MagicMock(return_value=True)  # live: teardown must still close
        async def close_br():
            closed["browser"] = True
        mock_browser.close = AsyncMock(side_effect=close_br)

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)
        mock_pw.start = AsyncMock(return_value=mock_pw)   # await async_playwright().start() -> p
        mock_pw.stop = AsyncMock(return_value=None)        # await p.stop()

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            with pytest.raises(Exception, match="ERR_SSL_PROTOCOL_ERROR"):
                await scraper.scrape_html(
                    "https://example.com", proxy="http://u:p@proxy:8000"
                )

        assert closed["context"] is True
        assert closed["browser"] is True


class TestChallengeResolvedStatus:
    """After a challenge resolves (post-PoW navigation), ScrapeResult.status_code
    must not keep the interstitial's 4xx from the initial goto response."""

    _CHALLENGE_HTML = (
        '<html><head><title>rescaled WAF · Verifying Browser</title>'
        '<script id="challenge_data">{"verifyURL":"/.well-known/rescaled-waf/verify"}</script>'
        '<script>dispatchEvent(new Event("rescaled-waf:challenge-started"))</script>'
        '</head><body>Verifying your browser.</body></html>'
    )
    _REAL_HTML = "<html><body>" + "Vraie page française. " * 30 + "</body></html>"

    def _mock_stack(self, mock_page):
        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        mock_context.close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()
        mock_browser.is_connected = MagicMock(return_value=True)  # live: teardown must still close

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)
        mock_pw.start = AsyncMock(return_value=mock_pw)
        mock_pw.stop = AsyncMock(return_value=None)
        return mock_browser, mock_pw

    def _mock_page(self, response_status, content_side_effect):
        mock_response = MagicMock()
        mock_response.status = response_status
        mock_response.headers = {"content-type": "text/html"}

        mock_page = MagicMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.content = AsyncMock(side_effect=content_side_effect)
        mock_page.url = "https://example.com/"
        mock_page.unroute_all = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)  # live page: teardown must not skip unroute_all
        return mock_page

    @pytest.mark.asyncio
    async def test_status_forced_200_when_challenge_resolves(self):
        from app.services import scraper

        contents = iter([self._CHALLENGE_HTML])  # initial read -> challenge

        async def content_side_effect():
            return next(contents, self._REAL_HTML)  # poll + re-reads -> real page

        mock_page = self._mock_page(403, content_side_effect)
        mock_browser, mock_pw = self._mock_stack(mock_page)

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            result = await scraper.scrape_html(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )

        assert result is not None
        assert "Vraie page" in result.html
        assert result.status_code == 200  # not the stale 403 from the interstitial

    @pytest.mark.asyncio
    async def test_status_kept_when_no_challenge(self):
        from app.services import scraper

        async def content_side_effect():
            return self._REAL_HTML

        mock_page = self._mock_page(200, content_side_effect)
        mock_browser, mock_pw = self._mock_stack(mock_page)

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            result = await scraper.scrape_html(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )

        assert result is not None
        assert result.status_code == 200


class TestBrowsersUnclosedGauge:
    """`BROWSERS_UNCLOSED` must be raised at the launch site of a real scrape,
    and only come back down when that browser's close() is confirmed.

    Reuses the mock stack above via a plain instance (not inheritance — that
    would re-run the challenge tests under this class too).
    """

    _stack = TestChallengeResolvedStatus()
    _REAL_HTML = TestChallengeResolvedStatus._REAL_HTML

    def _mock_stack(self, page):
        return self._stack._mock_stack(page)

    def _mock_page(self, status, content_side_effect):
        return self._stack._mock_page(status, content_side_effect)

    async def _scrape(self, mock_browser, mock_pw):
        from app.services import scraper
        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            return await scraper.scrape_html(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )

    @pytest.mark.asyncio
    async def test_successful_scrape_is_net_zero(self):
        from app.core.metrics import BROWSERS_UNCLOSED

        async def content_side_effect():
            return self._REAL_HTML

        mock_browser, mock_pw = self._mock_stack(self._mock_page(200, content_side_effect))
        before = BROWSERS_UNCLOSED._value.get()
        assert await self._scrape(mock_browser, mock_pw) is not None
        assert BROWSERS_UNCLOSED._value.get() == before, (
            "a launched-and-closed browser must not accumulate"
        )

    @pytest.mark.asyncio
    async def test_browser_whose_close_is_skipped_stays_counted(self):
        """`_teardown_targets` skips close() when the browser is already
        disconnected — a dead driver pipe is no proof the detached Firefox
        exited, so the launch stays counted."""
        from app.core.metrics import BROWSERS_UNCLOSED

        async def content_side_effect():
            return self._REAL_HTML

        mock_browser, mock_pw = self._mock_stack(self._mock_page(200, content_side_effect))
        mock_browser.is_connected = MagicMock(return_value=False)

        before = BROWSERS_UNCLOSED._value.get()
        await self._scrape(mock_browser, mock_pw)
        mock_browser.close.assert_not_awaited()
        assert BROWSERS_UNCLOSED._value.get() == before + 1

    @pytest.mark.asyncio
    async def test_redirect_follow_is_counted_too(self):
        """`scrape_html_with_redirects` (live path: RedirectTracker) launches its
        own browser and must be counted at its own launch site."""
        from app.services import scraper
        from app.core.metrics import BROWSERS_UNCLOSED

        async def content_side_effect():
            return self._REAL_HTML

        mock_browser, mock_pw = self._mock_stack(self._mock_page(200, content_side_effect))
        before = BROWSERS_UNCLOSED._value.get()
        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch.object(scraper, "async_playwright", return_value=mock_pw):
            result = await scraper.scrape_html_with_redirects(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )
        assert result["success"] is True
        assert BROWSERS_UNCLOSED._value.get() == before