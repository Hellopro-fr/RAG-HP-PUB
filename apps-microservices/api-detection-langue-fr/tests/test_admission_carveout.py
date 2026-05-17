"""Integration tests for the crawler admission carve-out.

Scenarios 1-4 verify route-level admission behavior under saturation:
  1. html_content provided -> bypasses admission, never 503
  2. No html_content + saturated -> HTTP 503 with Retry-After header
  3. Batch mixed items (some with html, some without) under saturation
  4. Cache HIT bypasses admission (no fetch needed)
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app, _prod_admission
from app.api.routes import _detect_single_url
from app.services.scraper import ScrapeResult


@pytest.fixture(autouse=True)
def reset_admission_counter():
    """Each test starts with a fresh admission counter."""
    _prod_admission._counter = 0
    yield
    _prod_admission._counter = 0


@pytest.fixture
def saturate_pool(monkeypatch):
    """Force the prod admission controller to refuse all acquires."""
    async def _refuse():
        return False
    monkeypatch.setattr(_prod_admission, "acquire", _refuse)


@pytest.mark.asyncio
async def test_detect_html_provided_bypasses_admission(saturate_pool):
    """With html_content, the route never reaches _fetch_with_admission.
    Acquire is monkey-patched to refuse everything, but the request must
    still complete with a normal DetectionResponse."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={
                "url": "https://example.fr",
                "html_content": "<html lang='fr'><body>Bonjour</body></html>",
                "mode": "simple",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] != "admission_rejected"


@pytest.mark.asyncio
async def test_detect_no_html_503_when_saturated(saturate_pool):
    """Without html_content, saturated pool -> HTTP 503 + Retry-After header."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://example.fr", "mode": "simple"},
        )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_batch_mixed_items_under_saturation(saturate_pool):
    """Items with html_content succeed; items without -> method=admission_rejected.
    No whole-batch 503."""
    items = [
        {"url": "https://a.fr", "html_content": "<html lang='fr'></html>"},
        {"url": "https://b.fr"},
        {"url": "https://c.fr", "html_content": "<html lang='fr'></html>"},
        {"url": "https://d.fr"},
    ]
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect-batch",
            json={"items": items, "mode": "simple", "max_concurrency": 2},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    methods = [r["method"] for r in body["results"]]
    assert methods.count("admission_rejected") == 2
    # items 0 and 2 (with html_content) must NOT be admission_rejected
    assert body["results"][0]["method"] != "admission_rejected"
    assert body["results"][2]["method"] != "admission_rejected"


@pytest.mark.asyncio
async def test_cache_hit_bypasses_admission(saturate_pool, monkeypatch):
    """Cache HIT path does not call _fetch_with_admission. Returns cached
    response even though admission is saturated."""
    from app.core.domain_fr import domain_cache

    cached_payload = {
        "ok": True,
        "url": "https://cached.fr",
        "method": "langHtml",
        "requested_url": "https://cached.fr",
    }

    async def fake_get(url):
        return cached_payload

    monkeypatch.setattr(domain_cache, "get", fake_get)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://cached.fr", "mode": "simple"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["method"] == "langHtml"
