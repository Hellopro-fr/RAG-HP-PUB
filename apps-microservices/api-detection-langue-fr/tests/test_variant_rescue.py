"""Volet A du chantier faux négatifs : un fetch RÉUSSI mais inexploitable
verrouille la forme d'URL testée, parce que la Phase 2 de fetch_html ne permute
http/https et www/apex que si la Phase 1 ÉCHOUE.

Cas réels du run 2026-08-10 : 2493 groupe-denis.com (le service a testé https,
or `http://` redirige vers ibyd.fr qui est français) et 346 sfte-shop.fr (https
a rendu 22 caractères visibles, or `http://www.` redirige vers sftefrance.fr).
Voir spec 2026-08-10-detection-faux-negatifs-design.md §2.1.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.api.routes import _detect_single_url
from app.core.config import settings
from app.core.domain_fr import DomainFR
from app.services.language_detector import LanguageDetector
from app.services.scraper import ScrapeResult

URL = "https://sfte-shop.example/"

# Page anglaise sur un domaine sans signal FR : la matrice tombe au Cas 9.
HTML_EN = """<html lang="en"><body><p>
We are a specialist supplier of industrial cleaning systems for professional
laundries. Our team of experienced technicians supports every project from the
first drawing to the final commissioning of the machines on site.
</p></body></html>"""

# Signal français maximal : lang="fr" + og:locale + prose française nette.
HTML_FR = """<html lang="fr"><head><meta property="og:locale" content="fr_FR"></head>
<body><p>
Nous sommes votre specialiste de la motorisation de portails et de la fermeture
automatique. Notre equipe de techniciens experimentes vous accompagne dans tous
vos projets, depuis le premier releve sur place jusqu'a la mise en service des
installations. Nous intervenons aussi pour le depannage et l'entretien.
</p></body></html>"""

# Cloudflare Turnstile réel (ancre chl_page/v1 + confirmation `<title>un
# instant`, cf. language_detector.py:54-63) — ET lang="fr" + prose française
# nette : si le garde challenge de _variant_rescue disparaissait, ce contenu
# se ferait accepter comme rattrapage FR à tort. Une page challenge purement
# anglaise (l'ancien fixture) passait le test même sans le garde, puisque son
# contenu échouait déjà la détection FR pour une autre raison — ce fixture ne
# passe QUE grâce au garde.
HTML_CHALLENGE = """<html lang="fr"><head><title>Un instant...</title></head>
<body>
<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1?ray=abc123"></script>
<div id="cf-wrapper">
Nous verifions que vous n'etes pas un robot avant de vous laisser continuer
vers notre catalogue de produits industriels. Merci de patienter quelques
instants : cette verification protege nos clients contre les robots
malveillants et les tentatives d'acces frauduleuses a notre site.
</div>
</body></html>"""


def _scrape(html, final_url=URL, status_code=200):
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


@pytest.fixture(autouse=True)
def _rescue_on(monkeypatch):
    """Budget généreux par défaut ; chaque test le resserre s'il le veut."""
    monkeypatch.setattr(settings, "VARIANT_RESCUE_BUDGET_S", 120)


async def _detect(primary, probe, url=URL, html_content=None, cache_set=None,
                   forced_method=None):
    """Lance _detect_single_url avec le fetch primaire et les sondes stubés.

    `force_refresh=True` court-circuite la lecture de cache ET le dedup
    inflight (routes.py:200 `if _INFLIGHT_DEDUP_ENABLED and not force_refresh`),
    donc aucun état partagé entre tests.
    """
    cache_set = cache_set or AsyncMock()
    with patch("app.api.routes._fetch_with_admission", primary), \
         patch("app.api.routes.scrape_html", probe), \
         patch("app.api.routes.domain_cache.set", cache_set):
        return await _detect_single_url(
            url=url, html_content=html_content, force_refresh=True,
            forced_method=forced_method,
        )


@pytest.mark.asyncio
async def test_variante_francaise_rattrape(monkeypatch):
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR, final_url="http://www.sfte-shop.example/"))

    res = await _detect(primary, probe)

    assert res.ok is True
    # Le numéro de cas dépend du stack NLP présent dans le venv (fastText absent
    # en local, présent dans l'image) : on assert le suffixe, pas le cas.
    assert res.method.endswith("+variant_rescue")
    assert res.analyzed_url == "http://www.sfte-shop.example/"


@pytest.mark.asyncio
async def test_premiere_variante_gagnante_arrete_la_boucle():
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR, final_url="http://x.example/"))

    await _detect(primary, probe)

    assert probe.call_count == 1


@pytest.mark.asyncio
async def test_une_sonde_par_variante_jamais_la_cascade():
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_EN))

    res = await _detect(primary, probe)

    # _generate_url_variants rend 3 variantes ; une sonde chacune, pas 3 x
    # HTTP_MAX_RETRIES comme le ferait fetch_html.
    assert probe.call_count == 3
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_kill_switch_budget_zero(monkeypatch):
    monkeypatch.setattr(settings, "VARIANT_RESCUE_BUDGET_S", 0, raising=False)
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    res = await _detect(primary, probe)

    assert probe.call_count == 0
    assert res.method == "Check_nok_v2"


