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


def _stub_nlp(
    detector, monkeypatch, lang, confidence, french_signal,
    recompute_signal=None, method="nlp_detection_fasttext",
):
    """Force le résultat NLP ET le french_signal exposé dans `details`.
    `lang=None` simule un NLP indisponible.

    `method` fixe le `method` du résultat NLP retourné : `'nlp_detection_fasttext'`
    (défaut, inchangé pour tous les tests préexistants) simule un verdict fastText
    réel ; `'nlp_detection'` simule le verdict de SUBSTITUTION langdetect+langid
    (celui que le cross-check :1257-1272 installe à la place du résultat fastText)
    — nécessaire pour tester que le garde-fou `soft_from_fasttext` refuse ce
    verdict même quand `lang`/`french_signal` sont par ailleurs identiques.

    `recompute_signal` isole le chemin `_compute_french_signal` (recalcul,
    décapage grossier) du chemin `details['french_signal']` (valeur déjà
    calculée par le NLP sur texte consent-strippé) : sans ce paramètre, les
    deux valent la même valeur dans chaque test et aucune assertion ne peut
    distinguer laquelle des deux sources a réellement été lue par le code.
    Les tests d'ACCEPTATION passent une valeur divergente sous le seuil (0.0) :
    ils échoueraient si le code se rabattait sur le recalcul au lieu de lire
    `details`. Les tests de REJET passent une valeur divergente au-dessus du
    seuil (0.9) : même logique, sens inverse — un rejet qui resterait un rejet
    avec `recompute_signal=0.0` ne prouve rien, puisque `details` prend feu
    seulement quand il est absent ; ce n'est un test valide que si une
    régression vers le recalcul romprait l'assertion."""
    result = None
    if lang is not None:
        result = {
            "lang": lang,
            "confidence": confidence,
            "method": method,
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
    # inchangé). Chemin NLP soft : les appelants passent une valeur divergente
    # (voir docstring) pour que leurs tests ne passent QUE si `details` est bien
    # lu en premier.
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
    """Signal lexical <= 0.3 : pas de corroboration, comportement inchangé.
    recompute_signal=0.9 (au-dessus du seuil, sens inverse du test d'acceptation) :
    si le code se rabattait sur le recalcul au lieu de lire `details`, 0.9 > 0.3
    accepterait à tort => ce test ne passe que si `details` est bien lu."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20,
        recompute_signal=0.9,
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
    """Label Case 9 généralisé : vrai pour les 3 causes de rejet possibles
    (pas de corroboration lexicale, verdict substitué, confiance sous le
    plancher) — le texte ne doit plus prétendre que la seule cause est
    `lexical signal <= 0.3`. recompute_signal=0.9 : voir _stub_nlp docstring."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20,
        recompute_signal=0.9,
    )

    dbg = await d.check_page_if_french_debug(HTML, DetectionMode.COMPLETE)

    assert dbg.result.ok is False
    assert "soft French but no corroboration" in dbg.debug.decision
    assert "(no URL/HTML signal, no lexical corroboration)" in dbg.debug.decision


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


@pytest.mark.asyncio
async def test_substituted_verdict_is_refused(monkeypatch):
    """GARDE-FOU 1 (revue finale 2026-07-29) : un verdict `fr` qui vient du
    substitut langdetect+langid (method='nlp_detection') ne doit JAMAIS
    corroborer, même avec un signal lexical très élevé — c'est la forme
    circulaire dénoncée par la revue (une page ES peut atteindre 0.99 de
    signal lexical sans un mot exclusivement français, et le bonus fr*0.3
    de language_detector.py:589-592 peut lui-même avoir élu ce `fr`)."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.537, french_signal=0.99,
        method="nlp_detection",
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_soft_below_confidence_floor_is_refused(monkeypatch):
    """GARDE-FOU 2 : un argmax `fr` fastText à 0.18 ne vaut pas rattrapage,
    même avec un signal lexical très élevé — sans plancher, ce serait
    exactement aussi peu fiable qu'accepté à n'importe quelle confiance."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.18, french_signal=0.9,
        method="nlp_detection_fasttext",
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_soft_at_confidence_floor_is_accepted(monkeypatch):
    """La comparaison est `>=` : exactement NLP_SOFT_MIN_CONFIDENCE (0.5)
    doit être accepté, pas seulement au-dessus."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.5, french_signal=0.577,
        recompute_signal=0.0, method="nlp_detection_fasttext",
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.method == "nlp_soft_confirmed+french_lexical_signal"
    assert res.confidence == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_lexical_signal_just_below_threshold_is_refused(monkeypatch):
    """Épingle la frontière 0.3 : muter `>` en `>=`, ou retoucher le seuil,
    ne doit PAS faire passer ce cas au vert. recompute_signal=0.9 (divergent,
    au-dessus) : ne passe que si `details` (0.30) est bien lu, pas le recalcul."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.30,
        recompute_signal=0.9,
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_lexical_signal_just_above_threshold_is_accepted(monkeypatch):
    """Symétrique du test précédent, juste au-dessus de 0.3.
    recompute_signal=0.0 (divergent, en dessous) : ne passe que si `details`
    (0.31) est bien lu, pas le recalcul."""
    d = _detector()
    _stub_nlp(
        d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.31,
        recompute_signal=0.0,
    )

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.method == "nlp_soft_confirmed+french_lexical_signal"
