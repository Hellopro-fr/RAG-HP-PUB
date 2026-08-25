# Cause d'échec de fetch + proposition de retrait — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un échec de fetch porte sa cause réelle jusqu'à l'appelant HTTP (B1), et un script BO propose des domaines à retirer sans rien écrire sans `--apply` (B2, inerte à la livraison).

**Architecture:** B1 ajoute un canal de sortie **parallèle** (`error_sink`, un dict fourni par l'appelant) à `scrape_html` → `fetch_html` → `_fetch_with_admission` → `routes.py`, exposé par un champ additif `failure_detail` sur `DetectionResponse`. Aucune classification, aucune liste de codes. B2 persiste la cause dans une clé du blob JSON `data_crawling_dspi` (aucune migration) et ajoute un script `--apply`/`?run=1` dont la liste de causes est vide.

**Tech Stack:** Python 3.10 / FastAPI / pydantic 2.10.5 / pytest (service) ; PHP 7.4 / mysqli (BO).

**Spec:** `docs/superpowers/specs/2026-08-06-detection-failure-cause-and-retire-proposal-design.md` (commit `d647dd5a`).

**User decisions (already made):**
- « Nous allons partir sur ta recommendation » → cause **brute**, jamais de classification ni de libellé deviné.
- « on peut spécifier mais ne pas activer directement mais d'abord que je valide sur la liste » → B2 livrée inerte, liste de causes vide.
- Découpage validé : B1 complète et activable + B2 mécanisme paramétrable.
- Persistance : blob `data_crawling_dspi`, **un seul constat suffit**, aucune migration, pas d'état « refusé ».
- Design approuvé section par section le 2026-08-06.

---

## Global Constraints

Ces contraintes sont des **non-régressions vérifiées dans le code**. Les violer casse des chantiers déjà déployés.

1. **`last_error` conserve exactement ses valeurs actuelles.** Il alimente la garde
   `variant_pointless` (`redirect_tracker.py:298-301`) via
   `_VARIANT_POINTLESS_ERRORS = ('Timeout', 'Contenu vide ou trop court')`. Y injecter la
   vraie cause inverserait cette garde : un échec aujourd'hui « pointless » deviendrait
   « réparable » et re-déclencherait les 3 variantes. Le sink est un canal **parallèle**,
   il ne remplace rien.
2. **Le proxy ne doit JAMAIS entrer dans la cause.** `settings.APIFY_PROXY` a la forme
   `http://auto:{password}@proxy.apify.com:8000` (`app/core/config.py:57-64`).
   `failure_detail` part dans une réponse HTTP puis dans un mail opérateur. Le log local
   `scraper.py:399` inclut le proxy ; le sink ne doit pas.
3. **Premier écrivain gagne dans un même appel de `scrape_html`.** Une erreur de
   navigation suivie d'un « contenu trop court » doit conserver la cause de navigation,
   qui est la racine.
4. **Le sink n'est lu que si le résultat est falsy.** La branche navigation transitoire
   (`scraper.py:448-449`) écrit dans le sink **puis continue** et peut réussir
   l'extraction partielle. Un sink rempli n'implique pas un échec.
5. **Ne PAS toucher ces trois listes mortes** : `_VARIANT_ELIGIBLE_ERRORS`
   (`redirect_tracker.py:13-17`), `_FATAL_ERRORS` (`:20-24`), `_PERMANENT_NAV_ERRORS`
   (`scraper.py:137-142`).
   **Elles sont mortes pour DEUX raisons distinctes** (correction du 2026-08-07 — une
   version antérieure les amalgamait toutes en « listes Chromium ») :
   - `_VARIANT_ELIGIBLE_ERRORS` et `_PERMANENT_NAV_ERRORS` contiennent des codes `ERR_*`
     **Chromium** et ne matchent jamais sur le moteur déployé (Camoufox/Firefox). Les
     réparer exige de vrais libellés Gecko, qui ne sont attestés nulle part.
   - `_FATAL_ERRORS` contient des chaînes **françaises propres au service**
     (`'Proxy non configuré'`, `'Proxy obligatoire'`, `'Proxy invalide'`) — aucun code
     Chromium. Elle est morte parce que `scrape_html` **retourne `None` au lieu de lever**
     sur ces cas (`scraper.py:393-400`), donc la branche `except` qui la teste est
     inatteignable. Y ajouter des codes Gecko ne la réparerait pas.
6. **`error_sink` est optionnel avec défaut `None`** partout. Les 2 appelants de
   `scrape_html` dans `domain_fr.py` (`:438`, `:1461`) et les 3 appels de
   `_fetch_with_admission` hors périmètre (`routes.py:261`, `:266`, `:349`) ne changent
   pas d'une ligne.
7. **Le point de retour `redirect_tracker.py:269`** (branche `_FATAL_ERRORS`) n'est
   **pas** câblé : spec §2.1 l'établit inatteignable.

---

## File Structure

**B1 — `apps-microservices/api-detection-langue-fr/` (RAG-HP-PUB, `features/poc`)**

| Fichier | Responsabilité |
|---|---|
| `app/services/scraper.py` (modif) | **Capture** : helper `_record_failure` + écriture aux 4 points d'échec. |
| `app/services/redirect_tracker.py` (modif) | **Agrégation** sur les tentatives Phase 1 + Phase 2, publication vers l'appelant. |
| `app/models/schemas.py` (modif) | Champ additif `failure_detail`. |
| `app/api/routes.py` (modif) | **Exposition** : `_fetch_with_admission` passe le sink ; 2 sites `fetch_failed`. |
| `tests/test_failure_cause_sink.py` (créer) | Capture + agrégation. |
| `tests/test_failure_detail_response.py` (créer) | Exposition + rétrocompatibilité cache. |

**B2 — `BO/admin/repertoire_test/moulinettes_...` (Marketplace, `master`)**

| Fichier | Responsabilité |
|---|---|
| `moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php` (créer) | Fonctions **pures** apply/read/strip + normalisation de groupe. |
| `moulinettes_rindra/.../roadmap_v1/pct_traitement_crawling_rindra_BO.php` (modif) | Pose / efface le marqueur. |
| `moulinettes_rindra/.../roadmap_v1/pct_propose_retire_domaine_mort_rindra_BO.php` (créer) | Script propose / `--apply`. |
| `moulinettes_rindra/.../roadmap_v1/test_detect_failure_pure.php` (créer) | Tests des fonctions pures. |

---

## Task 1: Capture de la cause dans scraper.py

**Goal:** `scrape_html` écrit la cause de son échec dans un dict fourni par l'appelant, sans changer son type de retour ni son comportement.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py` (signature `:367`, points `:386-391`, `:393-395`, `:397-400`, `:440-449`, `:558-560`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_failure_cause_sink.py` (créer)

**Acceptance Criteria:**
- [ ] `FAILURE_CAUSE_MAX_LEN = 200` défini au niveau module
- [ ] `_record_failure(sink, stage, cause)` : no-op si `sink is None` ; no-op si `'cause'` est déjà présent (premier écrivain gagne) ; ne garde que la première ligne ; tronque à 200 caractères ; tolère `cause=''` sans lever `IndexError`
- [ ] `scrape_html` accepte `error_sink: Optional[dict] = None` en dernier paramètre
- [ ] Écriture aux 4 points avec le `stage` correspondant : `runtime` (`:386`), `proxy` (`:393` et `:397`), `navigation` (`:440`, avant le `raise` **et** dans la branche avalée), `content` (`:558`)
- [ ] **La cause du stage `proxy` ne contient ni la valeur du proxy ni le mot de passe**
- [ ] `error_sink=None` ⇒ comportement inchangé (aucun appelant existant modifié)
- [ ] Le `stage` est une constante littérale au site d'appel, jamais dérivée du texte de l'erreur

**Verify:** `python -m pytest tests/test_failure_cause_sink.py tests/test_scraper.py tests/test_scraper_result.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_failure_cause_sink.py
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
async def test_scrape_html_records_proxy_stage_without_leaking_secret():
    sink = {}
    result = await scraper.scrape_html(
        'https://example.com',
        proxy='http://auto:SUPERSECRET@proxy.apify.com:8000/broken',
        error_sink=sink,
    )
    # _parse_proxy rejette cette valeur -> stage proxy
    if result is None and sink.get('stage') == 'proxy':
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_failure_cause_sink.py -v`
Expected: FAIL — `AttributeError: module 'app.services.scraper' has no attribute '_record_failure'`

- [ ] **Step 3: Add the helper and the constant**

Dans `app/services/scraper.py`, juste après `_PERMANENT_NAV_ERRORS` (`:142`) :

```python
# Longueur max d'une cause publiée. Le message Playwright est multi-lignes et embarque
# le call-log complet : sans troncature on l'injecterait dans chaque réponse HTTP et
# dans le cache Redis.
FAILURE_CAUSE_MAX_LEN = 200


def _record_failure(sink: Optional[dict], stage: str, cause: str) -> None:
    """Publie la cause d'un échec dans le dict fourni par l'appelant.

    `stage` vient du SITE D'APPEL, jamais d'une analyse de `cause` : c'est ce qui
    garantit qu'aucun libellé d'erreur n'est présupposé (aucun code Gecko/Chromium
    n'est attesté en production — cf. spec §2.3).

    Premier écrivain gagne : dans un même appel, une erreur de navigation est la
    racine du « contenu trop court » qui suit, donc elle ne doit pas être écrasée.

    NE JAMAIS passer une valeur de proxy dans `cause` : elle contient un mot de
    passe et cette chaîne finit dans une réponse HTTP puis dans un mail opérateur.
    """
    if sink is None or 'cause' in sink:
        return
    lines = (cause or '').splitlines()
    sink['cause'] = (lines[0] if lines else '')[:FAILURE_CAUSE_MAX_LEN]
    sink['stage'] = stage
```

- [ ] **Step 4: Thread the parameter and write at the 4 points**

Signature (`:367`) :

```python
async def scrape_html(
    url: str,
    timeout: int = 90,
    proxy: Optional[str] = None,
    error_sink: Optional[dict] = None,
) -> Optional[ScrapeResult]:
```

Point `runtime` (`:386-391`) — ajouter avant le `return None` :

```python
    if async_playwright is None:
        logger.error(
            "Playwright non installé. Installez-le avec: "
            "pip install playwright && python -m playwright install chromium"
        )
        _record_failure(error_sink, 'runtime', 'Playwright non installé')
        return None
```

Points `proxy` (`:393-400`) — noter l'absence délibérée de la valeur du proxy :

```python
    if not proxy:
        logger.error(f"Proxy obligatoire pour scrape_html: {url}")
        _record_failure(error_sink, 'proxy', 'Proxy obligatoire non fourni')
        return None

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        logger.error(f"Proxy invalide pour {url}: {proxy}")
        # Volontairement SANS la valeur du proxy : elle contient le mot de passe.
        _record_failure(error_sink, 'proxy', 'Proxy invalide (format non reconnu)')
        return None
```

Point `navigation` (`:440-449`) — dans les **deux** branches :

```python
                except Exception as nav_e:
                    err_str = str(nav_e)
                    _record_failure(error_sink, 'navigation', err_str or type(nav_e).__name__)
                    # Erreurs permanentes — re-raise pour que fetch_html puisse
                    # classifier l'erreur et basculer vers les variantes URL (Phase 2)
                    if any(err in err_str for err in _PERMANENT_NAV_ERRORS):
                        logger.error(f"Erreur navigation permanente pour {url}: {err_str.splitlines()[0]}")
                        raise  # finally block will close context + browser

                    # Erreurs transitoires (proxy, timeout) — on tente l'extraction partielle
                    logger.warning(f"Timeout/Erreur navigation pour {url} (extraction partielle tentée): {nav_e}")
```

Point `content` (`:558-560`) :

```python
                else:
                    logger.warning(f"Contenu trop court pour {url}")
                    _record_failure(error_sink, 'content', 'Contenu vide ou trop court')
                    return None
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_failure_cause_sink.py tests/test_scraper.py tests/test_scraper_result.py -v`
Expected: PASS (les 2 suites existantes prouvent la non-régression du chemin sans sink)

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/scraper.py \
        apps-microservices/api-detection-langue-fr/tests/test_failure_cause_sink.py
git commit -m "feat(detection): capture la cause d'un echec de scrape dans un sink appelant"
```

---

## Task 2: Agrégation et publication dans redirect_tracker.py

**Goal:** `fetch_html` retient la cause de la tentative la plus informative — Phase 1 **et** Phase 2 — et la publie vers son appelant, sans modifier `last_error`.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py` (signature `:201`, boucle `:235-282`, returns `:224`/`:307`/`:340`, boucle Phase 2 `:318-334`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_failure_cause_sink.py` (étendre)

**Acceptance Criteria:**
- [ ] `fetch_html` accepte `error_sink: Optional[dict] = None`
- [ ] Une variable `last_failure: Optional[dict]` agrège les sinks des tentatives ; **`last_error` garde exactement ses valeurs actuelles** (`"Contenu vide ou trop court"` et `str(e) or type(e).__name__`)
- [ ] Quand une exception survient hors des 4 points instrumentés (sink vide), la cause est `last_error` avec `stage='browser'` — déduit de l'absence d'écriture, pas du texte
- [ ] **La boucle Phase 2 (`:318-334`) alimente `last_failure`** (le trou actuel)
- [ ] La cause est publiée avant les returns `:224`, `:307` et `:340` ; **pas** avant `:269`
- [ ] La dernière tentative non vide gagne au niveau `fetch_html` (Phase 2 écrase Phase 1 — c'est l'échec le plus récent)
- [ ] `error_sink=None` ⇒ comportement inchangé
- [ ] La garde `variant_pointless` produit les mêmes décisions qu'avant (test de non-régression explicite)

**Verify:** `python -m pytest tests/test_failure_cause_sink.py tests/test_variant_gate.py tests/test_redirect_tracker_result.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# à ajouter dans tests/test_failure_cause_sink.py
import asyncio
from app.services import redirect_tracker


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
    sink = {}
    assert await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink=sink) is None
    assert sink['cause'] == 'NS_ERROR_EXAMPLE'
    assert sink['stage'] == 'navigation'


@pytest.mark.asyncio
async def test_fetch_html_publishes_phase2_cause(monkeypatch):
    """Le trou actuel : la boucle variantes n'alimentait rien."""
    fake, _ = _fake_scrape([
        {'cause': 'PHASE1_CAUSE', 'stage': 'navigation'},   # 3 tentatives Phase 1
        {'cause': 'PHASE1_CAUSE', 'stage': 'navigation'},
        {'cause': 'PHASE1_CAUSE', 'stage': 'navigation'},
        {'cause': 'PHASE2_CAUSE', 'stage': 'navigation'},   # variantes
    ])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', lambda u: ['http://x.test'])
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', lambda *_a, **_k: asyncio.sleep(0))
    sink = {}
    await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink=sink)
    assert sink['cause'] == 'PHASE2_CAUSE'