@pytest.mark.asyncio
async def test_budget_depasse_rend_le_verdict_dorigine(monkeypatch):
    """Invariant central : un rattrapage ne dégrade JAMAIS un verdict.
    Sans ce garde, une sonde lente pousserait l'item vers le wait_for de 300s
    et transformerait un Check_nok_v2 en error — pire que le défaut corrigé.

    Budget=81 : la 1re variante voit remaining≈81s (>= _MIN_PROBE_S=80) → la
    sonde est lancée. Elle répond (EN, donc pas de rattrapage) après 1.2s
    réelles — pas de TimeoutError, `remaining` (81) couvrait large le sleep.
    Avant la 2e variante, remaining≈81-1.2≈79.8s (< _MIN_PROBE_S) → la boucle
    s'arrête sur budget_exhausted SANS sonder la 2e/3e variante : une seule
    sonde au total, pas trois."""
    monkeypatch.setattr(settings, "VARIANT_RESCUE_BUDGET_S", 81, raising=False)
    primary = AsyncMock(return_value=_scrape(HTML_EN))

    async def slow_probe(*a, **kw):
        await asyncio.sleep(1.2)
        return _scrape(HTML_EN)

    probe = AsyncMock(side_effect=slow_probe)
    res = await _detect(primary, probe)

    assert probe.call_count == 1
    assert res.ok is False
    assert res.method == "Check_nok_v2"
    assert res.error is None or "imeout" not in (res.error or "")


@pytest.mark.asyncio
async def test_verdict_hors_perimetre_ne_sonde_pas():
    """http_error (404) est une propriété de la page, pas de la forme d'URL.

    Ce cas revient de la branche [3] invalid-page, bien AVANT le bloc [4bis] —
    il ne prouve donc rien sur le filtre `in _VARIANT_RESCUE_METHODS` lui-même
    (voir test_verdict_forced_hors_perimetre_atteint_le_point_de_decision
    ci-dessous pour un verdict qui, lui, atteint ce filtre)."""
    primary = AsyncMock(return_value=_scrape("<html><body>Not Found</body></html>",
                                             status_code=404))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    await _detect(primary, probe)

    assert probe.call_count == 0


@pytest.mark.asyncio
async def test_verdict_forced_hors_perimetre_atteint_le_point_de_decision():
    """Contrepartie du test ci-dessus : celui-là (le test ci-dessus) prouve le
    retour précoce (avant le bloc [4bis]) ; celui-ci prouve que le filtre
    `result.method in _VARIANT_RESCUE_METHODS` du bloc [4bis] est bien
    ÉVALUÉ mais rend faux pour un verdict hors périmètre.

    forced_method="langHtml" sur HTML_EN (`<html lang="en">`) : le tag HTML ne
    confirme pas le forced_method en français (domain_fr.py:1179, value="en"
    != "fr") → tombe dans l'else déterministe (domain_fr.py:1242-1246) →
    method='Check_nok_forced', qui n'est PAS dans _VARIANT_RESCUE_METHODS
    (seuls Check_nok_v2 et fetch_empty_content y figurent) — purement
    regex-based, aucune dépendance au stack NLP local."""
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    res = await _detect(primary, probe, forced_method="langHtml")

    assert res.method == "Check_nok_forced"
    assert probe.call_count == 0


@pytest.mark.asyncio
async def test_html_fourni_ne_sonde_jamais():
    """crawler-service passe html_content : aucun fetch ne lui est dû."""
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    res = await _detect(primary, probe, html_content=HTML_EN)

    assert probe.call_count == 0
    assert primary.call_count == 0
    assert res.ok is False


@pytest.mark.asyncio
async def test_variante_challenge_ignoree():
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_CHALLENGE))

    res = await _detect(primary, probe)

    assert res.method == "Check_nok_v2"
    assert probe.call_count == 3


@pytest.mark.asyncio
async def test_le_resultat_rattrape_part_au_cache():
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR, final_url="http://x.example/"))
    cache_set = AsyncMock()

    await _detect(primary, probe, cache_set=cache_set)

    assert cache_set.await_count == 1
    payload = cache_set.await_args.args[2]
    assert payload["method"].endswith("+variant_rescue")
    # 2e argument = l'URL analysée qui a semé l'entrée, comme au repli homepage
    # (routes.py:339).
    assert cache_set.await_args.args[1] == "http://x.example/"


