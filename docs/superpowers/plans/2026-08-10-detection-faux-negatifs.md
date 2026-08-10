# Faux négatifs de détection FR — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rattraper les domaines français classés non-français, par un re-test des formes d'URL sur verdict inexploitable (actif), et instrumenter le signal lexical au Cas 9 pour décider plus tard d'un second rattrapage (inerte).

**Architecture:** Deux volets indépendants dans un seul service. Volet A ajoute un helper `_variant_rescue` dans `routes.py`, appelé après la matrice de décision quand le verdict est `Check_nok_v2` ou `fetch_empty_content` : une sonde `scrape_html` par variante d'URL, bornée par un budget horloge qui sert aussi de kill-switch. Volet B ajoute un compteur lexical dans `language_detector.py`, publié dans `details`, lu au Cas 9 pour écrire un diagnostic dans `error` — sans jamais changer le verdict.

**Tech Stack:** Python 3.10, FastAPI, pydantic-settings, pytest + pytest-asyncio, Camoufox/Playwright, prometheus_client.

**User decisions (already made):**
- « Les faux négatifs d'abord » — priorité sur les 40 erreurs d'infrastructure du même run, parce qu'un faux négatif est figé 7 jours alors qu'une erreur se rejoue.
- Une seule spec, **deux volets nettement séparés** (fichiers et risques disjoints), un seul rebuild.
- Périmètre du volet A : **`Check_nok_v2` + `fetch_empty_content`** seulement — le plus petit périmètre couvrant des cas mesurés.
- Volet B livré **en observation** : il expose et diagnostique, il ne décide pas.
- Spec approuvée en l'état : `docs/superpowers/specs/2026-08-10-detection-faux-negatifs-design.md` (commit `a55defa1`).

---

## Structure des fichiers

Tout est dans `apps-microservices/api-detection-langue-fr/`.

| Fichier | Rôle | Volet |
|---|---|---|
| `app/core/config.py` | 2 réglages : `VARIANT_RESCUE_BUDGET_S`, `LEXICAL_OBSERVATION_MIN_DISTINCT` | A + B |
| `app/core/metrics.py` | 1 compteur `VARIANT_RESCUE_OUTCOME` (issues du rattrapage) | A |
| `app/api/routes.py` | helper `_variant_rescue` + branchement après la matrice | A |
| `app/services/language_detector.py` | `_count_french_exclusive_distinct` + publication dans `details` | B |
| `app/core/domain_fr.py` | diagnostic au Cas 9 (`error`), verdict inchangé | B |
| `tests/test_variant_rescue.py` | **nouveau** — budget, kill-switch, périmètre, immunité `html_content`, cache | A |
| `tests/test_lexical_observation.py` | **nouveau** — compteur par langue, diagnostic, verdict inchangé | B |
| `CLAUDE.md` (service) | 2 sections + 2 lignes de tableau env | A + B |

**Aucun fichier créé côté application** : les deux volets se greffent sur des seams existantes. Un module séparé pour `_variant_rescue` serait un fichier pour une fonction, alors que son seul appelant est `_detect_single_url` juste au-dessus.

## Invariants à ne pas casser

1. **`html_content` fourni ⇒ zéro fetch.** `crawler-service` appelle avec `html_content` ; le rattrapage ne doit jamais s'y déclencher. Le garde est `not html_was_provided`.
2. **Un rattrapage ne dégrade jamais un verdict.** Toute issue autre qu'un succès rend le verdict d'origine **inchangé** — jamais un timeout, jamais une exception, jamais un `error`.
3. **Le verdict du Cas 9 ne change pas** (volet B) : `ok=False`, `method='Check_nok_v2'`. Seul `error` est renseigné.
4. **Le Cas 8 et son garde `soft_from_fasttext` ne sont pas touchés** (`domain_fr.py:1606-1611`).
5. **`_compute_french_signal` garde sa signature et sa valeur** : le Cas 8 déployé le lit (`domain_fr.py:1619`, `:1628`).

---