@pytest.mark.asyncio
async def test_fetch_html_uses_browser_stage_when_sink_empty(monkeypatch):
    """Exception hors des 4 points instrumentes -> stage deduit de l'absence d'ecriture."""
    fake, _ = _fake_scrape([RuntimeError('new_context exploded')])
    monkeypatch.setattr(redirect_tracker, 'scrape_html', fake)
    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', lambda u: [])
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', lambda *_a, **_k: asyncio.sleep(0))
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
    monkeypatch.setattr(redirect_tracker.asyncio, 'sleep', lambda *_a, **_k: asyncio.sleep(0))
    variants_called = {'n': 0}

    def _variants(u):
        variants_called['n'] += 1
        return ['http://x.test']

    monkeypatch.setattr(redirect_tracker, '_generate_url_variants', _variants)
    await redirect_tracker.fetch_html('https://x.test', proxy='p', error_sink={})
    # 'Contenu vide ou trop court' est pointless -> variantes sautees -> 3 appels, pas 4
    assert calls['n'] == 3
    assert variants_called['n'] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_failure_cause_sink.py -k fetch_html -v`
Expected: FAIL — `TypeError: fetch_html() got an unexpected keyword argument 'error_sink'`

- [ ] **Step 3: Add the publish helper**

Après `_VARIANT_POINTLESS_ERRORS` (`:38`) :

```python
def _publish_failure(sink: Optional[dict], failure: Optional[dict]) -> None:
    """Recopie la cause agrégée dans le dict de l'appelant, si les deux existent."""
    if sink is not None and failure:
        sink.update(failure)
