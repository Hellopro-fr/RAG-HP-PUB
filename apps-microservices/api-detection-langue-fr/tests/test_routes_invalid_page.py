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
        """Pass 2 retries the transient set (_PASS2_RETRYABLE_METHODS) only —
        definitive verdicts like http_error (404) / soft_404 are never retried."""
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


_RESCALED_WAF_HTML = (
    '<html><head><title>rescaled WAF · Verifying Browser</title>'
    '<script id="challenge_data">{"verifyURL":"/.well-known/rescaled-waf/verify"}</script>'
    '<script>dispatchEvent(new Event("rescaled-waf:challenge-started"))</script>'
    '</head><body>Verifying your browser.</body></html>'
)


class TestDetectDebugTraceHonesty:
    """/detect-debug must record the raw HTTP status and mirror the prod
    challenge-wins / transient reclassification (spec 2026-07-25)."""

    @pytest.mark.asyncio
    async def test_debug_records_status_and_challenge_page(self, client):
        # lagff.com case: 403 + WAF interstitial body → prod says challenge_page;
        # debug must agree and expose the 403 in the trace.
        scrape = _scrape(html=_RESCALED_WAF_HTML, status_code=403,
                         final_url="https://example.com/")
        with patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect-debug", json={"url": "https://example.com/"})
        body = r.json()
        assert body["debug"]["fetch"]["status_code"] == 403
        assert body["debug"]["fetch"]["challenge_detected"] == "Rescaled_WAF"
        assert body["result"]["method"] == "challenge_page"

    @pytest.mark.asyncio
    async def test_debug_transient_status_reclassified(self, client):
        # 403 with a plain (non-challenge) body → http_error_transient, like prod.
        scrape = _scrape(status_code=403)
        with patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect-debug", json={"url": "https://example.com/"})
        body = r.json()
        assert body["debug"]["fetch"]["status_code"] == 403
        assert body["result"]["method"] == "http_error_transient"

    @pytest.mark.asyncio
    async def test_debug_status_none_when_html_provided(self, client):
        r = client.post("/api/v1/detect-debug", json={
            "url": "https://example.com/",
            "html_content": '<html lang="fr"><body>' + "Bonjour à tous. " * 20 + "</body></html>",
        })
        body = r.json()
        assert body["debug"]["fetch"]["status_code"] is None


_CLOUDFLARE_CHALLENGE_HTML = (
    '<html><head><title>Just a moment...</title></head>'
    '<body><script src="cdn-cgi/challenge-platform/v1/orchestrate/chl_page/v1"></script>'
    '<input name="cf-turnstile-response" />'
    '<noindex></body></html>'
)


class TestTransientHttpError:
    @pytest.mark.asyncio
    async def test_403_with_challenge_body_is_challenge_page(self, client):
        """A 403 whose body is a Cloudflare challenge is a WAF block (retryable),
        not a definitive http_error — validator status check must not win."""
        scrape = _scrape(
            html=_CLOUDFLARE_CHALLENGE_HTML,
            final_url="https://example.com/", status_code=403,
        )
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()) as set_mock, \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/"})
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "challenge_page"
        # Same contract as the main-path challenge: not cached at the fetch path.
        set_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_429_is_http_error_transient_with_short_ttl(self, client):
        """Rate-limit 429 → http_error_transient, cached TTL_TRANSIENT (6h), not 7d."""
        from app.core.domain_fr import domain_cache
        scrape = _scrape(status_code=429, final_url="https://example.com/")
        set_mock = AsyncMock()
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", set_mock), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/"})
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "http_error_transient"
        assert set_mock.await_args.kwargs["ttl_override"] == domain_cache.TTL_TRANSIENT

    @pytest.mark.asyncio
    async def test_404_stays_definitive_http_error(self, client):
        """404 keeps the 2026-05-05 semantics: http_error, hard TTL."""
        from app.core.config import settings
        scrape = _scrape(status_code=404, final_url="https://example.com/")
        set_mock = AsyncMock()
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", set_mock), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/"})
        body = r.json()
        assert body["method"] == "http_error"
        assert set_mock.await_args.kwargs["ttl_override"] == settings.INVALID_PAGE_TTL_HARD_S

    @pytest.mark.asyncio
    async def test_404_with_thin_error_body_stays_http_error(self, client):
        """detect_challenge_page's generic HTTP_xxx_blocked verdict (thin error
        page) must NOT reclassify a real 404 as retryable challenge_page."""
        scrape = _scrape(
            html="<html><head><title>404 - Not Found</title></head><body>gone</body></html>",
            final_url="https://example.com/missing", status_code=404,
        )
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        assert r.json()["method"] == "http_error"

    @pytest.mark.asyncio
    async def test_batch_pass2_retries_http_error_transient(self, client):
        """503 in Pass 1 → recovered FR page in Pass 2."""
        transient = _scrape(status_code=503, final_url="https://example.fr/")
        fr_text = (
            "Bienvenue sur notre site. Nous concevons et fabriquons des "
            "équipements industriels pour les professionnels depuis 1985. "
            "Découvrez nos produits et demandez un devis gratuit. "
        )
        recovered = _scrape(
            html='<html lang="fr"><body>' + fr_text * 5 + "</body></html>",
            final_url="https://example.fr/", status_code=200,
        )
        fetch_mock = AsyncMock(side_effect=[transient, recovered])
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock), \
             patch("app.api.routes.asyncio.sleep", AsyncMock()):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.fr/"}],
                "max_concurrency": 1,
            })
        body = r.json()
        assert fetch_mock.await_count == 2
        assert body["results"][0]["ok"] is True

    @pytest.mark.asyncio
    async def test_batch_pass2_retry_bypasses_cache_read(self, client):
        """Pass-2 retry must run with force_refresh=True — the Pass-1 transient
        rejection was just cached (6h) and would short-circuit the retry."""
        from app.api import routes as routes_mod
        calls = []

        async def fake_detect(url, **kwargs):
            calls.append(kwargs.get("force_refresh"))
            from app.models.schemas import DetectionResponse
            if len(calls) == 1:
                return DetectionResponse(ok=False, url=url, method="http_error_transient")
            return DetectionResponse(ok=True, url=url, method="direct_match")

        with patch.object(routes_mod, "_detect_single_url", fake_detect), \
             patch("app.api.routes.asyncio.sleep", AsyncMock()):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.fr/"}],
                "max_concurrency": 1,
            })
        body = r.json()
        assert body["results"][0]["ok"] is True
        assert calls == [False, True]  # Pass 1 default, Pass 2 forced


