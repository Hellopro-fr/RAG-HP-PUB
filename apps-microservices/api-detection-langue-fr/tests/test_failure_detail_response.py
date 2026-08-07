from app.models.schemas import DetectionResponse


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
