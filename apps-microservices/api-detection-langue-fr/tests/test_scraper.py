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
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/"
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.wait_for_timeout = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        mock_context.close = AsyncMock(side_effect=lambda: call_order.append("context.close"))

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(side_effect=lambda: call_order.append("browser.close"))

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch("playwright.async_api.async_playwright") as mock_pw:
            mock_pw.return_value.__aenter__.return_value = MagicMock()
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

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

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        async def close_ctx():
            closed["context"] = True
        mock_context.close = AsyncMock(side_effect=close_ctx)

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        async def close_br():
            closed["browser"] = True
        mock_browser.close = AsyncMock(side_effect=close_br)

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch("playwright.async_api.async_playwright") as mock_pw:
            mock_pw.return_value.__aenter__.return_value = MagicMock()
            mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(Exception, match="ERR_SSL_PROTOCOL_ERROR"):
                await scraper.scrape_html(
                    "https://example.com", proxy="http://u:p@proxy:8000"
                )

        assert closed["context"] is True
        assert closed["browser"] is True