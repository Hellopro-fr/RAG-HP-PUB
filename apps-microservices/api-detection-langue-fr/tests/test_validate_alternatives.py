"""Tests for the validate_alternatives skip-all flag.
Spec: docs/superpowers/specs/2026-06-04-detection-langue-fr-validate-alternatives-flag-design.md
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from app.api.routes import _run_batch_core
from app.models.schemas import (
    DetectionRequest,
    BatchDetectionRequest,
    AsyncBatchSubmitRequest,
    BatchItem,
    BatchOpts,
    DetectionMode,
)

HTML_WITH_ALTS = (
    '<html lang="fr"><head>'
    '<link rel="alternate" hreflang="fr-FR" href="https://example.com/fr-FR/">'
    '</head><body><a href="https://example.com/fr/page">Version FR</a>'
    '<p>Contenu en français.</p></body></html>'
)


class TestValidateAlternativesSchema:
    def test_detection_request_default_true(self):
        assert DetectionRequest(url="https://example.com").validate_alternatives is True

    def test_detection_request_accepts_false(self):
        req = DetectionRequest(url="https://example.com", validate_alternatives=False)
        assert req.validate_alternatives is False

    def test_batch_request_default_true(self):
        req = BatchDetectionRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_async_submit_request_default_true(self):
        req = AsyncBatchSubmitRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_batch_opts_default_true_and_overridable(self):
        assert BatchOpts().validate_alternatives is True
        assert BatchOpts(validate_alternatives=False).validate_alternatives is False

    def test_batch_request_accepts_false(self):
        req = BatchDetectionRequest(
            items=[BatchItem(url="https://example.com")],
            validate_alternatives=False,
        )
        assert req.validate_alternatives is False

    def test_async_submit_request_accepts_false(self):
        req = AsyncBatchSubmitRequest(
            items=[BatchItem(url="https://example.com")],
            validate_alternatives=False,
        )
        assert req.validate_alternatives is False


class TestValidateAlternativesRoute:
    def test_detect_flag_false_no_browser_alts_present(self):
        client = TestClient(app)
        with patch("app.core.domain_fr.fetch_html", new=AsyncMock()) as fetch_spy, \
             patch("app.services.scraper.scrape_html", new=AsyncMock()) as scrape_spy:
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com",
                "html_content": HTML_WITH_ALTS,
                "mode": "complete",
                "validate_alternatives": False,
            })
        assert r.status_code == 200
        body = r.json()
        # hreflang alt was parsed and returned even though nothing was validated over HTTP.
        assert any(a["method"] == "hreflang" for a in body["alternative_urls"])
        fetch_spy.assert_not_awaited()
        scrape_spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batch_core_threads_flag(self):
        items = [BatchItem(url="https://example.com", html_content=HTML_WITH_ALTS)]
        opts = BatchOpts(validate_alternatives=False)
        with patch("app.core.domain_fr.fetch_html", new=AsyncMock()) as fetch_spy:
            results, _ = await _run_batch_core(items, DetectionMode.COMPLETE, opts)
        fetch_spy.assert_not_awaited()
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 2026-07-25 deep-dive fixes (spec: 2026-07-25-detection-langue-fr-challenge-
# noscript-altprobe-design.md)
# ---------------------------------------------------------------------------

from app.core.domain_fr import DomainFR
from app.models.schemas import AlternativeUrl, DetectionResponse

# Analogue of siderosengineering.com: Italian page whose ONLY locale URLs are
# self-referencing (canonical + hreflang="it") — zero French references.
SIDEROS_LIKE_HTML = (
    '<html lang="it"><head>'
    '<link rel="canonical" href="https://www.example.com/home-page-it">'
    '<link rel="alternate" hreflang="it" href="https://www.example.com/home-page-it">'
    '</head><body><p>Contenuto italiano della homepage aziendale.</p></body></html>'
)


class TestLangSubstitutionProbe:
    def test_synthesizes_fr_url_from_declared_lang(self):
        d = DomainFR(homepage="https://www.example.com/home-page-it")
        urls = d._synthesize_lang_substitution_urls(SIDEROS_LIKE_HTML)
        assert urls == ["https://www.example.com/home-page-fr"]

    def test_no_lang_token_in_path_yields_nothing(self):
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://www.example.com/">'
                '</head><body></body></html>')
        d = DomainFR(homepage="https://www.example.com/")
        assert d._synthesize_lang_substitution_urls(html) == []

    def test_token_inside_word_not_substituted(self):
        # 'it' inside '/items' must not become '/frems'
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://www.example.com/items">'
                '</head><body></body></html>')
        d = DomainFR(homepage="https://www.example.com/items")
        assert d._synthesize_lang_substitution_urls(html) == []

    def test_cross_host_canonical_ignored(self):
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://other.example.net/home-page-it">'
                '</head><body></body></html>')
        d = DomainFR(homepage="https://www.example.com/")
        assert d._synthesize_lang_substitution_urls(html) == []

    @pytest.mark.asyncio
    async def test_probe_queued_when_zero_candidates(self):
        d = DomainFR(homepage="https://www.example.com/home-page-it")
        captured = []

        async def capture(candidates):
            captured.extend(candidates)
            return []

        with patch.object(d, "_validate_alternative_urls", new=AsyncMock(side_effect=capture)):
            await d.detect_alternative_languages(SIDEROS_LIKE_HTML)
        assert [c for c in captured if c["method"] == "lang_substitution"], captured
        assert captured[0]["url"] == "https://www.example.com/home-page-fr"

    @pytest.mark.asyncio
    async def test_probe_skipped_when_candidates_exist(self):
        # Page that WOULD synthesize (lang=it + canonical /home-page-it) but
        # already advertises a FR link — the zero-candidate guard must skip
        # the probe (fails if the guard is removed).
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://www.example.com/home-page-it">'
                '</head><body><a href="https://www.example.com/fr/">Français</a>'
                '<p>Contenuto.</p></body></html>')
        d = DomainFR(homepage="https://www.example.com/home-page-it")
        captured = []

        async def capture(candidates):
            captured.extend(candidates)
            return []

        with patch.object(d, "_validate_alternative_urls", new=AsyncMock(side_effect=capture)):
            await d.detect_alternative_languages(html)
        assert captured, "the /fr/ link must be queued"
        assert not [c for c in captured if c["method"] == "lang_substitution"]

    def test_multi_occurrence_substituted_one_at_a_time(self):
        # /it/it-support: one candidate per occurrence, never /fr/fr-support
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://www.example.com/it/it-support">'
                '</head><body></body></html>')
        d = DomainFR(homepage="https://www.example.com/it/it-support")
        urls = d._synthesize_lang_substitution_urls(html)
        assert urls == [
            "https://www.example.com/fr/it-support",
            "https://www.example.com/it/fr-support",
        ]

    def test_uppercase_token_keeps_case(self):
        html = ('<html lang="it"><head>'
                '<link rel="canonical" href="https://www.example.com/IT/chi-siamo">'
                '</head><body></body></html>')
        d = DomainFR(homepage="https://www.example.com/IT/chi-siamo")
        assert d._synthesize_lang_substitution_urls(html) == [
            "https://www.example.com/FR/chi-siamo"
        ]


class TestSelfRedirectRejection:
    def test_redirect_back_to_analyzed_page_rejected(self):
        # metaga case: candidate metaga.fr 301s to the Spanish page under analysis
        d = DomainFR(homepage="https://metaga.es/")
        assert d._redirects_to_analyzed_page("https://metaga.fr/", "https://metaga.es/") is True

    def test_redirect_back_to_original_homepage_rejected(self):
        d = DomainFR(homepage="https://metaga.es/", original_homepage="https://www.metaga.fr")
        assert d._redirects_to_analyzed_page(
            "https://metaga.fr/", "https://www.metaga.fr/"
        ) is True

    def test_no_redirect_not_rejected(self):
        d = DomainFR(homepage="https://metaga.es/")
        assert d._redirects_to_analyzed_page("https://example.fr/", "https://example.fr/") is False

    def test_redirect_elsewhere_not_rejected(self):
        d = DomainFR(homepage="https://example.com/")
        assert d._redirects_to_analyzed_page(
            "https://example.com/fr-old", "https://example.com/fr"
        ) is False

    def test_missing_final_url_not_rejected(self):
        d = DomainFR(homepage="https://example.com/")
        assert d._redirects_to_analyzed_page("https://example.fr/", None) is False

    def test_cookie_switcher_same_path_not_rejected(self):
        # /?lang=fr → 302 → / (query dropped, cookie set): same location,
        # must be judged on content, not rejected as a dead switcher.
        d = DomainFR(homepage="https://example.com/")
        assert d._redirects_to_analyzed_page(
            "https://example.com/?lang=fr", "https://example.com/"
        ) is False


class TestDecisionCaseHonesty:
    _ALTS = [AlternativeUrl(url="https://metaga.fr/", method="domain_fr_link",
                            reliability="medium", validated=True)]

    def _case(self, result):
        return DomainFR._identify_decision_case(
            nlp_confirms_french=False, is_strong_url=False,
            nlp_strongly_contradicts=True, nlp_soft_french=False,
            nlp_available=True, nlp_contradicts_french=True,
            url_indicates_french=False, html_indicates_french=False,
            alternatives=self._ALTS, result=result,
        )

    def test_case6_found_only_when_alternative_method(self):
        confirmed = DetectionResponse(
            ok=True, url="https://metaga.fr/",
            method="alternative_domain_fr_link+nlp_confirmed",
        )
        assert self._case(confirmed).startswith("Case 6: Alternative French URL found")

    def test_case6_attempted_when_rejected(self):
        rejected = DetectionResponse(ok=False, url="https://metaga.es/", method="Check_nok_v2")
        decision = self._case(rejected)
        assert decision.startswith("Case 6 attempted:")
        assert "none confirmed French" in decision
        assert decision.endswith("→ Case 9")

    def test_case6_attempted_non_case9_result_named(self):
        blocked = DetectionResponse(ok=False, url="https://x.example/", method="challenge_page")
        decision = self._case(blocked)
        assert decision.startswith("Case 6 attempted:")
        assert "(result: challenge_page)" in decision


class TestCase9KeepsAlternativesEmpty:
    @pytest.mark.asyncio
    async def test_check_nok_v2_does_not_expose_alternatives(self):
        """Contract pin: crawler routes.ts + BO not_french_signal.php treat
        'ok=false + non-empty alternative_urls' as a DIFFERENT signal than
        not_french — Case 9 must keep the list empty (diagnosis lives in
        /detect-debug's debug.alternatives)."""
        english = "<p>" + "This is plain English corporate content for testing. " * 10 + "</p>"
        html = ('<html><head><title>Corp</title></head><body>'
                '<a href="https://example.com/fr/">French version</a>'
                + english + "</body></html>")
        d = DomainFR(homepage="https://example.com/", validate_alternatives=False)
        resp = await d.check_page_if_french(html, DetectionMode.COMPLETE)
        assert resp.ok is False
        assert resp.method == "Check_nok_v2"
        assert not resp.alternative_urls


class TestValidateSingleUrlSelfRedirect:
    """Enforcement-point tests: _validate_single_url must actually apply the
    self-redirect rejection (mutation check: deleting the call sites fails these)."""

    def _client_mock(self, final_url):
        response = MagicMock()
        response.status_code = 200
        response.headers = {"content-type": "text/html"}
        response.url = final_url

        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.mark.asyncio
    async def test_candidate_redirecting_to_homepage_fails_validation(self):
        d = DomainFR(homepage="https://metaga.es/")
        client = self._client_mock("https://metaga.es/")
        with patch("app.core.domain_fr.httpx.AsyncClient", return_value=client), \
             patch("app.services.scraper.scrape_html", new=AsyncMock(return_value=None)):
            assert await d._validate_single_url("https://metaga.fr/") is False

    @pytest.mark.asyncio
    async def test_candidate_serving_own_page_passes_validation(self):
        d = DomainFR(homepage="https://metaga.es/")
        client = self._client_mock("https://metaga.fr/")
        with patch("app.core.domain_fr.httpx.AsyncClient", return_value=client):
            assert await d._validate_single_url("https://metaga.fr/") is True

    @pytest.mark.asyncio
    async def test_cookie_switcher_redirect_still_validates(self):
        # /?lang=fr → Set-Cookie + 302 back to / : same host+path, only the
        # query dropped — must NOT be rejected (Case 6 judges the content).
        d = DomainFR(homepage="https://example.com/")
        client = self._client_mock("https://example.com/")
        with patch("app.core.domain_fr.httpx.AsyncClient", return_value=client):
            assert await d._validate_single_url("https://example.com/?lang=fr") is True