## Task 1: Volet A — rattrapage par variante d'URL

**Goal:** Sur un verdict `Check_nok_v2` ou `fetch_empty_content` obtenu après un fetch réussi, re-tester les formes http/https et www/apex de l'URL et retenir le premier verdict français, dans un budget horloge borné.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/config.py` (après la ligne 43, bloc `STUB_PAGE_HOP_ENABLED`)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/metrics.py` (fin de fichier)
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py` (imports `:30` et `:38` ; helper après `_format_failure_detail` `:82-87` ; branchement après `:403`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_variant_rescue.py` (nouveau)

**Acceptance Criteria:**
- [ ] `VARIANT_RESCUE_BUDGET_S=0` ⇒ `scrape_html` n'est appelé **aucune** fois et le verdict rendu est identique au verdict d'origine (kill-switch)
- [ ] Une sonde qui dépasse le budget rend le verdict d'origine **inchangé** (`method == 'Check_nok_v2'`), et non un `error` ni une exception
- [ ] Une variante française donne `ok=True`, `method` suffixé `+variant_rescue`, `analyzed_url` = l'URL de la variante
- [ ] La première variante en succès arrête la boucle (`scrape_html.call_count == 1`)
- [ ] Trois variantes non françaises ⇒ exactement 3 appels à `scrape_html` (une sonde par variante, jamais la cascade de `fetch_html`)
- [ ] Un verdict `http_error` ne déclenche aucune sonde (`scrape_html.call_count == 0`)
- [ ] `html_content` fourni ⇒ aucune sonde, quel que soit le verdict
- [ ] Une variante servant une page de challenge est ignorée sans compter comme succès
- [ ] Le résultat rattrapé est celui qui part au cache (`domain_cache.set` reçoit le `method` suffixé)

**Verify:** `python -m pytest tests/test_variant_rescue.py -v` → 9 passed

**Steps:**