@pytest.mark.asyncio
async def test_variante_http_error_ne_rattrape_pas():
    """Une sonde qui répond par un statut HTTP 4xx/5xx ne doit JAMAIS être
    acceptée comme rattrapage, même si son corps est un français limpide —
    sans ce garde, une variante servant un 404 français ouvrirait une porte
    que le chemin primaire ferme : un faux POSITIF, la mauvaise direction pour
    un chantier qui corrige des faux négatifs. Couvre le garde ajouté au
    Round 1 (task-1-report, Finding 3), qui n'avait encore aucun test dédié —
    seul `test_variante_challenge_ignoree` protégeait une AUTRE page rejetée
    (challenge), pas ce statut HTTP."""
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR, status_code=404))

    res = await _detect(primary, probe)

    assert res.method == "Check_nok_v2"
    assert probe.call_count == 3


@pytest.mark.asyncio
async def test_exception_pendant_lanalyse_dune_variante_ne_degrade_pas():
    """Le `except Exception` de _variant_rescue couvre TOUTE l'analyse d'une
    variante (fetch + validation + DomainFR/NLP), pas seulement le fetch —
    c'est ce qui empêche une exception BeautifulSoup/NLP sur du HTML tiers
    arbitraire de remonter jusqu'au handler batch générique, qui
    transformerait le Check_nok_v2 d'origine en method='error' : une
    dégradation strictement pire que le faux négatif que le rattrapage
    corrige. Couvre le fix du Finding 1 (task-1-report, round 1), dont la
    seule vérification à ce jour était un script jetable non committé."""
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    real_check = DomainFR.check_page_if_french

    async def _raise_on_variant(self, content, mode):
        # Seule l'analyse de la SONDE (contenu HTML_FR) doit exploser ; le
        # chemin primaire (contenu HTML_EN) garde son comportement RÉEL, pour
        # produire un verdict d'origine authentique à protéger — pas un stub.
        if content == HTML_FR:
            raise RuntimeError("échec NLP simulé sur la sonde")
        return await real_check(self, content, mode)

    with patch.object(DomainFR, "check_page_if_french", _raise_on_variant):
        res = await _detect(primary, probe)

    assert res.ok is False
    assert res.method == "Check_nok_v2"


# Contenu neutre pour la sonde du test ci-dessous : le verdict NLP est forcé
# par monkeypatch via le marqueur MARQUEUR_VARIANTE, donc la prose réelle
# n'importe pas — seul compte le fait qu'elle diffère de HTML_EN/HTML_FR pour
# ne jamais être confondue avec le chemin primaire.
HTML_VARIANT_CASE9_LEXICAL = """<html lang="en-US"><body><p>
MARQUEUR_VARIANTE contenu neutre, sans signal de langue particulier.
</p></body></html>"""


@pytest.mark.asyncio
async def test_diagnostic_lexical_de_la_sonde_ne_fuit_pas_dans_la_reponse(monkeypatch):
    """Épingle la frontière entre le Volet A (rattrapage) et le Volet B
    (observation lexicale au Cas 9) : si la sonde elle-même retombe en Cas 9
    avec un diagnostic lexical dans `error`, ce candidat est rejeté par
    `if not candidate.ok: continue` (routes.py) — il ne doit JAMAIS ressortir.
    Régression que ce test attrape : un futur refactor qui propagerait ce
    candidat malgré `ok=False`, ou qui lirait son `error` avant ce test, ferait
    apparaître le diagnostic lexical calculé sur le texte de la VARIANTE
    attaché à une réponse qui parle de l'URL D'ORIGINE."""
    primary = AsyncMock(return_value=_scrape(HTML_EN))
    probe = AsyncMock(return_value=_scrape(HTML_VARIANT_CASE9_LEXICAL))

    real_fasttext = LanguageDetector.detect_from_text_content_fasttext

    def _fake_fasttext(self, content):
        if "MARQUEUR_VARIANTE" not in content:
            # Chemin primaire (HTML_EN) : comportement RÉEL, non stubé.
            return real_fasttext(self, content)
        # Mime automatismes.net (spec 2026-08-10 §1) : fastText tranche pour
        # une autre langue avec assurance, MAIS le compte lexical franchit le
        # seuil d'observation — exactement la situation où le Cas 9 écrit un
        # diagnostic dans `error` (domain_fr.py:1677-1691).
        return {
            "lang": "de", "confidence": 0.95,
            "method": "nlp_detection_fasttext",
            "details": {
                "fasttext": {"predictions": []}, "french_signal": 0.0,
                "french_exclusive_distinct": settings.LEXICAL_OBSERVATION_MIN_DISTINCT,
            },
        }

    monkeypatch.setattr(
        LanguageDetector, "detect_from_text_content_fasttext", _fake_fasttext
    )

    res = await _detect(primary, probe)

    assert probe.call_count == 3
    assert res.method == "Check_nok_v2"
    # Le diagnostic lexical de la SONDE n'a pas fuité sur la réponse à propos
    # de l'URL d'origine (HTML_EN n'a lui-même aucun mot exclusif français).
    assert res.error is None
