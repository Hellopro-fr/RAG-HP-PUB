import asyncio

import pytest
from app.services import scraper
from app.services import redirect_tracker


async def _no_sleep(*_a, **_k):
    """No-op replacement for asyncio.sleep in fetch_html's retry backoff.
    NEVER delegate to asyncio.sleep here: redirect_tracker.asyncio IS the
    global asyncio module, so patching its `sleep` attribute and then calling
    asyncio.sleep(...) from inside the stub recurses into the stub itself."""
    return None


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


def _fake_scrape(sequence):
    """Renvoie un faux scrape_html qui joue `sequence` : chaque élément est
    soit une exception à lever, soit un dict à écrire dans le sink (puis None),
    soit un objet à retourner."""
    calls = {'n': 0}

    async def _inner(url, proxy=None, error_sink=None):
        i = calls['n']
        calls['n'] += 1
        step = sequence[min(i, len(sequence) - 1)]
        if isinstance(step, Exception):
            raise step
        if isinstance(step, dict):
            if error_sink is not None:
                error_sink.update(step)
            return None
        return step

    return _inner, calls


@pytest.mark.asyncio
async def test_fetch_html_publishes_phase1_cause(monkeypatch):
    fake, _ = _fake_scrape([{'cause': 'NS_ERROR_EXAMPLE', 'stage': 'navigation'}])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', lambda u: [])
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', _no_sleep)
    sink = {}
    assert await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink=sink) is None
    assert sink['cause'] == 'NS_ERROR_EXAMPLE'
    assert sink['stage'] == 'navigation'


@pytest.mark.asyncio
async def test_fetch_html_publishes_phase2_cause(monkeypatch):
    """Le trou actuel : la boucle variantes n'alimentait rien.

    Phase 1 doit échouer d'une façon NON 'pointless' (ni 'Timeout' ni
    'Contenu vide ou trop court', cf. _VARIANT_POINTLESS_ERRORS) pour que le
    garde variant_pointless (inchangé, piloté par last_error) laisse
    effectivement passer la Phase 2 — sinon les variantes ne sont jamais
    essayées et le test ne prouverait rien sur la boucle Phase 2 elle-même.
    """
    fake, _ = _fake_scrape([
        RuntimeError('NS_ERROR_TEMPORARY'),   # 3 tentatives Phase 1, réparables
        RuntimeError('NS_ERROR_TEMPORARY'),
        RuntimeError('NS_ERROR_TEMPORARY'),
        {'cause': 'PHASE2_CAUSE', 'stage': 'navigation'},   # variante
    ])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', lambda u: ['http://x.test'])
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', _no_sleep)
    sink = {}
    await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink=sink)
    assert sink['cause'] == 'PHASE2_CAUSE'


@pytest.mark.asyncio
async def test_fetch_html_uses_browser_stage_when_sink_empty(monkeypatch):
    """Exception hors des 4 points instrumentes -> stage deduit de l'absence d'ecriture."""
    fake, _ = _fake_scrape([RuntimeError('new_context exploded')])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', lambda u: [])
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', _no_sleep)
    sink = {}
    await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink=sink)
    assert sink['stage'] == 'browser'
    assert 'new_context exploded' in sink['cause']


@pytest.mark.asyncio
async def test_variant_gate_decision_unchanged(monkeypatch, caplog):
    """NON-REGRESSION : une cause reelle dans le sink ne doit pas reactiver les variantes
    d'un echec 'pointless' (last_error inchange)."""
    fake, calls = _fake_scrape([{'cause': 'NS_ERROR_EXAMPLE', 'stage': 'content'}])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', _no_sleep)
    variants_called = {'n': 0}

    def _variants(u):
        variants_called['n'] += 1
        return ['http://x.test']

    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', _variants)
    await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink={})
    # 'Contenu vide ou trop court' est pointless -> variantes sautees -> 3 appels, pas 4
    assert calls['n'] == 3
    assert variants_called['n'] == 0