```

- [ ] **Step 4: Thread and aggregate**

Signature (`:201`) :

```python
async def fetch_html(
    url: str,
    proxy: Optional[str] = None,
    error_sink: Optional[dict] = None,
) -> Optional[ScrapeResult]:
```

Initialisation, à côté de `last_error = None` (`:227`) :

```python
    last_error = None
    # Canal PARALLÈLE à last_error. Ne le remplace JAMAIS : last_error pilote la garde
    # variant_pointless plus bas, et y injecter la vraie cause inverserait cette garde.
    last_failure: Optional[dict] = None
```

Retour proxy absent (`:224`) — publier avant :

```python
    if not effective_proxy:
        logger.error(f"Proxy obligatoire pour fetch_html: {url}. "
                     f"Configurez APIFY_PROXY ou passez proxy_url.")
        _publish_failure(error_sink, {'cause': 'Proxy obligatoire non fourni', 'stage': 'proxy'})
        return None
```

Boucle Phase 1 (`:243-264`) :

```python
        attempt_sink: dict = {}
        try:
            result = await scrape_html(url, proxy=attempt_proxy, error_sink=attempt_sink)
            if result:
                if attempt > 1:
                    logger.info(f"Récupération réussie pour {url} à la tentative {attempt}/{max_retries}")
                return result

            # Contenu vide/trop court — retryable
            last_error = "Contenu vide ou trop court"
            if attempt_sink.get('cause'):
                last_failure = dict(attempt_sink)
            saw_repairable = saw_repairable or not any(
                tok in last_error for tok in _VARIANT_POINTLESS_ERRORS
            )

        except Exception as e:
            last_error = str(e) or type(e).__name__
            if attempt_sink.get('cause'):
                last_failure = dict(attempt_sink)
            else:
                # Le sink est vide : l'échec est hors des points instrumentés de
                # scrape_html (new_context/new_page/launch). Le stage est déduit de
                # cette absence, pas du texte de l'erreur.
                last_failure = {'cause': last_error[:200], 'stage': 'browser'}
            saw_repairable = saw_repairable or not any(
                tok in last_error for tok in _VARIANT_POINTLESS_ERRORS
            )
            ...  # le reste du bloc except est INCHANGÉ (_FATAL_ERRORS, _VARIANT_ELIGIBLE_ERRORS)
```

Retour garde variantes (`:307`) :

```python
    if variant_pointless and not saw_repairable:
        logger.warning(...)  # INCHANGÉ
        _publish_failure(error_sink, last_failure)
        return None
```

Boucle Phase 2 (`:318-334`) — **le trou à combler** :

```python
        for variant in variants:
            variant_sink: dict = {}
            try:
                variant_proxy = build_proxy_url(effective_proxy, country=None)
                logger.warning(f"[VARIANTE] Test {variant}")
                result = await scrape_html(variant, proxy=variant_proxy, error_sink=variant_sink)
                if result:
                    logger.warning(
                        f"[VARIANTE] Succès avec {variant} → {result.final_url} "
                        f"({len(result.html)} caractères)"
                    )
                    return result
                if variant_sink.get('cause'):
                    last_failure = dict(variant_sink)
            except Exception as e:
                if variant_sink.get('cause'):
                    last_failure = dict(variant_sink)
                else:
                    last_failure = {'cause': (str(e) or type(e).__name__)[:200], 'stage': 'browser'}
                if not _is_retryable_error(str(e)):
                    logger.warning(f"[VARIANTE] Erreur permanente pour {variant}: {e}")
                    continue
                logger.warning(f"[VARIANTE] Échec pour {variant}: {e}")
                continue
```

Retour final (`:340`) :

```python
    _publish_failure(error_sink, last_failure)
    return None
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_failure_cause_sink.py tests/test_variant_gate.py tests/test_redirect_tracker_result.py -v`
Expected: PASS — `test_variant_gate.py` prouve que la garde n'a pas bougé.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py \
        apps-microservices/api-detection-langue-fr/tests/test_failure_cause_sink.py
git commit -m "feat(detection): agrege la cause d'echec sur les deux phases de fetch_html"
```

---

## Task 3: Exposition via failure_detail sur DetectionResponse

**Goal:** Une réponse `fetch_failed` porte la cause observée dans un champ additif, sans casser aucun consommateur ni aucune entrée de cache antérieure.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/models/schemas.py:109-112` (après `analyzed_url`)
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py:53-78` (`_fetch_with_admission`), `:186-205` (chemin `/detect`), `:858-864` (miroir debug)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_failure_detail_response.py` (créer)

**Acceptance Criteria:**
- [ ] `DetectionResponse.failure_detail: Optional[str] = None`
- [ ] Format `"<stage>: <cause>"` quand une cause existe, `None` sinon
- [ ] `_fetch_with_admission` accepte `error_sink: Optional[dict] = None` et le passe à `fetch_html`
- [ ] Câblé aux **deux** sites `fetch_failed` : `routes.py:202-205` et le miroir debug `:858-864`
- [ ] `DetectionResponse(**cached)` sur un payload SANS la clé ⇒ `failure_detail is None`, aucune exception (rétrocompatibilité du cache)
- [ ] Les 3 appels de `_fetch_with_admission` hors périmètre (`:261`, `:266`, `:349`) ne fournissent pas de sink et sont inchangés
- [ ] Le champ n'apparaît jamais dans une réponse `ok=True`

**Verify:** `python -m pytest tests/test_failure_detail_response.py tests/test_routes_invalid_page.py tests/test_domain_cache_ttl.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_failure_detail_response.py
from app.models.schemas import DetectionResponse


