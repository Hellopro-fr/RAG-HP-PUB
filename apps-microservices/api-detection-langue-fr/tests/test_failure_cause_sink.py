import pytest
from app.services import scraper


def test_record_failure_noop_without_sink():
    scraper._record_failure(None, 'navigation', 'boom')  # ne doit pas lever


def test_record_failure_keeps_first_line_and_truncates():
    sink = {}
    scraper._record_failure(sink, 'navigation', 'ligne1\nligne2\nligne3')
    assert sink == {'cause': 'ligne1', 'stage': 'navigation'}

    sink2 = {}
    scraper._record_failure(sink2, 'navigation', 'x' * 500)
    assert len(sink2['cause']) == scraper.FAILURE_CAUSE_MAX_LEN


def test_record_failure_first_writer_wins():
    """Une erreur de navigation ne doit pas être écrasée par le 'contenu court' qui en découle."""
    sink = {}
    scraper._record_failure(sink, 'navigation', 'NS_ERROR_WHATEVER')
    scraper._record_failure(sink, 'content', 'Contenu trop court')
    assert sink == {'cause': 'NS_ERROR_WHATEVER', 'stage': 'navigation'}


def test_record_failure_tolerates_empty_cause():
    sink = {}
    scraper._record_failure(sink, 'runtime', '')
    assert sink == {'cause': '', 'stage': 'runtime'}


@pytest.mark.asyncio
async def test_scrape_html_records_proxy_stage_without_leaking_secret(monkeypatch):
    # _parse_proxy fait un urlparse() nu sans validation de format : la valeur
    # ci-dessous lui serait en fait acceptée (elle ne rejette rien), donc on la
    # patche pour forcer deterministiquement la branche 'proxy invalide'
    # (scraper.py ~:397-400) sans dependre de Playwright ni du reseau.
    monkeypatch.setattr(scraper, '_parse_proxy', lambda proxy: None)
    sink = {}
    result = await scraper.scrape_html(
        'https://example.com',
        proxy='http://auto:SUPERSECRET@proxy.apify.com:8000/broken',
        error_sink=sink,
    )
    assert result is None
    assert sink['stage'] == 'proxy'
    assert sink['cause'] == 'Proxy invalide (format non reconnu)'
    assert 'SUPERSECRET' not in sink['cause']
    assert 'proxy.apify.com' not in sink['cause']


@pytest.mark.asyncio
async def test_scrape_html_records_when_proxy_missing():
    sink = {}
    assert await scraper.scrape_html('https://example.com', proxy=None, error_sink=sink) is None
    assert sink['stage'] == 'proxy'
    assert 'SUPERSECRET' not in sink['cause']


@pytest.mark.asyncio
async def test_scrape_html_without_sink_is_unchanged():
    assert await scraper.scrape_html('https://example.com', proxy=None) is None
