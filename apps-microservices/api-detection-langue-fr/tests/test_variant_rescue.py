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

HTML_CHALLENGE = """<html><head><title>Just a moment...</title></head>
<body><div id="cf-wrapper">Checking your browser before accessing the site.
DDoS protection by Cloudflare</div></body></html>"""


def _scrape(html, final_url=URL, status_code=200):
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


@pytest.fixture(autouse=True)
def _rescue_on(monkeypatch):
    """Budget généreux par défaut ; chaque test le resserre s'il le veut."""
    monkeypatch.setattr(settings, "VARIANT_RESCUE_BUDGET_S", 120, raising=False)


async def _detect(primary, probe, url=URL, html_content=None, cache_set=None):
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
    et transformerait un Check_nok_v2 en error — pire que le défaut corrigé."""
    monkeypatch.setattr(settings, "VARIANT_RESCUE_BUDGET_S", 1, raising=False)
    primary = AsyncMock(return_value=_scrape(HTML_EN))

    async def slow_probe(*a, **kw):
        await asyncio.sleep(3)
        return _scrape(HTML_FR)

    probe = AsyncMock(side_effect=slow_probe)
    res = await _detect(primary, probe)

    assert res.ok is False
    assert res.method == "Check_nok_v2"
    assert res.error is None or "imeout" not in (res.error or "")


@pytest.mark.asyncio
async def test_verdict_hors_perimetre_ne_sonde_pas():
    """http_error (404) est une propriété de la page, pas de la forme d'URL."""
    primary = AsyncMock(return_value=_scrape("<html><body>Not Found</body></html>",
                                             status_code=404))
    probe = AsyncMock(return_value=_scrape(HTML_FR))

    await _detect(primary, probe)

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
