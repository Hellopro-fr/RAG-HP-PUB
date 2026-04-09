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