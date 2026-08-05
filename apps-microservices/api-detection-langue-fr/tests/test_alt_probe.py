"""Case-6 alternative confirmation uses ONE probe, not the retry cascade.

Why this matters (2026-08-05): the loop wrapped `fetch_html` — the whole
3-attempt cascade, ~85s per attempt — in `asyncio.wait_for(..., timeout=120)`.
A belt shorter than what it wraps cannot outlast it, so the cancellation was
the NORMAL outcome for any alternative that missed on attempt 1. Cancelling
mid-`page.goto` leaves Playwright's protocol callback pending-and-uncancelled;
`Connection.cleanup()` then sets an exception on it that nobody can read —
the `Future exception was never retrieved` flood on deep /fr/ URLs.
"""
from types import SimpleNamespace

import pytest

from app.core import domain_fr as domain_fr_module
from app.core.domain_fr import DomainFR
from app.models.schemas import AlternativeUrl, DetectionMode

HOMEPAGE = "https://www.sumca.fr/"
ALT_URL = "https://www.sumca.fr/fr/"
ALT_URL_2 = "https://www.sumca.fr/fr-fr/"

HOME_HTML = """<html lang="en-US"><body><p>
Perfect bespoke tooling for demanding industrial applications. Micron
tolerances, superb finishing all ready out of the box to be used on your press.
</p></body></html>"""

ALT_HTML_FR = """<html lang="fr"><body><p>
FRENCH_ALT_MARKER Outillage sur mesure pour les applications industrielles
exigeantes. Tolerances au micron et finition soignee pour votre presse.
</p></body></html>"""


def _make_detector():
    return DomainFR(homepage=HOMEPAGE, use_nlp_detection=True,
                    validate_alternatives=True)


def _stub_nlp(detector, monkeypatch):
    """`fr` strong when the FR marker is present, else `en` strong (0.95 > 0.9
    => strongly_contradicts on the English homepage, which reaches Case 6)."""
    def fake_fasttext(text):
        if "FRENCH_ALT_MARKER" in (text or ""):
            return {"lang": "fr", "confidence": 0.95, "method": "stub"}
        return {"lang": "en", "confidence": 0.95, "method": "stub"}

    monkeypatch.setattr(detector.language_detector,
                        "detect_from_text_content_fasttext", fake_fasttext)
    monkeypatch.setattr(detector.language_detector,
                        "detect_from_text_content", fake_fasttext)


def _stub_alternatives(detector, monkeypatch, candidates):
    async def fake_detect_alternative_languages(content):
        return candidates
    monkeypatch.setattr(detector, "detect_alternative_languages",
                        fake_detect_alternative_languages)


def _alt(url=ALT_URL):
    return AlternativeUrl(url=url, method="hreflang", reliability="high",
                          validated=True)


def _result(url, html):
    return SimpleNamespace(html=html, final_url=url, status_code=200,
                           content_type="text/html", headers={})


@pytest.mark.asyncio
async def test_alternative_confirmed_with_single_scrape(monkeypatch):
    scrape_calls = []

    async def fake_scrape(url, timeout=90, proxy=None):
        scrape_calls.append(url)
        return _result(url, ALT_HTML_FR)

    async def fake_fetch(url, proxy=None, *a, **kw):
        raise AssertionError("Case 6 must not use the fetch_html cascade")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.url == ALT_URL
    assert scrape_calls == [ALT_URL], f"expected one probe, got {scrape_calls}"


@pytest.mark.asyncio
async def test_probe_returning_none_probes_every_candidate(monkeypatch):
    scrape_calls = []

    async def fake_scrape(url, timeout=90, proxy=None):
        scrape_calls.append(url)
        return None          # what scrape_html returns on a bad/missing proxy

    async def fake_fetch(url, proxy=None, *a, **kw):
        raise AssertionError("Case 6 must not use the fetch_html cascade")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt(ALT_URL), _alt(ALT_URL_2)])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert scrape_calls == [ALT_URL, ALT_URL_2], (
        f"loop must continue past a None result: {scrape_calls}"
    )


@pytest.mark.asyncio
async def test_probe_raising_does_not_propagate(monkeypatch):
    async def fake_scrape(url, timeout=90, proxy=None):
        raise RuntimeError("Timeout 30000ms exceeded.")

    async def fake_fetch(url, proxy=None, *a, **kw):
        raise AssertionError("Case 6 must not use the fetch_html cascade")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch)

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False          # returns a verdict, does not raise


@pytest.mark.asyncio
async def test_probe_gets_the_full_proxy_url(monkeypatch):
    """settings.APIFY_PROXY is already a full URL after config.py:57-64 —
    the probe passes it straight through, like domain_fr.py:414/:484 do."""
    seen = {}

    async def fake_scrape(url, timeout=90, proxy=None):
        seen["proxy"] = proxy
        return None

    async def fake_fetch(url, proxy=None, *a, **kw):
        raise AssertionError("Case 6 must not use the fetch_html cascade")

    monkeypatch.setattr(domain_fr_module, "scrape_html", fake_scrape)
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch)
    monkeypatch.setattr(domain_fr_module.settings, "APIFY_PROXY",
                        "http://auto:pw@proxy.apify.com:8000")

    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_alt()])

    await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert seen["proxy"] == "http://auto:pw@proxy.apify.com:8000"
