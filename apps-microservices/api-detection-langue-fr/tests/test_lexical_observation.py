"""Volet B du chantier faux négatifs : instrumenter le signal lexical au Cas 9.

Cas réel du run 2026-08-10 : 324 automatismes.net — 3500 caractères de français
limpide, mais aucun `html lang`, aucun hreflang, TLD `.net`, et fastText tranche
pour une autre langue avec assurance. Le Cas 8, seul à consulter le signal
lexical, est gardé par `soft_from_fasttext` qui exige que fastText ait dit `fr`
(domain_fr.py:1606-1611) : le signal n'est donc JAMAIS lu. Ce volet ne corrige
rien — il mesure, pour qu'un seuil d'activation soit choisi sur des données
réelles. Voir spec 2026-08-10-detection-faux-negatifs-design.md §2.2 et §5.

Les comptes exacts du §3 de la spec (15, 9, 0, 0, 1, 0) ne sont PAS réassertés
ici : ils ont été mesurés sur des extraits qui n'ont pas été conservés mot pour
mot, et réasserter un nombre contre un autre texte ne prouverait rien. Ce sont
les PROPRIÉTÉS DISCRIMINANTES qui sont testées — français >= 5, autres langues
<= 1 — car c'est d'elles que dépend le choix d'un seuil.

Comptes RÉELLEMENT mesurés sur ces échantillons (2026-08-10, cette machine,
via _count_french_exclusive_distinct) :
  FR_PROSE=8 (avec, chez, dans, notre, nous, pour, votre, vous)
  ES_PROSE=0, IT_PROSE=0, EN_PROSE=0, FR_CATALOGUE=0
  PT_PROSE=1 (mais)
Cette table (pas les 6 chiffres de la spec) est ce qu'une session future doit
lire pour choisir le seuil d'activation.
"""
import pytest

from app.core.config import settings
from app.core.domain_fr import DomainFR
from app.models.schemas import DetectionMode
from app.services.language_detector import LanguageDetector

FR_PROSE = (
    "Nous sommes votre specialiste de la motorisation de portails dans la "
    "region. Notre equipe intervient chez vous pour l'installation et pour "
    "l'entretien de vos automatismes, avec des techniciens qui connaissent "
    "toutes les marques du marche. Vous pouvez nous joindre du lundi au "
    "vendredi, et nous vous repondons dans la journee."
)
ES_PROSE = (
    "Somos su especialista en la motorizacion de puertas en la region. "
    "Nuestro equipo interviene en su casa para la instalacion y para el "
    "mantenimiento de sus automatismos, con tecnicos que conocen todas las "
    "marcas del mercado. Puede llamarnos de lunes a viernes."
)
IT_PROSE = (
    "Siamo il vostro specialista nella motorizzazione dei cancelli nella "
    "regione. La nostra squadra interviene a casa vostra per l'installazione "
    "e per la manutenzione dei vostri automatismi, con tecnici che conoscono "
    "tutte le marche del mercato."
)
PT_PROSE = (
    "Somos o seu especialista na motorizacao de portoes na regiao. A nossa "
    "equipa intervem em casa para a instalacao e para a manutencao dos seus "
    "automatismos, mais os tecnicos que conhecem todas as marcas do mercado. "
    "Pode ligar-nos de segunda a sexta."
)
EN_PROSE = (
    "We are your specialist in gate motorisation in the region. Our team "
    "comes to your home for the installation and the maintenance of your "
    "automatic systems, with technicians who know every brand on the market."
)
# Catalogue sans prose : la limite honnête du volet. Aucun mot fonctionnel.
FR_CATALOGUE = (
    "Portail battant aluminium Portail coulissant acier Motorisation "
    "Somfy Nice Came BFT Digicode Interphone Video Barriere levante"
)


def _counter():
    return LanguageDetector()._count_french_exclusive_distinct


class TestCompteur:
    def test_prose_francaise_au_dessus_du_seuil_dactivation_envisage(self):
        assert _counter()(FR_PROSE) >= 5

    @pytest.mark.parametrize("sample,label", [
        (ES_PROSE, "espagnol"), (IT_PROSE, "italien"), (EN_PROSE, "anglais"),
    ])
    def test_autres_langues_sous_le_seuil(self, sample, label):
        assert _counter()(sample) <= 1, label

    def test_portugais_ne_franchit_pas_le_seuil(self):
        """`mais` est portugais courant ET listé comme exclusivement français :
        c'est pourquoi un seuil à 1 serait faux (spec §3, conclusion 3)."""
        assert _counter()(PT_PROSE) <= 1

    def test_catalogue_sans_prose_ne_marque_rien(self):
        """Limite assumée : ce rattrapage ne sauvera que les pages rédigées."""
        assert _counter()(FR_CATALOGUE) <= 1

    def test_mots_distincts_pas_occurrences(self):
        """`nous` est exclusif (language_detector.py:199) : un mutant qui
        compterait les OCCURRENCES rendrait 12 ici ; le vrai compteur (mots
        DISTINCTS) rend 1. `le`, utilisé dans une version antérieure de ce
        test, est un mot PARTAGÉ (:207-211) — il rend 0 sous les deux
        implémentations et ne garde donc rien."""
        assert _counter()("nous " * 12) == 1

    def test_texte_trop_court_rend_zero(self):
        """5 mots, tous exclusifs (nous vous avec dans pour) : un mutant SANS
        le plancher à 10 mots (:300-301) rendrait 5 (5 distincts) ; le vrai
        compteur, sous le plancher, rend 0. `le la les des`, utilisé dans une
        version antérieure de ce test, sont tous des mots PARTAGÉS — 0 sous
        les deux implémentations, donc aucune garde."""
        assert _counter()("nous vous avec dans pour") == 0