- [ ] **Step 1: Écrire les tests (ils échouent tous — `_variant_rescue` n'existe pas)**

Créer `tests/test_variant_rescue.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `python -m pytest tests/test_variant_rescue.py -v`
Expected: FAIL — `AttributeError: <module 'app.api.routes'> does not have the attribute 'scrape_html'` (le nom n'est pas encore importé dans `routes.py`).

- [ ] **Step 3: Ajouter les deux réglages**

Dans `app/core/config.py`, après le bloc `STUB_PAGE_HOP_ENABLED` (ligne 43) :

```python
    # Rattrapage par variante d'URL sur verdict inexploitable (Check_nok_v2,
    # fetch_empty_content). Budget horloge total des sondes, vérifié AVANT
    # chaque variante ; dépassé, le verdict d'origine est rendu inchangé.
    # 0 désactive le rattrapage (kill-switch). Le défaut de 120 s est une
    # ESTIMATION : le coût réel d'une sonde n'a pas été mesuré sur la VM
    # (spec 2026-08-10 §9.4) — le compteur detection_variant_rescue_total sert
    # à le réviser.
    VARIANT_RESCUE_BUDGET_S: int = 120

    # Observation du signal lexical au Cas 9 : seuil de mots exclusivement
    # français DISTINCTS au-delà duquel un diagnostic est écrit dans `error`.
    # OBSERVATION, jamais décision — aucun verdict ne le lit. Volontairement
    # permissif (3) pour faire apparaître les cas limites entre le portugais
    # mesuré (1) et le français mesuré (9 à 15). 0 désactive le diagnostic.
    LEXICAL_OBSERVATION_MIN_DISTINCT: int = 3
```

- [ ] **Step 4: Ajouter le compteur**

À la fin de `app/core/metrics.py` :

```python
# Issues du rattrapage par variante d'URL sur verdict inexploitable.
# Valeurs de `outcome` : success, budget_exhausted, no_variant_french.
# Sert notamment à réviser le défaut de VARIANT_RESCUE_BUDGET_S, qui est une
# estimation non mesurée.
VARIANT_RESCUE_OUTCOME = Counter(
    "detection_variant_rescue_total",
    "Outcomes of the URL-variant rescue attempted on an unusable verdict",
    labelnames=("outcome",),
)
```

- [ ] **Step 5: Étendre les imports de `routes.py`**

Ligne 29 — ajouter le compteur :

```python
from app.core.metrics import VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED, ADMISSION_REJECTED, INFLIGHT_REQUESTS, VARIANT_RESCUE_OUTCOME
```

Ligne 30 — ajouter le générateur de variantes :

```python
from app.services.redirect_tracker import fetch_html, _generate_url_variants
```

Ligne 38 — ajouter la sonde :

```python
from app.services.scraper import ScrapeResult, scrape_html
```

`asyncio`, `time`, `settings`, `DomainFR` et `detect_challenge_page` sont déjà importés (`:1`, `:4`, `:27`, `:26`, `:31`).

- [ ] **Step 6: Écrire le helper**

Dans `app/api/routes.py`, juste après `_format_failure_detail` (fin ligne 87) :

```python
# Verdicts qu'une AUTRE FORME d'URL peut réparer. Ils ont en commun d'être nés
# d'un fetch RÉUSSI : la Phase 2 de fetch_html (permutation http/https,
# www/apex) ne s'est donc jamais exécutée, alors que c'est précisément le cas
# où elle répare. Les échecs de fetch ne figurent PAS ici — fetch_html a déjà
# permuté les variantes pour eux.
_VARIANT_RESCUE_METHODS = ('Check_nok_v2', 'fetch_empty_content')


async def _variant_rescue(
    url: str,
    proxy_url: Optional[str],
    mode: DetectionMode,
    use_nlp_detection: bool,
    forced_method: Optional[str],
) -> Optional[DetectionResponse]:
    """Re-teste les formes http/https et www/apex de `url`, rend le premier
    verdict français obtenu.

    Rend `None` — donc « garde le verdict d'origine » — dans TOUS les autres
    cas : budget nul, aucune variante, sonde en échec, sonde en timeout, page
    de challenge, aucune variante française. Un rattrapage ne doit jamais
    dégrader un verdict : le transformer en `error` par un timeout serait pire
    que le faux négatif qu'il corrige, puisqu'`error` n'est ni re-tenté en
    Pass 2 ni porteur d'une cause.
    """
    budget = settings.VARIANT_RESCUE_BUDGET_S
    if budget <= 0:
        return None

    variants = _generate_url_variants(url)
    if not variants:
        return None

    deadline = time.monotonic() + budget
    for variant in variants:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.info(f"[VARIANT-RESCUE] budget épuisé pour {url}")
            VARIANT_RESCUE_OUTCOME.labels(outcome="budget_exhausted").inc()
            return None

        try:
            # Une SONDE, pas une cible primaire : un seul scrape_html, jamais la
            # cascade de fetch_html (3 tentatives x ~85s ne tient dans aucun
            # budget). Même patron que la sonde de confirmation du Cas 6
            # (domain_fr.py:1460-1463). Le wait_for est borné par le RESTE du
            # budget, pas par une constante : une variante lente ne peut donc
            # pas le dépasser à elle seule.
            fetch = await asyncio.wait_for(
                scrape_html(variant, proxy=proxy_url or settings.APIFY_PROXY),
                timeout=remaining,
            )
        except Exception as e:
            # Y compris asyncio.TimeoutError : une sonde ratée n'est pas un
            # échec de la détection, c'est l'absence d'un rattrapage.
            # `Exception` et non `BaseException` : asyncio.CancelledError dérive
            # de BaseException depuis Python 3.8 et doit continuer à remonter —
            # un item annulé ne doit pas se présenter comme « aucune variante
            # française ».
            logger.info(f"[VARIANT-RESCUE] {variant} : sonde en échec ({e!r})")
            continue

        if not fetch or not fetch.html:
            continue

        challenge = detect_challenge_page(fetch.html)
        if challenge:
            logger.info(f"[VARIANT-RESCUE] {variant} : page {challenge}, ignorée")
            continue

        variant_final = fetch.final_url or variant
        # validate_alternatives=False, en dur : la question posée est « CETTE
        # forme d'URL est-elle française ? », pas « expose-t-elle une
        # alternative française ? » — la chasse aux alternatives a déjà eu lieu
        # sur la forme d'origine, avec le réglage de l'appelant. Sans ce faux,
        # la boucle du Cas 6 ouvrirait des navigateurs supplémentaires HORS du
        # budget (jusqu'à 120s par alternative), et l'annuler en pleine
        # navigation ré-ouvrirait le flood de callbacks orphelins que le commentaire
        # de domain_fr.py:1451-1459 documente.
        detector = DomainFR(
            homepage=variant_final,
            forced_method=forced_method,
            use_nlp_detection=use_nlp_detection,
            original_homepage=url,
            validate_alternatives=False,
        )
        candidate = await detector.check_page_if_french(fetch.html, mode)
        if not candidate.ok:
            continue

        candidate.analyzed_url = variant_final
        candidate.method = f"{candidate.method}+variant_rescue"
        logger.info(
            f"[VARIANT-RESCUE] OK {url} via {variant_final} ({candidate.method})"
        )
        VARIANT_RESCUE_OUTCOME.labels(outcome="success").inc()
        return candidate

    VARIANT_RESCUE_OUTCOME.labels(outcome="no_variant_french").inc()
    return None
```

- [ ] **Step 7: Brancher le rattrapage**

Dans `app/api/routes.py`, entre la ligne 403 (`result.analyzed_url = stub_target_used`) et la ligne 405 (`if not html_was_provided:`) :

```python
    # [4bis] Rattrapage par variante d'URL. `not html_was_provided` est
    # structurel : quand l'appelant fournit le HTML (crawler-service), aucun
    # fetch ne lui est dû et le rattrapage n'a pas de sens.
    if not html_was_provided and result.method in _VARIANT_RESCUE_METHODS:
        rescued = await _variant_rescue(
            url, proxy_url, mode, use_nlp_detection, forced_method,
        )
        if rescued:
            result = rescued
            # L'URL analysée devient la graine de l'entrée de cache, comme au
            # repli homepage (`domain_cache.set(url, homepage, …)` ligne 339).
            # La CLÉ reste le domaine d'origine.
            effective_url = rescued.analyzed_url or effective_url
```

- [ ] **Step 8: Lancer les tests jusqu'au vert**

Run: `python -m pytest tests/test_variant_rescue.py -v`
Expected: 9 passed.

Si `test_variante_francaise_rattrape` échoue avec `ok=False`, c'est que `HTML_FR` n'a pas convaincu le stack NLP présent dans le venv : **allonger la prose française**, ne pas affaiblir l'assertion. Le test doit prouver un rattrapage réel, pas un rattrapage stubé.

- [ ] **Step 9: Vérifier l'absence de régression sur les routes**

Run: `python -m pytest tests/test_routes_invalid_page.py tests/test_api.py tests/test_failure_detail_response.py -v`
Expected: aucun échec NOUVEAU. Référence connue avant ce chantier : `tests/test_api.py` a une **erreur de collecte préexistante** et `tests/test_domain_fr.py` **7 échecs préexistants** — les comparer, ne pas les compter comme introduits.

- [ ] **Step 10: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/config.py \
        apps-microservices/api-detection-langue-fr/app/core/metrics.py \
        apps-microservices/api-detection-langue-fr/app/api/routes.py \
        apps-microservices/api-detection-langue-fr/tests/test_variant_rescue.py
git commit -m "feat(detection): rescue an unusable verdict by re-testing URL forms"
```

---

## Task 2: Volet B — observation du signal lexical au Cas 9

**Goal:** Publier le nombre de mots exclusivement français distincts dans `details`, et écrire un diagnostic dans le champ `error` du Cas 9 quand il atteint le seuil d'observation — sans changer aucun verdict.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/language_detector.py` (nouvelle méthode après `_compute_french_signal` `:288-317` ; publication dans les deux `details` `:605-610` et `:680-688`)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` (avant le `return` du Cas 9, `:1661-1665`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_lexical_observation.py` (nouveau)

**Acceptance Criteria:**
- [ ] `_count_french_exclusive_distinct` rend un compte de mots **distincts** (un mot répété 10 fois compte 1)
- [ ] Sur de la prose française : `>= 5`. Sur de l'espagnol, de l'italien, de l'anglais : `<= 1`
- [ ] Sur du portugais : `<= 1` — le seuil ne doit pas être franchi par le seul mot `mais`, faux exclusif de la liste
- [ ] Moins de 10 mots : `0` (même plancher que `_compute_french_signal`)
- [ ] La clé `french_exclusive_distinct` est présente dans `details` des deux chemins NLP (`nlp_detection_fasttext` et `nlp_detection`)
- [ ] `_compute_french_signal` rend exactement la même valeur qu'avant sur les mêmes entrées (signature et valeur intactes)
- [ ] Au Cas 9, un compte au-dessus du seuil écrit `error` contenant `"N mots exclusifs distincts"`, avec `ok=False` et `method == 'Check_nok_v2'` inchangés
- [ ] Au Cas 9, un compte sous le seuil laisse `error is None`
- [ ] `LEXICAL_OBSERVATION_MIN_DISTINCT = 0` ⇒ aucun diagnostic
- [ ] Les tests préexistants du Cas 9 restent verts : leurs stubs n'ont pas la clé, donc `error` reste `None`

**Verify:** `python -m pytest tests/test_lexical_observation.py tests/test_soft_french_lexical.py tests/test_language_detector.py -v` → tout passe

**Steps:**

- [ ] **Step 1: Écrire les tests (ils échouent — la méthode n'existe pas)**

Créer `tests/test_lexical_observation.py` :

```python
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
        assert _counter()("le le le le le le le le le le le le") <= 1

    def test_texte_trop_court_rend_zero(self):
        assert _counter()("le la les des") == 0


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
```

- [ ] **Step 2: Lancer les tests pour les voir échouer**

Run: `python -m pytest tests/test_lexical_observation.py -v`
Expected: FAIL — `AttributeError: 'LanguageDetector' object has no attribute '_count_french_exclusive_distinct'`.

- [ ] **Step 3: Écrire le compteur**

Dans `app/services/language_detector.py`, juste après `_compute_french_signal` (fin ligne 317) :

```python
    def _count_french_exclusive_distinct(self, text: str) -> int:
        """Nombre de mots exclusivement français DISTINCTS présents dans le texte.

        Discriminant délibérément séparé du score agrégé de
        `_compute_french_signal`, qui SATURE et ne peut donc pas servir ici :
        mesuré le 2026-08-10, il vaut 1.000 pour du portugais comme pour du
        français, et 0.761 pour de l'espagnol. Le compte de mots exclusifs
        distincts sépare nettement — 9 à 15 pour du français rédigé, 0 à 1 pour
        les autres langues (spec 2026-08-10 §3).

        Distincts et non occurrences : un menu répétant « le » vingt fois n'est
        pas plus français qu'une phrase le contenant une fois.

        OBSERVATION uniquement — aucun verdict ne lit cette valeur pour décider.
        """
        words = re.findall(r'\b\w+\b', text.lower())
        # Même plancher que _compute_french_signal (:300-301) : sous 10 mots,
        # aucun compte n'est significatif.
        if len(words) < 10:
            return 0
        return len({w for w in words if w in self.FRENCH_EXCLUSIVE_STOPWORDS})
```

- [ ] **Step 4: Publier la clé dans les deux `details`**

Chemin fastText, dans `details` (`:680-688`) — ajouter après `'french_signal': round(french_signal, 3)` :

```python
                'french_signal': round(french_signal, 3),
                # Observation : discriminant non saturant, voir
                # _count_french_exclusive_distinct. Additif — aucun lecteur
                # existant de `details` n'en dépend.
                'french_exclusive_distinct': self._count_french_exclusive_distinct(text),
```

Chemin langdetect+langid, dans `details` (`:605-610`) — même ajout, après `'french_signal': round(french_signal, 3),` :

```python
                'french_exclusive_distinct': self._count_french_exclusive_distinct(text),
```

- [ ] **Step 5: Écrire le diagnostic au Cas 9**

Dans `app/core/domain_fr.py`, remplacer le bloc `:1655-1665` (commentaire du Cas 9 + `return`) par :

```python
        # Cas 9 : Aucun indicateur français trouvé.
        # NB: alternative_urls reste volontairement vide ici — le crawler
        # (routes.ts) et le BO (not_french_signal.php) traitent « ok=false +
        # alternatives non vides » comme un signal distinct de not_french ;
        # exposer les candidates trouvées-puis-rejetées casserait cette chaîne.
        # Le diagnostic passe par /detect-debug (debug.alternatives).
        #
        # OBSERVATION du signal lexical (aucune décision). Un faux négatif
        # mesuré le 2026-08-10 — automatismes.net, 3500 caractères de français
        # limpide, ni `html lang` ni hreflang ni TLD — n'atteint jamais le
        # Cas 8, dont le garde `soft_from_fasttext` (:1606-1611) exige que
        # fastText ait dit `fr`. Le compte de mots exclusifs distincts est donc
        # publié ICI, en clair, pour qu'un run réel dise combien de domaines
        # seraient rattrapables et à quel seuil. Le champ `error` est libre au
        # Cas 9 (aucune autre écriture) et déjà affiché par le rapport BO :
        # zéro changement de contrat. Le VERDICT, lui, ne change pas.
        lexical_note = None
        threshold = settings.LEXICAL_OBSERVATION_MIN_DISTINCT
        exclusive_distinct = (
            ((nlp_result or {}).get('details') or {}).get('french_exclusive_distinct')
        )
        if (
            threshold > 0
            and isinstance(exclusive_distinct, int)
            and exclusive_distinct >= threshold
        ):
            lexical_note = (
                f"lexical: {exclusive_distinct} mots exclusifs distincts — "
                f"rattrapage candidat"
            )
            logger.info(f"[LEXICAL-OBS] {url} : {lexical_note}")

        return DetectionResponse(
            ok=False,
            url=url,
            method='Check_nok_v2',
            error=lexical_note,
        )
```

- [ ] **Step 6: Lancer les tests jusqu'au vert**

Run: `python -m pytest tests/test_lexical_observation.py -v`
Expected: 13 passed.

Si `test_prose_francaise_au_dessus_du_seuil_dactivation_envisage` échoue, **allonger `FR_PROSE`** — c'est l'échantillon qui est trop court, pas le seuil qui est trop haut. Relever le compte réel de chaque échantillon et le noter en commentaire dans le test : c'est cette table qui servira à choisir le seuil d'activation.

- [ ] **Step 7: Vérifier que le Cas 8 et le Cas 9 préexistants sont intacts**

Run: `python -m pytest tests/test_soft_french_lexical.py tests/test_language_detector.py tests/test_domain_fr.py -v`
Expected: `test_soft_french_lexical.py` et `test_language_detector.py` entièrement verts ; `test_domain_fr.py` avec ses **7 échecs préexistants** et pas un de plus. Comparer à la référence, ne pas les compter comme introduits.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/language_detector.py \
        apps-microservices/api-detection-langue-fr/app/core/domain_fr.py \
        apps-microservices/api-detection-langue-fr/tests/test_lexical_observation.py
git commit -m "feat(detection): observe the lexical signal at Case 9, change no verdict"
```

---

## Task 3: Documentation du service

**Goal:** Le `CLAUDE.md` du service décrit les deux volets, leurs réglages et l'inertie du volet B, pour qu'une session future n'ait pas à relire le diff.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md` (section « URL-Variant Fallback Gate » ; tableau env vars ; nouvelle section pour le volet B)

**Acceptance Criteria:**
- [ ] La section « URL-Variant Fallback Gate » renvoie au rattrapage post-verdict, en distinguant les deux mécanismes : Phase 2 sur fetch en ÉCHEC, rattrapage sur fetch RÉUSSI mais inexploitable
- [ ] `VARIANT_RESCUE_BUDGET_S` et `LEXICAL_OBSERVATION_MIN_DISTINCT` figurent dans un tableau d'env vars avec leur défaut et leur rôle de kill-switch
- [ ] Une section dit explicitement que le volet B **ne change aucun verdict** et que le seuil de 3 est un seuil d'observation, distinct du seuil d'activation envisagé (5)
- [ ] Le suffixe de méthode `+variant_rescue` est documenté comme observable côté rapport BO
- [ ] La limite du volet B est écrite : une page sans prose ne produit aucun signal

**Verify:** `git diff --stat apps-microservices/api-detection-langue-fr/CLAUDE.md` → 1 file changed ; relire la section « URL-Variant Fallback Gate » et vérifier qu'elle ne prétend plus que les variantes ne sont tentées que sur échec.

**Steps:**

- [ ] **Step 1: Étendre la section « URL-Variant Fallback Gate »**

Ajouter à la fin de cette section :

```markdown
**Rattrapage post-verdict (`+variant_rescue`).** La Phase 2 ci-dessus ne concerne
que les fetchs en **échec**. Un fetch **réussi** dont le verdict est inexploitable
(`Check_nok_v2`, `fetch_empty_content`) verrouillait donc la forme d'URL testée —
alors que c'est exactement le cas où la permutation répare : la redirection vers
le vrai site n'existant que sur `http` (groupe-denis.com → ibyd.fr) ou sur l'apex.
`_variant_rescue` (`app/api/routes.py`) re-teste les formes après la matrice de
décision : **une** sonde `scrape_html` par variante (jamais la cascade), avec
`validate_alternatives=False` en dur pour que la boucle du Cas 6 n'ouvre pas de
navigateurs hors budget. La première variante rendant `ok=True` gagne ; son
`method` est suffixé `+variant_rescue` et `analyzed_url` porte l'URL retenue, ce
qui rend le rattrapage mesurable dans le rapport BO sans y changer une ligne.

Toute autre issue rend le verdict d'origine **inchangé** — jamais un timeout, ce
qui transformerait un `Check_nok_v2` en `error`, non re-tenté en Pass 2 et sans
cause. `VARIANT_RESCUE_BUDGET_S=0` désactive le rattrapage. Ne se déclenche
jamais quand l'appelant fournit `html_content` : **crawler-service est immune**.
Métrique : `detection_variant_rescue_total{outcome=success|budget_exhausted|no_variant_french}`.
```

- [ ] **Step 2: Ajouter la section du volet B**

À la suite, une nouvelle section :

```markdown
## Observation du signal lexical au Cas 9 (inerte)

`_count_french_exclusive_distinct` (`app/services/language_detector.py`) publie
dans `details` le nombre de mots **exclusivement français distincts**. Le score
agrégé `french_signal` ne pouvait pas servir : mesuré le 2026-08-10 il **sature**
— 1.000 pour du portugais comme pour du français, 0.761 pour de l'espagnol —
tandis que le compte de distincts sépare nettement (9 à 15 pour du français
rédigé, 0 à 1 ailleurs).

Au Cas 9, un compte atteignant `LEXICAL_OBSERVATION_MIN_DISTINCT` écrit un
diagnostic dans `error` (`"lexical: N mots exclusifs distincts — rattrapage
candidat"`). **Le verdict ne change pas** : `ok=False`, `method='Check_nok_v2'`.

Pourquoi inerte : le faux négatif visé (automatismes.net — français limpide, ni
`html lang` ni hreflang ni TLD, fastText confiant dans une autre langue) ne peut
pas être rattrapé par le Cas 8, dont le garde `soft_from_fasttext` exige que
fastText ait dit `fr`. Élargir ce garde demande un seuil, et le seuil ne repose
pour l'instant que sur six textes courts. **3 est un seuil d'OBSERVATION**,
volontairement permissif pour faire apparaître les cas limites ; le seuil
d'ACTIVATION envisagé est 5, et il n'est pas implémenté.

Deux limites à connaître : un mot de la liste « exclusivement française »,
`mais`, est du portugais courant — c'est pourquoi un seuil à 1 serait faux ; et
une page française **sans prose** (catalogue de références) marque 0, donc ce
mécanisme ne sauvera jamais que des pages rédigées.

Spec : `docs/superpowers/specs/2026-08-10-detection-faux-negatifs-design.md`.
```

- [ ] **Step 3: Ajouter les deux réglages au tableau des env vars**

Dans le tableau de la section « Invalid Page Rejection & Homepage Fallback » (celui qui contient `STUB_PAGE_HOP_ENABLED`) :

```markdown
| `VARIANT_RESCUE_BUDGET_S` | `120` | Budget horloge total des sondes de rattrapage par variante, vérifié AVANT chaque variante. Dépassé → verdict d'origine inchangé. `0` désactive (kill-switch). Défaut **estimé**, non mesuré sur la VM. |
| `LEXICAL_OBSERVATION_MIN_DISTINCT` | `3` | Seuil de mots exclusivement français distincts au-delà duquel le Cas 9 écrit un diagnostic dans `error`. Observation seule, aucun verdict n'en dépend. `0` désactive. |
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/CLAUDE.md
git commit -m "docs(detection): document the variant rescue and the lexical observation"
```

---

## Déploiement

Un seul rebuild Docker de `api-detection-langue-fr` sur la VM. **Aucun BO, aucune migration.**

Les deux volets sont livrés **actifs par défaut** au sens du code, mais leur risque est asymétrique :
- volet A **agit** (`VARIANT_RESCUE_BUDGET_S=120`) → mettre `0` le neutralise sans rebuild ;
- volet B **n'agit pas** par construction : il écrit du texte dans un champ vide et ne touche à aucun verdict.

Fumée après rebuild, sur un domaine du run 2026-08-10 :

```bash
curl -s -X POST https://<host>/api/v1/detect \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://groupe-denis.com/","force_refresh":true}' | jq '.ok,.method,.analyzed_url'
```

Attendu si le rattrapage prend : `true`, un `method` suffixé `+variant_rescue`, et un `analyzed_url` différent de l'URL demandée. Puis vérifier `detection_variant_rescue_total` sur `/metrics`, et lire les `error` des `Check_nok_v2` du prochain run pour la table de comptes du volet B.

## Points laissés ouverts, à ne pas présumer résolus

Repris de la spec §9 — l'implémentation ne doit ni les fermer ni les contourner :

1. **`6351 rgb-solutions.green` reste ambigu** entre les deux défauts. Le discriminant est `/detect-debug` sur les deux formes, qui n'a pas été fait. Ne pas le compter comme un succès du volet A.
2. **Le seuil de 5 n'est pas éprouvé** — six textes courts, dont quatre rédigés par l'assistant. C'est la raison d'être du mode observation.
3. **`mais` dans `FRENCH_EXCLUSIVE_STOPWORDS`** est un faux exclusif. Le retirer changerait le score agrégé, donc le comportement du Cas 8 **déjà déployé** : hors périmètre ici, chantier séparé.
4. **Le coût réel d'une sonde n'a pas été mesuré sur la VM.** Le défaut de 120 s est une estimation ; le compteur ajouté sert à la réviser après un run.
5. **Rattrapage cross-domaine** (2493 → `ibyd.fr`) : la clé de cache reste le domaine d'origine et `analyzed_url` porte la cible, exactement comme le repli homepage. Vérifier ce que les appelants BO font de cette valeur — un chantier « cross-domain result pairing » et un garde de déduplication à l'insertion existent déjà de ce côté.