def test_failure_detail_defaults_to_none():
    r = DetectionResponse(ok=False, url='https://x.test', method='fetch_failed')
    assert r.failure_detail is None


def test_failure_detail_roundtrips():
    r = DetectionResponse(
        ok=False, url='https://x.test', method='fetch_failed',
        failure_detail='navigation: NS_ERROR_EXAMPLE',
    )
    assert r.model_dump()['failure_detail'] == 'navigation: NS_ERROR_EXAMPLE'


def test_cached_payload_without_the_key_still_builds():
    """Une entree de cache anterieure au deploiement n'a pas la cle."""
    cached = {'ok': False, 'url': 'https://x.test', 'method': 'fetch_empty_content'}
    assert DetectionResponse(**cached).failure_detail is None


def test_unknown_keys_still_tolerated():
    """Le code prod fait DetectionResponse(**cached) avec des cles en plus (requested_url)."""
    cached = {'ok': False, 'url': 'https://x.test', 'method': 'fetch_failed', 'requested_url': 'y'}
    assert DetectionResponse(**cached).method == 'fetch_failed'


def test_format_helper():
    from app.api.routes import _format_failure_detail
    assert _format_failure_detail({}) is None
    assert _format_failure_detail({'cause': 'C', 'stage': 'navigation'}) == 'navigation: C'
    assert _format_failure_detail({'cause': 'C'}) == 'unknown: C'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_failure_detail_response.py -v`
Expected: FAIL — `failure_detail` inconnu / `ImportError: cannot import name '_format_failure_detail'`

- [ ] **Step 3: Add the field**

Dans `app/models/schemas.py`, après `analyzed_url` (`:109-112`) :

```python
    failure_detail: Optional[str] = Field(
        default=None,
        description="Cause brute observée d'un échec de fetch, au format '<stage>: <cause>'. "
                    "Aucune classification : la chaîne est celle du moteur, tronquée. "
                    "None quand aucune cause n'a été capturée."
    )
```

- [ ] **Step 4: Add the formatter and thread the sink**

Dans `app/api/routes.py`, près de `_fetch_with_admission` :

```python
def _format_failure_detail(sink: dict) -> Optional[str]:
    """Formate le sink en une chaîne publiable, ou None si rien n'a été capturé."""
    cause = (sink or {}).get('cause')
    if not cause:
        return None
    return f"{(sink or {}).get('stage') or 'unknown'}: {cause}"
```

`_fetch_with_admission` (`:53-78`) :

```python
async def _fetch_with_admission(
    url: str,
    proxy_url: Optional[str],
    endpoint_label: str,
    error_sink: Optional[dict] = None,
):
    ...
    try:
        return await fetch_html(url, proxy_url, error_sink=error_sink)
    finally:
        ...
```

Chemin `/detect` (`:186-205`) — déclarer le sink avant le bloc de fetch, puis :

```python
        fetch_sink: dict = {}
        if _INFLIGHT_DEDUP_ENABLED:
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key,
                lambda: _fetch_with_admission(url, proxy_url, "/api/v1/detect", error_sink=fetch_sink),
            )
        else:
            fetch_result = await _fetch_with_admission(
                url, proxy_url, "/api/v1/detect", error_sink=fetch_sink
            )

        if not fetch_result:
            return DetectionResponse(
                ok=False, url=url, method='fetch_failed',
                error='Impossible de récupérer le contenu HTML',
                failure_detail=_format_failure_detail(fetch_sink),
            )
```

> **Limite connue, à documenter en Task 7** : sous dedup, seul le *leader* exécute la
> lambda, donc un *follower* reçoit `failure_detail=None` pour la même URL. Acceptable
> (même cause, et le leader la publie) ; ne pas tenter de partager le sink entre
> coroutines.

Miroir debug (`:858-864`) — même schéma avec son propre sink.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_failure_detail_response.py tests/test_routes_invalid_page.py tests/test_domain_cache_ttl.py -v`
Expected: PASS

- [ ] **Step 6: Run the whole suite for regressions**

Run: `python -m pytest tests/ -q`
Expected: aucun nouvel échec par rapport à la référence (7 échecs pré-existants dans `tests/test_domain_fr.py`)

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/models/schemas.py \
        apps-microservices/api-detection-langue-fr/app/api/routes.py \
        apps-microservices/api-detection-langue-fr/tests/test_failure_detail_response.py
git commit -m "feat(detection): expose failure_detail sur les reponses fetch_failed"
```

---

## Task 4: Fonctions pures du marqueur (BO)

**Goal:** Poser, lire, effacer et regrouper un marqueur de cause dans le blob `data_crawling_dspi`, en fonctions pures testables sans base.

**Files:**
- Create: `D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php`
- Create: `D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/test_detect_failure_pure.php`

**Acceptance Criteria:**
- [ ] `detect_failure_apply(array $data, string $detail, string $now): array` pose la clé `detect_failure` avec `{detail, stage, cause, seen_count, first_seen_at, last_seen_at}`
- [ ] `seen_count` passe à 2 quand la cause est **identique**, revient à 1 quand elle change ; `first_seen_at` est préservé dans le premier cas, réinitialisé dans le second
- [ ] `detect_failure_read(array $data): ?array` et `detect_failure_strip(array $data): array`
- [ ] `detect_failure_split_detail(string $detail): array` sépare `"<stage>: <cause>"` ; un détail sans `": "` donne `stage='unknown'` et la chaîne entière en cause
- [ ] `detect_failure_group_key(array $marker): string` retourne le **stage** — axe de groupement stable, la cause pouvant contenir l'URL
- [ ] `detect_failure_matches_causes(array $marker, array $causes): bool` compare par **sous-chaîne** (insensible à la casse) et retourne **false sur une liste vide**
- [ ] Aucun `include`, aucune constante externe, aucune écriture : purement fonctionnel
- [ ] Toutes les fonctions sont gardées par `if (!function_exists(...))` (convention du dépôt)

**Verify:** `php -l fonctions_detect_failure_pure.php && php test_detect_failure_pure.php` → `No syntax errors` puis `OK`

**Steps:**

- [ ] **Step 1: Write the failing test**

```php
<?php
// test_detect_failure_pure.php
require_once __DIR__ . '/../../../../moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php';

function check($c, $l) { if (!$c) { fwrite(STDERR, "FAIL: $l\n"); exit(1); } }

// split_detail
check(detect_failure_split_detail('navigation: NS_ERROR_X') === ['stage' => 'navigation', 'cause' => 'NS_ERROR_X'], 'split simple');
check(detect_failure_split_detail('content: a: b') === ['stage' => 'content', 'cause' => 'a: b'], 'split garde le reste');
check(detect_failure_split_detail('sans separateur') === ['stage' => 'unknown', 'cause' => 'sans separateur'], 'split sans separateur');
check(detect_failure_split_detail('') === ['stage' => 'unknown', 'cause' => ''], 'split vide');

