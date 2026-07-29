"""Cas 8 élargi : un NLP `fr` sous le seuil, corroboré par le signal lexical,
doit être accepté quand aucun indicateur URL/HTML ne peut le confirmer.

Cas réel : amt-lavage.com (DSPI 5582) — contenu manifestement français
("Notre site internet est actuellement en travaux", adresse et téléphone
français), mais `.com` (pas de signal URL), `lang="en-US"` (défaut WordPress
erroné, donc pas de signal HTML) et fastText à `fr` 0.723 < 0.75. Le signal
lexical valait 0.577. Verdict avant correctif : Case 9. Voir spec 2026-07-28.
"""
import pytest

from app.core.domain_fr import DomainFR
from app.models.schemas import DetectionMode

URL = "http://amt-lavage.com"

# `.com` + lang="en-US" erroné => ni signal URL ni signal HTML.
HTML = """<html lang="en-US"><body><p>
Notre site internet est actuellement en travaux. Expert des systemes de lavage
auto et laveries automatiques. Nous vous accompagnons dans tous vos projets
avec une equipe de techniciens experimentes sur toutes les marques.
Siege social 385 rue Francois Rabelais 30290 Laudun L Ardoise.
</p></body></html>"""


def _detector():
    return DomainFR(homepage=URL, use_nlp_detection=True)


def _stub_nlp(detector, monkeypatch, lang, confidence, french_signal, recompute_signal=None):
    """Force le résultat NLP ET le french_signal exposé dans `details`.
    `lang=None` simule un NLP indisponible.

    `recompute_signal` isole le chemin `_compute_french_signal` (recalcul,
    décapage grossier) du chemin `details['french_signal']` (valeur déjà
    calculée par le NLP sur texte consent-strippé) : sans ce paramètre, les
    deux valent la même valeur dans chaque test et aucune assertion ne peut
    distinguer laquelle des deux sources a réellement été lue par le code."""
    result = None
    if lang is not None:
        result = {
            "lang": lang,
            "confidence": confidence,
            "method": "nlp_detection_fasttext",
            "details": {"fasttext": {"predictions": []}, "french_signal": french_signal},
        }

    def fake_fasttext(text):
        return result

    def fake_secondary(text):
        return result

    monkeypatch.setattr(
        detector.language_detector, "detect_from_text_content_fasttext", fake_fasttext
    )
    monkeypatch.setattr(
        detector.language_detector, "detect_from_text_content", fake_secondary
    )
    # Chemin NLP indisponible : le recalcul lexical doit trouver la valeur voulue
    # (recompute_signal par défaut = None => renvoie french_signal, comportement
    # inchangé). Chemin NLP soft : les appelants passent recompute_signal=0.0
    # pour que leurs tests ne passent QUE si `details` est bien lu en premier.
    monkeypatch.setattr(
        detector.language_detector,
        "_compute_french_signal",
        lambda text: (french_signal if recompute_signal is None else recompute_signal),
    )


@pytest.mark.asyncio
async def test_soft_french_corroborated_is_accepted(monkeypatch):
    """amt-lavage : fr 0.723 + signal 0.577 => accepté via le cas 8 élargi.
    recompute_signal=0.0 : si le code recalculait au lieu de lire `details`,
    0.0 <= 0.3 rejetterait => ce test ne passe que si `details` est bien lu."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.577,
        recompute_signal=0.0,
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.method == "nlp_soft_confirmed+french_lexical_signal"
    assert res.confidence == pytest.approx(0.723)


@pytest.mark.asyncio
async def test_soft_french_below_floor_still_rejected(monkeypatch):
    """Signal lexical <= 0.3 : pas de corroboration, comportement inchangé."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20,
        recompute_signal=0.0,
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_contradicting_nlp_is_never_overridden(monkeypatch):
    """GARDE-FOU de sûreté : un NLP qui contredit n'entre JAMAIS dans le cas 8,
    même avec un signal lexical très élevé. Les mots partagés (de/la/que/un)
    recouvrent l'espagnol et l'italien : sans ce garde-fou, un site ES/IT
    pourrait être faussement détecté français."""
    d = _detector()
    _stub_nlp(d, monkeypatch, lang="en", confidence=0.95, french_signal=0.9)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    # Pin the path: rejection must come from Case 8 declining (guard holds),
    # not from some unrelated earlier case coincidentally also saying no.
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_nlp_unavailable_path_unchanged(monkeypatch):
    """Chemin préexistant (NLP indisponible) : method et confiance inchangés."""
    d = _detector()
    _stub_nlp(d, monkeypatch, lang=None, confidence=0.0, french_signal=0.577)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.method == "french_lexical_signal"
    assert res.confidence == pytest.approx(0.577, abs=0.001)


@pytest.mark.asyncio
async def test_decision_label_soft_corroborated(monkeypatch):
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.577,
        recompute_signal=0.0,
    )

    dbg = await d.check_page_if_french_debug(HTML, DetectionMode.COMPLETE)

    assert dbg.result.ok is True
    assert dbg.debug.decision.startswith("Case 8b:")


@pytest.mark.asyncio
async def test_decision_label_soft_uncorroborated(monkeypatch):
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20,
        recompute_signal=0.0,
    )

    dbg = await d.check_page_if_french_debug(HTML, DetectionMode.COMPLETE)

    assert dbg.result.ok is False
    assert "soft French but no corroboration" in dbg.debug.decision


@pytest.mark.asyncio
async def test_decision_label_nlp_unavailable(monkeypatch):
    d = _detector()
    _stub_nlp(d, monkeypatch, lang=None, confidence=0.0, french_signal=0.577)

    dbg = await d.check_page_if_french_debug(HTML, DetectionMode.COMPLETE)

    assert dbg.result.ok is True
    assert dbg.debug.decision.startswith("Case 8:")


@pytest.mark.asyncio
async def test_short_text_no_rescue_when_nlp_unavailable(monkeypatch):
    """AC : `len(visible_text) >= 50` doit empêcher toute tentative de secours
    sur un texte trop court, même NLP indisponible (chemin recalcul)."""
    d = _detector()
    short_html = "<html><body><p>Trop court ici</p></body></html>"
    _stub_nlp(d, monkeypatch, lang=None, confidence=0.0, french_signal=0.9)

    res = await d.check_page_if_french(short_html, DetectionMode.COMPLETE)

    assert res.ok is False