class TestSignalAgregeInchange:
    def test_compute_french_signal_rend_toujours_un_float(self):
        """Le Cas 8 déployé lit cette valeur (domain_fr.py:1619, :1628) :
        ce volet ne doit ni changer sa signature ni changer sa valeur."""
        d = LanguageDetector()
        value = d._compute_french_signal(FR_PROSE)
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0


# --- Diagnostic au Cas 9 ------------------------------------------------------

URL = "http://automatismes.example"
# `.example` (pas de signal URL) + lang="en-US" (pas de signal HTML) : la
# matrice n'a que le NLP, et il se trompe.
HTML = f"""<html lang="en-US"><body><p>{FR_PROSE}</p></body></html>"""


def _stub_nlp(detector, monkeypatch, lang, confidence, exclusive_distinct):
    """Force le verdict NLP ET le contenu de `details`.

    `exclusive_distinct=None` simule un `details` d'AVANT ce chantier (clé
    absente) : c'est la situation des tests préexistants du Cas 9, qui doivent
    continuer à voir `error is None`.
    """
    details = {"fasttext": {"predictions": []}, "french_signal": 0.0}
    if exclusive_distinct is not None:
        details["french_exclusive_distinct"] = exclusive_distinct
    result = {
        "lang": lang, "confidence": confidence,
        "method": "nlp_detection_fasttext", "details": details,
    }
    for name in ("detect_from_text_content_fasttext", "detect_from_text_content"):
        monkeypatch.setattr(
            detector.language_detector, name, lambda text, _r=result: _r
        )


@pytest.mark.asyncio
async def test_diagnostic_ecrit_sans_changer_le_verdict(monkeypatch):
    d = DomainFR(homepage=URL, use_nlp_detection=True)
    _stub_nlp(d, monkeypatch, lang="de", confidence=0.95, exclusive_distinct=9)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is False
    assert res.method == "Check_nok_v2"
    assert "9 mots exclusifs distincts" in (res.error or "")


@pytest.mark.asyncio
async def test_sous_le_seuil_aucun_diagnostic(monkeypatch):
    d = DomainFR(homepage=URL, use_nlp_detection=True)
    _stub_nlp(d, monkeypatch, lang="de", confidence=0.95, exclusive_distinct=2)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.method == "Check_nok_v2"
    assert res.error is None


@pytest.mark.asyncio
async def test_seuil_exact_ecrit_le_diagnostic(monkeypatch):
    """Épingle la frontière : à exactement `LEXICAL_OBSERVATION_MIN_DISTINCT`,
    le diagnostic DOIT être écrit — la comparaison est `>=`, pas `>`. Référence
    le setting plutôt que 3 en dur : suit le défaut s'il bouge."""
    threshold = settings.LEXICAL_OBSERVATION_MIN_DISTINCT
    d = DomainFR(homepage=URL, use_nlp_detection=True)
    _stub_nlp(d, monkeypatch, lang="de", confidence=0.95, exclusive_distinct=threshold)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.error is not None
    assert f"{threshold} mots exclusifs distincts" in res.error


@pytest.mark.asyncio
async def test_seuil_a_zero_desactive_le_diagnostic(monkeypatch):
    monkeypatch.setattr(settings, "LEXICAL_OBSERVATION_MIN_DISTINCT", 0, raising=False)
    d = DomainFR(homepage=URL, use_nlp_detection=True)
    _stub_nlp(d, monkeypatch, lang="de", confidence=0.95, exclusive_distinct=9)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.error is None


@pytest.mark.asyncio
async def test_details_sans_la_cle_reste_muet(monkeypatch):
    """Compatibilité : les stubs des tests préexistants n'ont pas la clé."""
    d = DomainFR(homepage=URL, use_nlp_detection=True)
    _stub_nlp(d, monkeypatch, lang="de", confidence=0.95, exclusive_distinct=None)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.method == "Check_nok_v2"
    assert res.error is None