// apply : pose
$d = detect_failure_apply([], 'navigation: NS_ERROR_X', '2026-08-06 10:00:00');
check($d['detect_failure']['seen_count'] === 1, 'apply seen_count=1');
check($d['detect_failure']['stage'] === 'navigation', 'apply stage');
check($d['detect_failure']['first_seen_at'] === '2026-08-06 10:00:00', 'apply first_seen_at');

// apply : meme cause -> incremente, first_seen_at preserve
$d2 = detect_failure_apply($d, 'navigation: NS_ERROR_X', '2026-08-07 11:00:00');
check($d2['detect_failure']['seen_count'] === 2, 'apply incremente');
check($d2['detect_failure']['first_seen_at'] === '2026-08-06 10:00:00', 'first_seen_at preserve');
check($d2['detect_failure']['last_seen_at'] === '2026-08-07 11:00:00', 'last_seen_at maj');

// apply : cause differente -> reset
$d3 = detect_failure_apply($d2, 'content: Contenu vide ou trop court', '2026-08-08 12:00:00');
check($d3['detect_failure']['seen_count'] === 1, 'cause differente -> reset');
check($d3['detect_failure']['first_seen_at'] === '2026-08-08 12:00:00', 'first_seen_at reinitialise');

// apply preserve les autres cles du blob
$blob = ['homepage' => 'https://x.test', 'dropData' => 1];
$d4 = detect_failure_apply($blob, 'navigation: X', '2026-08-06 10:00:00');
check($d4['homepage'] === 'https://x.test' && $d4['dropData'] === 1, 'apply preserve le blob');

// read / strip
check(detect_failure_read($d4)['cause'] === 'X', 'read');
check(detect_failure_read([]) === null, 'read absent => null');
$s = detect_failure_strip($d4);
check(!isset($s['detect_failure']) && $s['homepage'] === 'https://x.test', 'strip cible la seule cle');

// group_key = stage
check(detect_failure_group_key(detect_failure_read($d4)) === 'navigation', 'group_key = stage');
check(detect_failure_group_key([]) === 'unknown', 'group_key defaut');

// matches_causes : sous-chaine, insensible a la casse, liste vide = false
$m = detect_failure_read(detect_failure_apply([], 'navigation: page.goto: NS_ERROR_UNKNOWN_HOST at https://x.test', '2026-08-06 10:00:00'));
check(detect_failure_matches_causes($m, []) === false, 'liste vide => aucun candidat');
check(detect_failure_matches_causes($m, ['NS_ERROR_UNKNOWN_HOST']) === true, 'match sous-chaine');
check(detect_failure_matches_causes($m, ['ns_error_unknown_host']) === true, 'match insensible a la casse');
check(detect_failure_matches_causes($m, ['NS_ERROR_PROXY']) === false, 'pas de match');

echo "OK\n";
```

- [ ] **Step 2: Run test to verify it fails**

Run: `php test_detect_failure_pure.php`
Expected: FAIL — `Failed opening required ... fonctions_detect_failure_pure.php`

- [ ] **Step 3: Write the pure functions**

```php
<?php
/**
 * Pure helpers pour le marqueur de cause d'échec de détection.
 * Aucun include, aucune DB, aucune constante externe — testable localement.
 *
 * Le marqueur vit dans la clé `detect_failure` du blob JSON data_crawling_dspi.
 * Aucune migration : le blob existe déjà et aucune clause d'exclusion de crawl ne le lit.
 * Précédents : relaunch_on_eligible (fonctions_relaunch_on_eligible_pure.php:19-34)
 * et maintenance_probe (fonctions_maintenance_domaine.php:152-184).
 */

if (!function_exists('detect_failure_split_detail')) {
    /** Pure: sépare "<stage>: <cause>" produit par le service de détection. */
    function detect_failure_split_detail(string $detail): array
    {
        $pos = strpos($detail, ': ');
        if ($pos === false) {
            return ['stage' => 'unknown', 'cause' => $detail];
        }
        return [
            'stage' => substr($detail, 0, $pos),
            'cause' => substr($detail, $pos + 2),
        ];
    }
}

if (!function_exists('detect_failure_apply')) {
    /**
     * Pure: pose ou met à jour le marqueur sur un blob décodé.
     * Même cause -> seen_count++ et first_seen_at préservé.
     * Cause différente -> seen_count remis à 1 (nouvelle observation).
     */
    function detect_failure_apply(array $data, string $detail, string $now): array
    {
        $parts = detect_failure_split_detail($detail);
        $previous = $data['detect_failure'] ?? null;
        $same = is_array($previous) && ($previous['cause'] ?? null) === $parts['cause'];

        $data['detect_failure'] = [
            'detail'        => $detail,
            'stage'         => $parts['stage'],
            'cause'         => $parts['cause'],
            'seen_count'    => $same ? ((int)($previous['seen_count'] ?? 1) + 1) : 1,
            'first_seen_at' => $same ? ($previous['first_seen_at'] ?? $now) : $now,
            'last_seen_at'  => $now,
        ];
        return $data;
    }

    /** Pure: lit le marqueur, ou null. */
    function detect_failure_read(array $data)
    {
        $m = $data['detect_failure'] ?? null;
        return is_array($m) ? $m : null;
    }

    /** Pure: retire le marqueur (à appeler dès que la détection réussit). */
    function detect_failure_strip(array $data): array
    {
        unset($data['detect_failure']);
        return $data;
    }
}

if (!function_exists('detect_failure_group_key')) {
    /**
     * Pure: axe de groupement pour l'aperçu = le STAGE.
     * La cause n'est pas groupable telle quelle : un message Playwright embarque
     * souvent l'URL, donc chaque cause serait unique.
     */
    function detect_failure_group_key(array $marker): string
    {
        $stage = $marker['stage'] ?? '';
        return $stage !== '' ? $stage : 'unknown';
    }
}

if (!function_exists('detect_failure_matches_causes')) {
    /**
     * Pure: la cause du marqueur contient-elle un des motifs listés ?
     * Comparaison par SOUS-CHAÎNE insensible à la casse (la cause embarque souvent
     * l'URL et un préfixe `page.goto: `, donc une égalité ne matcherait jamais).
     * Liste vide => false : c'est ce qui rend le script inerte à la livraison.
     */
    function detect_failure_matches_causes(array $marker, array $causes): bool
    {
        if (empty($causes)) {
            return false;
        }
        $haystack = strtolower((string)($marker['cause'] ?? ''));
        if ($haystack === '') {
            return false;
        }
        foreach ($causes as $needle) {
            $needle = strtolower(trim((string)$needle));
            if ($needle !== '' && strpos($haystack, $needle) !== false) {
                return true;
            }
        }
        return false;
    }
}
```

- [ ] **Step 4: Run tests**

Run: `php -l fonctions_detect_failure_pure.php && php test_detect_failure_pure.php`
Expected: `No syntax errors detected` puis `OK`

- [ ] **Step 5: Commit**

```bash
cd D:/DevHellopro/Marketplace
git add BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php \
        BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/test_detect_failure_pure.php
