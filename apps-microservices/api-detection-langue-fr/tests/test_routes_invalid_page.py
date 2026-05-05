import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from app.services.scraper import ScrapeResult
from app.services.page_validator import ValidationVerdict


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_inflight_dedup():
    """Force dedup off so tests don't share Future state."""
    import os
    os.environ["INFLIGHT_DEDUP_ENABLED"] = "false"
    # Reload routes module to pick up env change.
    import importlib
    from app.api import routes
    importlib.reload(routes)
    # Re-mount router so app sees the reloaded one.
    yield


def _scrape(html="<html><body>FR" + "x" * 200 + "</body></html>",
            final_url="https://example.com/page", status_code=200):
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


class TestCacheHitSameUrl:
    @pytest.mark.asyncio
    async def test_same_url_hit_no_analyzed_url(self, client):
        cached = {
            "ok": True, "url": "https://example.com/", "method": "langHtml",
            "requested_url": "https://example.com/",
        }
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body.get("analyzed_url") is None


class TestCacheHitCrossUrl:
    @pytest.mark.asyncio
    async def test_cross_url_hit_sets_analyzed_url(self, client):
        cached = {
            "ok": True, "url": "https://example.com/", "method": "langHtml",
            "requested_url": "https://example.com/",
        }
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/some/page"})
        body = r.json()
        assert body["ok"] is True
        assert body["analyzed_url"] == "https://example.com/"

    @pytest.mark.asyncio
    async def test_cross_url_hit_old_entry_without_requested_url_field(self, client):
        # Old entry lacks requested_url; falls back to url field.
        cached = {"ok": True, "url": "https://example.com/", "method": "langHtml"}
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/some/page"})
        body = r.json()
        assert body["analyzed_url"] == "https://example.com/"


class TestHttpError:
    @pytest.mark.asyncio
    async def test_404_no_fallback_returns_http_error(self, client):
        scrape = _scrape(status_code=404)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "http_error"


class TestSoft404FallbackSuccess:
    @pytest.mark.asyncio
    async def test_soft_404_then_homepage_success(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing",
            status_code=200,
        )
        homepage = _scrape(
            html='<html lang="fr"><body>' + "Bonjour " * 100 + "</body></html>",
            final_url="https://example.com/",
            status_code=200,
        )
        # First fetch_html call returns soft-404; second returns valid homepage.
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage])):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is True
        assert body["analyzed_url"] == "https://example.com/"


class TestSoft404FallbackAlsoFails:
    @pytest.mark.asyncio
    async def test_soft_404_homepage_also_invalid(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        homepage_bad = _scrape(status_code=503)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage_bad])):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "soft_404"  # Original verdict surfaces
        assert body.get("analyzed_url") is None


class TestRedirectedToHome:
    @pytest.mark.asyncio
    async def test_redirected_to_home_no_fallback(self, client):
        # Server redirects /missing -> /
        scrape = _scrape(final_url="https://example.com/", status_code=200)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "redirected_to_home"


class TestKillSwitches:
    @pytest.mark.asyncio
    async def test_validation_disabled_passes_through(self, client):
        scrape = _scrape(status_code=404)  # Would be http_error, but...
        with patch("app.core.config.settings.INVALID_PAGE_DETECTION_ENABLED", False), \
             patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        # With validation off, the 404's HTML body runs through DomainFR pipeline.
        # We don't assert on ok=true/false (depends on body content); we assert
        # the method is NOT http_error (validator was bypassed).
        body = r.json()
        assert body["method"] != "http_error"

    @pytest.mark.asyncio
    async def test_fallback_disabled_returns_rejection(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        with patch("app.core.config.settings.HOMEPAGE_FALLBACK_ENABLED", False), \
             patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=soft)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "soft_404"


class TestDetectBatchPassesHomepageFallback:
    @pytest.mark.asyncio
    async def test_batch_passes_homepage_fallback_flag(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        homepage = _scrape(
            html='<html lang="fr"><body>' + "Bonjour " * 100 + "</body></html>",
            final_url="https://example.com/", status_code=200,
        )
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage])):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.com/missing"}],
                "homepage_fallback": True,
                "max_concurrency": 1,
            })
        body = r.json()
        assert body["total"] == 1
        assert body["results"][0]["ok"] is True
        assert body["results"][0]["analyzed_url"] == "https://example.com/"

    @pytest.mark.asyncio
    async def test_batch_pass2_does_not_retry_invalid_methods(self, client):
        """Pass 2 retries fetch_failed + challenge_page only — not http_error/soft_404."""
        scrape = _scrape(status_code=404)
        # If Pass 2 retried, fetch_html would be called > 1 time. Assert it's exactly 1.
        fetch_mock = AsyncMock(return_value=scrape)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.com/missing"}],
                "homepage_fallback": False,
                "max_concurrency": 1,
            })
        body = r.json()
        assert body["results"][0]["method"] == "http_error"
        assert fetch_mock.await_count == 1


class TestDetectDebugFallbackOff:
    @pytest.mark.asyncio
    async def test_debug_does_not_trigger_homepage_fallback(self, client):
        scrape = _scrape(status_code=404)
        fetch_mock = AsyncMock(return_value=scrape)
        with patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect-debug", json={
                "url": "https://example.com/missing",
            })
        # /detect-debug returns DebugDetectionResponse; result.method must reflect
        # the verdict, but no homepage hop should occur (only one fetch_html call).
        body = r.json()
        assert body["result"]["method"] == "http_error"
        assert fetch_mock.await_count == 1