class TestStubPageHop:
    _STUB_HTML = (
        '<html><head><title>Moved</title></head>'
        '<body>Page has moved. <a href="/fr.html">Click here...</a></body></html>'
    )
    _FR_HTML = (
        '<html lang="fr"><body>'
        + (
            "Bienvenue sur notre site. Nous concevons et fabriquons des "
            "équipements industriels pour les professionnels depuis 1985. "
        ) * 5
        + "</body></html>"
    )

    @pytest.mark.asyncio
    async def test_stub_homepage_hops_to_target(self, client):
        stub = _scrape(html=self._STUB_HTML, final_url="https://www.example.fr/", status_code=200)
        target = _scrape(html=self._FR_HTML, final_url="https://www.example.fr/fr.html", status_code=200)
        fetch_mock = AsyncMock(side_effect=[stub, target])
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect", json={"url": "https://www.example.fr/"})
        body = r.json()
        assert fetch_mock.await_count == 2
        assert body["ok"] is True
        assert body["analyzed_url"] == "https://www.example.fr/fr.html"

    @pytest.mark.asyncio
    async def test_stub_hop_failure_keeps_stub_flow(self, client):
        """Hop target fetch fails → detection continues on the stub content
        (ends as fetch_empty_content, which Pass 2 can retry)."""
        stub = _scrape(html=self._STUB_HTML, final_url="https://www.example.fr/", status_code=200)
        fetch_mock = AsyncMock(side_effect=[stub, None])
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect", json={"url": "https://www.example.fr/"})
        body = r.json()
        assert fetch_mock.await_count == 2
        assert body["method"] == "fetch_empty_content"

    @pytest.mark.asyncio
    async def test_stub_hop_disabled_by_kill_switch(self, client):
        stub = _scrape(html=self._STUB_HTML, final_url="https://www.example.fr/", status_code=200)
        fetch_mock = AsyncMock(return_value=stub)
        with patch("app.core.config.settings.STUB_PAGE_HOP_ENABLED", False), \
             patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect", json={"url": "https://www.example.fr/"})
        assert fetch_mock.await_count == 1
        assert r.json()["method"] == "fetch_empty_content"


class TestHomepageFallbackChallengePage:
    @pytest.mark.asyncio
    async def test_soft_404_homepage_is_challenge_page(self, client):
        """When the homepage fallback hits a Cloudflare/DataDome challenge page,
        rejection must surface url=requested (not homepage) and analyzed_url=homepage.
        Regression guard for I2 from final whole-impl review."""
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        # Homepage HTML is a Cloudflare challenge page (passes validator since 200
        # + not URL/title soft-404 marker, but detect_challenge_page fires).
        cloudflare_html = (
            '<html><head><title>Just a moment...</title></head>'
            '<body><script src="cdn-cgi/challenge-platform/v1/orchestrate/chl_page/v1"></script>'
            '<input name="cf-turnstile-response" />'
            '<noindex></body></html>'
        )
        homepage_challenge = _scrape(
            html=cloudflare_html,
            final_url="https://example.com/", status_code=200,
        )
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage_challenge])):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "challenge_page"
        # Original requested URL preserved on the rejection — not overwritten by homepage.
        assert body["url"] == "https://example.com/missing"
        # analyzed_url discloses the homepage that produced the challenge verdict.
        assert body["analyzed_url"] == "https://example.com/"
