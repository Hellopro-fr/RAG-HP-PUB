"""Tests for the validate_alternatives skip-all flag.
Spec: docs/superpowers/specs/2026-06-04-detection-langue-fr-validate-alternatives-flag-design.md
"""
import pytest
from unittest.mock import AsyncMock, patch
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