git commit -m "feat(crawling): fonctions pures du marqueur de cause d'echec de detection"
```

---

## Task 5: Pose et effacement du marqueur dans le rapport

**Goal:** Le script de traitement pose le marqueur sur un domaine indéterminé porteur d'une cause, et l'efface dès qu'il ressort FR ou jugé.

**Files:**
- Modify: `D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_traitement_crawling_rindra_BO.php` (includes `:20-23`, collecte `:196-203`, après le split `:237-241`)

**Acceptance Criteria:**
- [ ] `failure_detail` est collecté depuis le résultat de détection dans `$non_fr_domains` (`$result['failure_detail'] ?? ''`)
- [ ] Après le split, chaque **indéterminé** avec un `failure_detail` non vide voit son marqueur posé via `detect_failure_apply` ; chaque domaine **FR** ou **jugé** voit `detect_failure_strip` appliqué
- [ ] L'écriture passe par un read-modify-write du blob : décodage de `data_crawling_dspi`, application, ré-encodage, `UPDATE` par `retire_ia_update`
- [ ] Un blob JSON invalide est traité comme `[]` et ne fait pas échouer le script
- [ ] Le nombre d'écritures est journalisé (`logMsg`) et compté dans le rapport texte
- [ ] Le chemin FR → prospect (`:244-280`) n'est pas modifié
- [ ] La colonne `failure_detail` apparaît dans le tableau HTML des indéterminés
- [ ] `php -l` sans erreur

**Verify:** `php -l pct_traitement_crawling_rindra_BO.php && php test_parse_ids.php && php test_detect_failure_pure.php` → `No syntax errors` puis `OK` deux fois

**Steps:**

- [ ] **Step 1: Add the include**

Après la ligne `require_once` de `fonctions_retire_domaine.php` (`:22`) :

```php
require_once($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php'); // marqueur de cause d'échec (pur, sans DB)
```

- [ ] **Step 2: Collect the new field**

Dans la collecte des non-FR (`:196-203`) :

```php
                $non_fr_domains[] = [
                    'id'             => $domain_info['id'],
                    'domaine'        => $domain_info['domaine'],
                    'homepage'       => $domain_info['homepage'],
                    'method'         => $result['method'] ?? '',
                    'error'          => $result['error'] ?? '',
                    'failure_detail' => $result['failure_detail'] ?? '',
                ];
```

- [ ] **Step 3: Write the marker after the split**

Juste après le calcul de `$undetermined_by_method` :

```php
// Marqueur de cause : posé sur les indéterminés porteurs d'une cause, effacé dès que
// le domaine redevient interprétable (FR ou jugé). Sans l'effacement, un site réparé
// resterait candidat au retrait indéfiniment.
$marker_set = 0;
$marker_cleared = 0;
$now_marker = date('Y-m-d H:i:s');

function detect_failure_write_blob($id_domaine, callable $mutate): bool
{
    $id = intval($id_domaine);
    if ($id <= 0) { return false; }
    $sql = "SELECT data_crawling_dspi FROM domaine_scrapping_produit_ia
            WHERE id_domaine_scrapping_produit_ia = " . $id;
    $res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql);
    if (!$res) { return false; }
    $row = mysqli_fetch_assoc($res);
    if (!$row) { return false; }

    $data = json_decode((string)$row['data_crawling_dspi'], true);
    if (json_last_error() !== JSON_ERROR_NONE || !is_array($data)) { $data = []; }

    $before = json_encode($data);
    $data = $mutate($data);
    $after = json_encode($data);
    if ($after === $before) { return false; }

    return (bool)retire_ia_update(
        ['data_crawling_dspi' => $after],
        ['id_domaine_scrapping_produit_ia' => $id]
    );
}

foreach ($undetermined as $u) {
    $detail = (string)($u['failure_detail'] ?? '');
    if ($detail === '') { continue; }
    if (detect_failure_write_blob($u['id'], function (array $d) use ($detail, $now_marker) {
        return detect_failure_apply($d, $detail, $now_marker);
    })) { $marker_set++; }
}

foreach (array_merge($fr_domains, $non_fr_judged) as $interpretable) {
    if (detect_failure_write_blob($interpretable['id'], function (array $d) {
        return detect_failure_strip($d);
    })) { $marker_cleared++; }
}

logMsg("Marqueurs de cause — posés : {$marker_set} | effacés : {$marker_cleared}");
```

- [ ] **Step 4: Surface the cause in the HTML table**

Les deux tableaux partagent la même boucle `$nfr_sections`, mais la colonne n'a de sens
que pour les indéterminés (elle serait toujours vide chez les jugés). Ajouter donc un
drapeau par section plutôt qu'une colonne globale.

Dans la déclaration de `$nfr_sections`, ajouter `'show_cause' => false` sur la section
« Domaines Non-FR (jugés) » et `'show_cause' => true` sur « Domaines indéterminés ».

Puis, dans la boucle, l'en-tête devient conditionnel — juste après le `<th>` `Erreur` :

```php
    $show_cause = !empty($section['show_cause']);
    ...
    $html .= '<tr><th style="' . $style_th . '">ID</th><th style="' . $style_th . '">Domaine</th><th style="' . $style_th . '">Homepage</th><th style="' . $style_th . '">Méthode</th><th style="' . $style_th . '">Erreur</th>'
        . ($show_cause ? '<th style="' . $style_th . '">Cause</th>' : '')
        . '</tr>';
```

et la cellule, juste après celle de `error` :

```php
        if ($show_cause) {
            $html .= '<td style="' . $style_td . 'font-family:monospace;font-size:11px;">'
                . htmlspecialchars($nfr['failure_detail'] ?? '') . '</td>';
        }
