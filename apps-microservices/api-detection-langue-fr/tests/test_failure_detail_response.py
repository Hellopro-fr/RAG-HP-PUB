import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.schemas import DetectionResponse
from main import app


@pytest.fixture
def client():
    return TestClient(app)


async def _fetch_html_stub_with_cause(url, proxy_url, error_sink=None):
    """Mime un echec de fetch qui a bien capture une cause dans le sink recu."""
    if error_sink is not None:
        error_sink['cause'] = 'NS_ERROR_WHATEVER'
        error_sink['stage'] = 'navigation'
    return None


async def _fetch_html_stub_no_cause(url, proxy_url, error_sink=None):
    """Mime un echec de fetch qui n'a capture aucune cause (sink recu, laisse vide)."""
    return None


def test_detect_fetch_failed_surfaces_failure_detail(client):
    """Verrouille le cablage bout-en-bout (/api/v1/detect) : le sink que
    _fetch_with_admission transmet a fetch_html est bien celui que
    _format_failure_detail relit pour peupler la reponse JSON. Un edit futur
    qui deplace la declaration de fetch_sink ou echange le dict passe casserait
    ce test sans toucher a test_format_helper (qui teste le helper isole)."""
    with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
         patch("app.api.routes.fetch_html", _fetch_html_stub_with_cause):
        r = client.post("/api/v1/detect", json={"url": "https://x-failure-detail.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "fetch_failed"
    assert body["failure_detail"] == "navigation: NS_ERROR_WHATEVER"


def test_detect_fetch_failed_without_cause_is_none(client):
    """Sink reste vide (aucune cause capturee cote moteur) -> failure_detail
    None dans la reponse, jamais une chaine vide ou 'unknown: '."""
    with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
         patch("app.api.routes.fetch_html", _fetch_html_stub_no_cause):
        r = client.post("/api/v1/detect", json={"url": "https://x-failure-detail-empty.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "fetch_failed"
    assert body["failure_detail"] is None


def test_detect_debug_fetch_failed_surfaces_failure_detail(client):
    """Meme verrou que ci-dessus, sur le miroir /api/v1/detect-debug (sink
    distinct, mais meme helper _format_failure_detail et meme monkeypatch
    target fetch_html)."""
    with patch("app.api.routes.fetch_html", _fetch_html_stub_with_cause):
        r = client.post("/api/v1/detect-debug", json={"url": "https://x-failure-detail-debug.test"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["method"] == "fetch_failed"
    assert body["result"]["failure_detail"] == "navigation: NS_ERROR_WHATEVER"


def test_failure_detail_defaults_to_none():
    r = DetectionResponse(ok=False, url='https://x.test', method='fetch_failed')
    assert r.failure_detail is None


def test_failure_detail_roundtrips():
    r = DetectionResponse(
        ok=False, url='https://x.test', method='fetch_failed',
        failure_detail='navigation: NS_ERROR_EXAMPLE',
    )
    assert r.model_dump()['failure_detail'] == 'navigation: NS_ERROR_EXAMPLE'


def test_cached_payload_without_the_key_still_builds():
    """Une entree de cache anterieure au deploiement n'a pas la cle."""
    cached = {'ok': False, 'url': 'https://x.test', 'method': 'fetch_empty_content'}
    assert DetectionResponse(**cached).failure_detail is None


def test_unknown_keys_still_tolerated():
    """Le code prod fait DetectionResponse(**cached) avec des cles en plus (requested_url)."""
    cached = {'ok': False, 'url': 'https://x.test', 'method': 'fetch_failed', 'requested_url': 'y'}
    assert DetectionResponse(**cached).method == 'fetch_failed'


def test_format_helper():
    from app.api.routes import _format_failure_detail
    assert _format_failure_detail({}) is None
    assert _format_failure_detail({'cause': 'C', 'stage': 'navigation'}) == 'navigation: C'
    assert _format_failure_detail({'cause': 'C'}) == 'unknown: C'
