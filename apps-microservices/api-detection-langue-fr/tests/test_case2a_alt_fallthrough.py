"""Cas 2a : un site .fr en anglais qui DÉCLARE une version française validée
doit être accepté via cette alternative, pas rejeté.

Cas réel : sumca.fr (DSPI 90) — page d'accueil réellement anglaise (fastText
en 0.916) mais alternative hreflang validée https://www.sumca.fr/fr/ que le
cas 2a jetait en retournant avant la boucle du cas 6. Voir spec 2026-07-28.
"""
import pytest
from types import SimpleNamespace

from app.core import domain_fr as domain_fr_module
from app.core.domain_fr import DomainFR
from app.models.schemas import AlternativeUrl, DetectionMode

HOMEPAGE = "https://www.sumca.fr/"
ALT_URL = "https://www.sumca.fr/fr/"

# Page d'accueil : anglaise, lang="en-US" (comme le vrai sumca.fr)
HOME_HTML = """<html lang="en-US"><body><p>
Perfect bespoke tooling for demanding industrial applications. Micron
tolerances, superb finishing all ready out of the box to be used on your press.
</p></body></html>"""

# Alternative : française, lang="fr"
ALT_HTML_FR = """<html lang="fr"><body><p>
FRENCH_ALT_MARKER Outillage sur mesure pour les applications industrielles
exigeantes. Tolerances au micron et finition soignee pour votre presse.
</p></body></html>"""

# Alternative qui MENT : déclarée FR mais servant de l'anglais
ALT_HTML_EN = """<html lang="en"><body><p>
Perfect bespoke tooling for demanding industrial applications, delivered
worldwide with micron tolerances and superb finishing.
</p></body></html>"""


def _make_detector(validate_alternatives=True):
    return DomainFR(
        homepage=HOMEPAGE,
        use_nlp_detection=True,
        validate_alternatives=validate_alternatives,
    )


def _stub_nlp(detector, monkeypatch):
    """NLP déterministe : `fr` fort si le marqueur FR est présent, sinon `en` fort.
    0.95 > 0.9 => strongly_contradicts sur la page d'accueil anglaise."""
    def fake_fasttext(text):
        if "FRENCH_ALT_MARKER" in (text or ""):
            return {"lang": "fr", "confidence": 0.95, "method": "stub"}
        return {"lang": "en", "confidence": 0.95, "method": "stub"}

    monkeypatch.setattr(
        detector.language_detector, "detect_from_text_content_fasttext", fake_fasttext
    )
    monkeypatch.setattr(
        detector.language_detector, "detect_from_text_content", fake_fasttext
    )


def _stub_alternatives(detector, monkeypatch, candidates):
    async def fake_detect_alternative_languages(content):
        return candidates
    monkeypatch.setattr(
        detector, "detect_alternative_languages", fake_detect_alternative_languages
    )


def _stub_fetch(monkeypatch, html):
    async def fake_fetch_html(url, proxy=None, *args, **kwargs):
        return SimpleNamespace(html=html, final_url=url, status_code=200,
                               content_type="text/html", headers={})
    monkeypatch.setattr(domain_fr_module, "fetch_html", fake_fetch_html)


def _validated_hreflang_alt():
    # region_priority a un default=1 dans le modèle → non requis ici.
    return AlternativeUrl(
        url=ALT_URL, method="hreflang", reliability="high", validated=True
    )


@pytest.mark.asyncio
async def test_validated_french_alt_is_accepted(monkeypatch):
    """L'alternative validée est réellement française → ok=True sur SON url."""
    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_validated_hreflang_alt()])
    _stub_fetch(monkeypatch, ALT_HTML_FR)

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.url == ALT_URL
    assert "alternative_hreflang" in res.method


@pytest.mark.asyncio
async def test_lying_alt_is_rejected(monkeypatch):
    """L'alternative déclarée FR sert de l'anglais → pas de faux positif."""
    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_validated_hreflang_alt()])
    _stub_fetch(monkeypatch, ALT_HTML_EN)

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False


@pytest.mark.asyncio
async def test_no_validated_alt_keeps_case_2a(monkeypatch):
    """Aucune alternative validée → comportement inchangé (cas 2a)."""
    d = _make_detector()
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "nlp_override_tld_fr"


@pytest.mark.asyncio
async def test_validate_alternatives_off_keeps_case_2a(monkeypatch):
    """validate_alternatives=False (crawler-service) → comportement inchangé."""
    d = _make_detector(validate_alternatives=False)
    _stub_nlp(d, monkeypatch)
    _stub_alternatives(d, monkeypatch, [_validated_hreflang_alt()])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "nlp_override_tld_fr"


@pytest.mark.asyncio
async def test_soft_french_fr_tld_still_accepted(monkeypatch):
    """Non-régression du sous-cas 2b : .fr + NLP soft FR reste ok=True."""
    d = _make_detector()

    def soft_fr(text):
        return {"lang": "fr", "confidence": 0.60, "method": "stub"}  # < 0.75
    monkeypatch.setattr(d.language_detector, "detect_from_text_content_fasttext", soft_fr)
    monkeypatch.setattr(d.language_detector, "detect_from_text_content", soft_fr)
    _stub_alternatives(d, monkeypatch, [])

    res = await d.check_page_if_french(HOME_HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert "nlp_soft_confirmed" in res.method