```

- [ ] **Step 5: Verify**

Run: `php -l pct_traitement_crawling_rindra_BO.php && php test_parse_ids.php && php test_detect_failure_pure.php`
Expected: `No syntax errors detected`, `OK`, `OK`

- [ ] **Step 6: Commit**

```bash
cd D:/DevHellopro/Marketplace
git add BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_traitement_crawling_rindra_BO.php
git commit -m "feat(crawling): pose et efface le marqueur de cause dans le rapport"
```

---

## Task 6: Script de proposition de retrait

**Goal:** Un script qui liste les domaines candidats au retrait, groupe les causes observées, et n'écrit rien sans `--apply` — avec une liste de causes vide, donc inerte.

> **USER-ORDERED GATE — NON-SKIPPABLE.** This task was requested by the user in the current conversation. It MUST NOT be closed by walking around it, by declaring it "verified inline", or by substituting a cheaper check. Close only after every item in `acceptanceCriteria` has been re-validated independently, with output captured.

L'utilisateur a exigé : « on peut spécifier mais ne pas activer directement mais d'abord que je valide sur la liste ». L'inertie à la livraison (liste vide **et** flag `false`) est la raison d'être de cette tâche : ne pas remplir `DETECT_FAILURE_RETIRE_CAUSES`, ne pas passer `RETIRE_PROPOSAL_ENABLED` à `true`, même « pour tester ». Le test d'activation se fait en local en surchargeant la constante, jamais en modifiant la valeur livrée.

**Files:**
- Create: `D:/DevHellopro/Marketplace/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_propose_retire_domaine_mort_rindra_BO.php`

**Acceptance Criteria:**
- [ ] `DETECT_FAILURE_RETIRE_CAUSES = []` et `RETIRE_PROPOSAL_ENABLED = false`, tous deux `define`-gardés
- [ ] Sélection par `data_crawling_dspi LIKE '%detect_failure%'`, excluant `est_retire_dspi = 1`
- [ ] Partition en 4 seaux : **candidats**, **cause non listée**, **déjà retirés**, **blob illisible**
- [ ] **L'aperçu groupe les causes observées par stage** avec leur volume — utilisable liste vide
- [ ] Sans `--apply` (ni `?run=1`) : aperçu imprimé puis `exit(0)` **avant toute écriture**
- [ ] Avec `--apply` mais `RETIRE_PROPOSAL_ENABLED === false` : refus explicite, `exit(0)`, aucune écriture
- [ ] En application : `retire_domaine($id, 'domain_dead', 'auto', <cause>)`, et la condition d'origine est re-vérifiée juste avant (lecture fraîche du blob), un domaine ayant dérivé étant compté à part
- [ ] Mail récapitulatif via `envoyer_mail_scripts`
- [ ] Liste vide ⇒ **zéro candidat** même avec des marqueurs en base
- [ ] `php -l` sans erreur

**Verify:** `php -l pct_propose_retire_domaine_mort_rindra_BO.php` → `No syntax errors detected`. Puis, en aperçu sur la base réelle : `php pct_propose_retire_domaine_mort_rindra_BO.php` → affiche la répartition des causes et `0 candidat` (liste vide), sans aucune écriture.

**Steps:**

- [ ] **Step 1: Write the script**

```php
<?php
/**
 * Propose des domaines au retrait « domain_dead » d'après la cause d'échec de détection.
 *
 * DEUX TEMPS, comme pct_revive_retire_auto_sans_relance_rindra_BO.php :
 *   - sans --apply : APERÇU, aucune écriture ;
 *   - avec --apply (ou ?run=1) : applique, et seulement si RETIRE_PROPOSAL_ENABLED.
 *
 * INERTE À LA LIVRAISON : DETECT_FAILURE_RETIRE_CAUSES est vide, donc aucun domaine
 * n'est candidat. L'aperçu reste utile : il groupe les causes réellement observées,
 * ce qui est la base pour remplir la liste. Aucun libellé n'est deviné — cf. la spec
 * docs/superpowers/specs/2026-08-06-detection-failure-cause-and-retire-proposal-design.md
 *
 * Usage :
 *   php pct_propose_retire_domaine_mort_rindra_BO.php            # aperçu
 *   php pct_propose_retire_domaine_mort_rindra_BO.php --apply    # applique
 */

ini_set('memory_limit', '2048M');
ini_set('max_execution_time', '0');

$__is_web = (php_sapi_name() !== 'cli');
if ($__is_web) { header('Content-Type: text/plain; charset=UTF-8'); }

require_once($_SERVER['DOCUMENT_ROOT'] . '/include/connexion.php');
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "include/functions.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_hellopro.php');
require_once($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_retire_domaine.php');
require_once($_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php');

// Causes qui signifient « le domaine n'existe plus ». VIDE tant qu'aucun libellé réel
// n'a été observé : le remplir sur des suppositions est le mode d'échec qui a rendu
// trois listes de codes Chromium mortes dans deux services.
if (!defined('DETECT_FAILURE_RETIRE_CAUSES')) {
    define('DETECT_FAILURE_RETIRE_CAUSES', json_encode([]));
}
// Gate des écritures. Séparé d'AUTO_RETIRE_ENABLED, qui garde déjà 4 écritures réelles.
if (!defined('RETIRE_PROPOSAL_ENABLED')) {
    define('RETIRE_PROPOSAL_ENABLED', false);
}

$causes = json_decode(DETECT_FAILURE_RETIRE_CAUSES, true);
if (!is_array($causes)) { $causes = []; }

$apply = in_array('--apply', $argv ?? [], true) || ($__is_web && ($_GET['run'] ?? '') === '1');
$start = microtime(true);

$sql = "SELECT id_domaine_scrapping_produit_ia AS id, domaine_dspi, est_retire_dspi, data_crawling_dspi
        FROM domaine_scrapping_produit_ia
        WHERE data_crawling_dspi LIKE '%detect_failure%'";
$res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql)
    or die(hellopro_mysql_error($sql, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

$candidats = [];
$non_listees = [];
$deja_retires = [];
$illisibles = [];
$par_stage = [];
$par_cause = [];

while ($row = mysqli_fetch_assoc($res)) {
    $data = json_decode((string)$row['data_crawling_dspi'], true);
    if (json_last_error() !== JSON_ERROR_NONE || !is_array($data)) {
        $illisibles[] = $row;
        continue;
    }
    $marker = detect_failure_read($data);
    if ($marker === null) { continue; }

    $stage = detect_failure_group_key($marker);
    $par_stage[$stage] = ($par_stage[$stage] ?? 0) + 1;
    $cause_courte = mb_substr((string)($marker['cause'] ?? ''), 0, 80);
    $par_cause[$stage . ' | ' . $cause_courte] = ($par_cause[$stage . ' | ' . $cause_courte] ?? 0) + 1;

    $entry = ['id' => (int)$row['id'], 'domaine' => $row['domaine_dspi'], 'marker' => $marker];

    if ((int)$row['est_retire_dspi'] === 1) { $deja_retires[] = $entry; continue; }
    if (detect_failure_matches_causes($marker, $causes)) { $candidats[] = $entry; }
    else { $non_listees[] = $entry; }
}

arsort($par_stage);
arsort($par_cause);

echo "=== PROPOSITION DE RETRAIT « domain_dead » d'apres la cause de detection ===\n";
echo "Mode : " . ($apply ? "APPLICATION" : "APERCU (dry-run)") . "\n";
echo "Causes configurees : " . (empty($causes) ? "(AUCUNE - script inerte)" : implode(', ', $causes)) . "\n";
echo "Flag RETIRE_PROPOSAL_ENABLED : " . (RETIRE_PROPOSAL_ENABLED ? 'true' : 'false') . "\n\n";

echo "-- Repartition des causes observees (par stage) --\n";
foreach ($par_stage as $stage => $n) { printf("  %-12s %d\n", $stage, $n); }
echo "\n-- Causes distinctes (80 premiers caracteres) --\n";
foreach ($par_cause as $k => $n) { printf("  %4d  %s\n", $n, $k); }

echo "\n-- Seaux --\n";
echo "  candidats (cause listee, non retires) : " . count($candidats) . "\n";
echo "  cause NON listee                      : " . count($non_listees) . "\n";
echo "  deja retires                          : " . count($deja_retires) . "\n";
echo "  blob illisible                        : " . count($illisibles) . "\n";

if (!empty($candidats)) {
    echo "\n-- Detail des candidats --\n";
    foreach ($candidats as $c) {
        printf("  id=%d %s | vu %dx depuis %s | %s\n",
            $c['id'], $c['domaine'],
            (int)($c['marker']['seen_count'] ?? 1),
            (string)($c['marker']['first_seen_at'] ?? '?'),
            mb_substr((string)($c['marker']['detail'] ?? ''), 0, 120));
    }
}

if (!$apply) {
    $hint = $__is_web ? "ajouter ?run=1 a l'URL" : "relancer avec --apply";
    echo "\n[DRY-RUN] Aucune modification effectuee. Pour executer, {$hint}.\n";
    exit(0);
}

if (!RETIRE_PROPOSAL_ENABLED) {
    echo "\n[REFUS] RETIRE_PROPOSAL_ENABLED est false : aucune ecriture. "
       . "Activer le flag dans ce script apres avoir valide la liste.\n";
    exit(0);
}

$retires = 0; $derive = 0; $echecs = 0; $applied = [];
foreach ($candidats as $c) {
    // Re-verification sur lecture fraiche : le marqueur a pu changer depuis le calcul
    // de la liste (le blob est un read-modify-write sans verrou).
    $sql_v = "SELECT est_retire_dspi, data_crawling_dspi FROM domaine_scrapping_produit_ia
              WHERE id_domaine_scrapping_produit_ia = " . (int)$c['id'];
    $rv = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_v);
    $lv = $rv ? mysqli_fetch_assoc($rv) : null;
    if (!$lv) { $echecs++; continue; }
    if ((int)$lv['est_retire_dspi'] === 1) { $derive++; continue; }

    $dv = json_decode((string)$lv['data_crawling_dspi'], true);
    $mv = (json_last_error() === JSON_ERROR_NONE && is_array($dv)) ? detect_failure_read($dv) : null;
    if ($mv === null || !detect_failure_matches_causes($mv, $causes)) { $derive++; continue; }

    if (retire_domaine($c['id'], 'domain_dead', 'auto', (string)($mv['detail'] ?? ''))) {
        $retires++;
        $applied[] = "id={$c['id']} {$c['domaine']} retire (domain_dead)";
    } else {
        $echecs++;
    }
}

$duree = round(microtime(true) - $start, 2);
echo "\n[RESULTAT] retires : {$retires} | derive : {$derive} | echecs : {$echecs} | {$duree}s\n";
foreach ($applied as $l) { echo "  - {$l}\n"; }

$msg = "Proposition de retrait domain_dead<br>"
     . "Retires : {$retires}<br>Derive : {$derive}<br>Echecs : {$echecs}<br>"
     . "Candidats calcules : " . count($candidats) . "<br>"
     . "Causes configurees : " . htmlspecialchars(implode(', ', $causes)) . "<br>"
     . "Duree : {$duree}s";
envoyer_mail_scripts('[SCRIPT] Retrait domain_dead — ' . $retires . ' retire(s)', '', 'script@hellopro.fr', $msg, 1);
```

- [ ] **Step 2: Lint**

Run: `php -l pct_propose_retire_domaine_mort_rindra_BO.php`
Expected: `No syntax errors detected`

- [ ] **Step 3: Commit**

```bash
cd D:/DevHellopro/Marketplace
git add BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_propose_retire_domaine_mort_rindra_BO.php
git commit -m "feat(crawling): script de proposition de retrait domain_dead (inerte, liste vide)"
```

---

## Task 7: Documentation

**Goal:** Le champ, le marqueur et le script sont documentés là où un lecteur les cherchera, et les limites connues sont écrites.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md` (section des valeurs de `method` / réponses)
- Modify: `D:/DevHellopro/Marketplace/docs/pipelines/A-lancement-crawl-initial.md` (étape STEP2c et suivantes)

**Acceptance Criteria:**
- [ ] Le `CLAUDE.md` du service documente `failure_detail` : format `"<stage>: <cause>"`, les 5 stages (`navigation`, `content`, `proxy`, `runtime`, `browser`), le fait qu'il n'y a **aucune classification**, et qu'il n'est jamais caché pour `fetch_failed`
- [ ] La limite du dedup y est écrite (un follower reçoit `None`)
- [ ] Il est écrit que les trois listes de codes Chromium restent mortes et pourquoi
- [ ] La doc pipeline BO décrit le marqueur `detect_failure` et le script de proposition, avec `file:line`
- [ ] Aucune affirmation sur un libellé Gecko : la doc renvoie à la procédure de récolte (spec §6)

**Verify:** relecture — chaque affirmation ajoutée est soit vérifiable dans le code livré, soit explicitement marquée comme à vérifier.

**Steps:**

- [ ] **Step 1: Update the service CLAUDE.md**

Ajouter après le tableau « Invalid Page Rejection » :

```markdown
### `failure_detail` — cause brute d'un échec de fetch

Champ optionnel de `DetectionResponse`, format `"<stage>: <cause>"`. **Aucune
classification** : la chaîne est celle du moteur, première ligne, tronquée à 200
caractères.

| `stage` | Origine |
|---|---|
| `navigation` | `page.goto` a échoué (`scraper.py`, branche `nav_e`) |
| `content` | page récupérée mais contenu vide ou trop court |
| `proxy` | proxy absent ou format non reconnu (**la valeur du proxy n'est jamais publiée**) |
| `runtime` | Playwright absent du conteneur |
| `browser` | échec hors des points instrumentés (launch, new_context, new_page) |

Le `stage` vient du site d'appel dans le code, jamais d'une analyse du texte : aucun
libellé d'erreur n'est présupposé. Les trois listes de codes **Chromium**
(`_VARIANT_ELIGIBLE_ERRORS`, `_FATAL_ERRORS`, `_PERMANENT_NAV_ERRORS`) restent
volontairement mortes sur le moteur déployé (Camoufox/Firefox) : aucun libellé Gecko de
DNS introuvable n'est attesté, et les réparer sur une supposition est ce qui les a rendues
inopérantes. Procédure de récolte : spec `2026-08-06-...-design.md` §6.

**Limites** : sous `INFLIGHT_DEDUP_ENABLED`, seul le leader remplit le sink — un follower
sur la même URL reçoit `failure_detail=None`. Le champ n'est pas produit pour l'échec
réseau du repli homepage ni pour le saut de stub (hors périmètre). `fetch_failed` étant
dans `_NEVER_CACHE_METHODS`, la cause n'est jamais mise en cache.
```

- [ ] **Step 2: Update the BO pipeline doc**

Ajouter après l'étape STEP2c :

```markdown
11c. **STEP2d Marqueur de cause** — un indéterminé porteur de `failure_detail` reçoit un
marqueur `detect_failure` dans le blob `data_crawling_dspi` (cause, stage, `seen_count`,
dates) ; un domaine redevenu FR ou jugé le perd. Fonctions **pures** :
`fonctions_detect_failure_pure.php`. Aucune migration. Proposition de retrait :
`pct_propose_retire_domaine_mort_rindra_BO.php` — aperçu par défaut, `--apply`/`?run=1`
pour écrire, `DETECT_FAILURE_RETIRE_CAUSES` **vide** et `RETIRE_PROPOSAL_ENABLED=false`
à la livraison, donc inerte. L'aperçu groupe les causes observées par stage : c'est
l'instrument qui sert à remplir la liste.
```

- [ ] **Step 3: Commit (deux dépôts)**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/api-detection-langue-fr/CLAUDE.md
git commit -m "docs(detection): documente failure_detail et ses limites"

cd D:/DevHellopro/Marketplace
git add docs/pipelines/A-lancement-crawl-initial.md
git commit -m "docs(crawling): marqueur detect_failure et script de proposition"
```

---

## Déploiement

| Ordre | Cible | Action |
|---|---|---|
| 1 | `api-detection-langue-fr` | push + **rebuild Docker VM**. Aucune migration, aucun flag, aucun changement compose. |
| 2 | BO | MEP SFTP (skill `build-mep`) : 4 fichiers. Aucune migration. Livré inerte. |

B2 sans B1 n'a aucune cause à lire : l'ordre est contraignant.

**Après déploiement** — remplir la liste, en 4 étapes (spec §6) : lancer un lot, lire les
causes dans le rapport, lancer le script **en aperçu** pour les grouper, puis décider.
