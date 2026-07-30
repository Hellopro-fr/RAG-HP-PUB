# Soft-French lexical corroboration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plainly French site whose NLP says `fr` just below the confidence threshold, with no URL or HTML signal to corroborate it, is accepted on the strength of its lexical French signal instead of falling to Case 9.

**Architecture:** Widen the gate of the existing last-resort `Cas 8` in `DomainFR.check_page_if_french` from "NLP unavailable" to "NLP unavailable **or** NLP says `fr` below threshold", reading the already-computed `french_signal` out of `nlp_result['details']` with the existing BeautifulSoup recompute as fallback. `Cas 8` sits last in the matrix, so widening it cannot preempt any other case. Two decision-label fixes in `_identify_decision_case` keep `debug.decision` truthful.

**Tech Stack:** Python 3.10, pytest + pytest-asyncio. Service `apps-microservices/api-detection-langue-fr`.

**User decisions (already made):**
- Approach **C** (widen `Cas 8`) over **A** (new case after Case 4, which would preempt Cases 5/6/7) and **B** (lower `NLP_MIN_CONFIDENCE`, rejected as global and merely relocating the flapping boundary).
- `french_signal > 0.3` kept as-is and `NLP_MIN_CONFIDENCE` untouched. The user was offered a stricter `0.5` floor for this path and chose to keep `0.3`; requiring fastText's `fr` is the agreed mitigation.
- The lexical signal corroborates, never overrides: a **contradicting** NLP must still never enter this branch (test 3 is that guard).

**Spec:** `docs/superpowers/specs/2026-07-28-detection-soft-french-lexical-corroboration-design.md`

**Prereq for local tests:** `common_utils` installed editable **from the main checkout** (`pip install -e D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils`) — installing from a worktree breaks when that worktree is removed. Run pytest from `apps-microservices/api-detection-langue-fr` with `$env:PYTHONIOENCODING="utf-8"` (French output crashes cp1252 stdout).

---

### Task 1: Widen `Cas 8` to accept soft-French corroborated by the lexical signal

**Goal:** `nlp_soft_french` + `french_signal > 0.3` yields `ok=true` with a distinguishable method, and `debug.decision` reports the real case.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` (`Cas 8` block ~1565-1590; `_identify_decision_case` labels ~1818-1821)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_soft_french_lexical.py` (create)

**Acceptance Criteria:**
- [ ] soft `fr` (0.723) + `french_signal` 0.577 + `.com` + `lang="en-US"` → `ok=True`, `method == 'nlp_soft_confirmed+french_lexical_signal'`, `confidence == nlp_confidence`
- [ ] soft `fr` + `french_signal` 0.20 → `ok=False`, `method == 'Check_nok_v2'` (below the floor — unchanged)
- [ ] NLP **contradicts** (`en` 0.95) + `french_signal` 0.9 → `ok=False` (lexical signal never overrides a contradicting NLP)
- [ ] NLP unavailable + `french_signal` 0.577 → `ok=True`, `method == 'french_lexical_signal'`, confidence `min(0.7, signal)` (pre-existing path byte-identical in behaviour)
- [ ] `debug.decision`: soft+corroborated → `Case 8b: …`; soft+below-floor → `Case 9: NLP soft French but no corroboration …`; NLP-unavailable+corroborated → `Case 8: Last resort …`
- [ ] `french_signal` is read from `nlp_result['details']` when present (no second BeautifulSoup parse); recompute only when absent
- [ ] The `len(visible_text) >= 50` guard still prevents a rescue on very short text

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_soft_french_lexical.py -v` → 7 passed; then `python -m pytest tests/ --ignore=tests/test_api.py -q` → `281 passed, 7 failed` (the 7 pre-existing `test_domain_fr.py` failures, unchanged)

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/api-detection-langue-fr/tests/test_soft_french_lexical.py`:

```python
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


def _stub_nlp(detector, monkeypatch, lang, confidence, french_signal):
    """Force le résultat NLP ET le french_signal exposé dans `details`.
    `lang=None` simule un NLP indisponible."""
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
    # Chemin NLP indisponible : le recalcul lexical doit trouver la valeur voulue.
    monkeypatch.setattr(
        detector.language_detector,
        "_compute_french_signal",
        lambda text: french_signal,
    )


@pytest.mark.asyncio
async def test_soft_french_corroborated_is_accepted(monkeypatch):
    """amt-lavage : fr 0.723 + signal 0.577 => accepté via le cas 8 élargi."""
    d = _detector()
    _stub_nlp(d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.577)

    res = await d.check_page_if_french(HTML, DetectionMode.COMPLETE)

    assert res.ok is True
    assert res.method == "nlp_soft_confirmed+french_lexical_signal"
    assert res.confidence == pytest.approx(0.723)


@pytest.mark.asyncio
async def test_soft_french_below_floor_still_rejected(monkeypatch):
    """Signal lexical <= 0.3 : pas de corroboration, comportement inchangé."""
    d = _detector()
    _stub_nlp(d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20)

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
    _stub_nlp(d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.577)

    dbg = await d.check_page_if_french_debug(HTML, DetectionMode.COMPLETE)

    assert dbg.result.ok is True
    assert dbg.debug.decision.startswith("Case 8b:")


@pytest.mark.asyncio
async def test_decision_label_soft_uncorroborated(monkeypatch):
    d = _detector()
    _stub_nlp(d, monkeypatch, lang="fr", confidence=0.723, french_signal=0.20)

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
```

Before running, read `check_page_if_french_debug`'s signature and adapt the three label tests' call if it needs extra arguments (e.g. `fetched_by='api'`). The assertions are the contract; the call shape is not.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && $env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_soft_french_lexical.py -v`
Expected RED: `test_soft_french_corroborated_is_accepted` fails (`ok` is False — Case 9 today) and `test_decision_label_soft_corroborated` fails. The other five should already pass (they assert unchanged behaviour). Report which failed and how.

- [ ] **Step 3: Widen the `Cas 8` gate**

In `app/core/domain_fr.py`, replace the whole `Cas 8` block (comment + `if not nlp_available:` through its `except`):

```python
        # Cas 8 : Dernier recours — signal lexical français
        # Uniquement si NLP n'est pas disponible (texte trop court, modèle absent).
        # Si NLP a détecté une autre langue, le signal lexical ne doit JAMAIS
        # outrepasser le NLP — sinon des sites allemands/espagnols/etc. avec
        # quelques mots français (navigation, footer) seraient faussement détectés.
        if not nlp_available:
            try:
                soup_check = BeautifulSoup(content, 'lxml')
                for el in soup_check(['script', 'style', 'meta', 'link', 'noscript']):
                    el.decompose()
                visible_text = soup_check.get_text(separator=' ', strip=True)

                if len(visible_text) >= 50:
                    french_signal = self.language_detector._compute_french_signal(visible_text)
                    logger.debug(f"Lexical French signal (last resort): {french_signal:.3f}")

                    if french_signal > 0.3:
                        return DetectionResponse(
                            ok=True,
                            url=url,
                            method='french_lexical_signal',
                            confidence=round(min(0.7, french_signal), 3),
                            alternative_urls=alternatives
                        )
            except Exception as e:
                logger.warning(f"Erreur signal lexical: {e}")
```

with:

```python
        # Cas 8 : Dernier recours — signal lexical français. Deux situations :
        #   - NLP indisponible (texte trop court, modèle absent) ;
        #   - NLP dit `fr` mais SOUS le seuil (soft) et aucun indicateur URL/HTML
        #     n'a pu le corroborer (cas amt-lavage.com : .com donc pas de signal
        #     URL, lang="en-US" erroné donc pas de signal HTML, fastText fr 0.723
        #     < 0.75, signal lexical 0.577 → tombait en cas 9).
        # Le signal lexical CORROBORE, il n'outrepasse JAMAIS le NLP : si le NLP a
        # détecté une AUTRE langue on n'entre pas ici, sinon des sites espagnols
        # ou italiens seraient faussement détectés (les mots partagés de/la/que/un
        # suffisent à atteindre 0.5-0.6 sans être français).
        # Ce cas est le DERNIER de la matrice : l'élargir ne peut préempter aucun
        # autre cas.
        if not nlp_available or nlp_soft_french:
            try:
                # Réutiliser le signal déjà calculé par le NLP : il porte sur le
                # texte nettoyé (bannières de consentement retirées) que fastText
                # a réellement analysé, alors que le recalcul ci-dessous utilise
                # un décapage plus grossier. Repli uniquement si absent.
                french_signal = None
                if nlp_result:
                    french_signal = (nlp_result.get('details') or {}).get('french_signal')

                if french_signal is None:
                    soup_check = BeautifulSoup(content, 'lxml')
                    for el in soup_check(['script', 'style', 'meta', 'link', 'noscript']):
                        el.decompose()
                    visible_text = soup_check.get_text(separator=' ', strip=True)

                    if len(visible_text) >= 50:
                        french_signal = self.language_detector._compute_french_signal(visible_text)

                if french_signal is not None:
                    logger.debug(f"Lexical French signal (last resort): {french_signal:.3f}")

                    if french_signal > 0.3:
                        if nlp_soft_french:
                            method = 'nlp_soft_confirmed+french_lexical_signal'
                            confidence = nlp_confidence
                        else:
                            method = 'french_lexical_signal'
                            confidence = round(min(0.7, french_signal), 3)

                        logger.info(
                            f"Signal lexical français {french_signal:.3f} retenu "
                            f"({method})"
                        )
                        return DetectionResponse(
                            ok=True,
                            url=url,
                            method=method,
                            confidence=confidence,
                            alternative_urls=alternatives
                        )
            except Exception as e:
                logger.warning(f"Erreur signal lexical: {e}")
```

- [ ] **Step 4: Fix the two decision labels**

In `_identify_decision_case`, replace:

```python
        if not nlp_available and 'french_lexical_signal' in method:
            return "Case 8: Last resort — French lexical signal (NLP unavailable)"

        return "Case 9: No French indicators found"
```

with:

```python
        if 'french_lexical_signal' in method:
            # Le cas 8 accepte désormais aussi un NLP `fr` sous le seuil corroboré
            # par le signal lexical : sans ce branchement, ce résultat ok=true
            # serait étiqueté « Case 9: No French indicators found ».
            if nlp_soft_french:
                return "Case 8b: NLP soft French corroborated by lexical signal"
            return "Case 8: Last resort — French lexical signal (NLP unavailable)"

        if nlp_soft_french:
            return (
                "Case 9: NLP soft French but no corroboration "
                "(no URL/HTML signal, lexical signal <= 0.3)"
            )

        return "Case 9: No French indicators found"
```

Confirm `nlp_soft_french` is already a parameter of `_identify_decision_case` before editing (it is used earlier in the same function).

- [ ] **Step 5: Run the tests + syntax check**

Run: `python -c "import ast; ast.parse(open('app/core/domain_fr.py',encoding='utf-8').read()); print('AST OK')"` → `AST OK`
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_soft_french_lexical.py -v` → 7 passed.

- [ ] **Step 6: Prove the safety guard bites**

Temporarily change the gate to `if not nlp_available or nlp_soft_french or nlp_contradicts_french:` (i.e. let a contradicting NLP in) and run `test_contradicting_nlp_is_never_overridden` → it MUST fail. Restore the gate exactly and re-run → 7 passed. Report both outcomes: this proves test 3 is a live guard on the spec's core safety argument, not decoration.

- [ ] **Step 7: Regression run**

Run: `python -m pytest tests/ --ignore=tests/test_api.py -q`
Expected: `281 passed, 7 failed` — the 7 being the pre-existing `tests/test_domain_fr.py` failures (fastText `.bin` absent locally, `ScrapeResult` tuple-unpack drift, missing-`await` in `test_detect_hreflang`/`test_detect_data_lang`). If anything else fails, STOP and report DONE_WITH_CONCERNS — do not edit unrelated tests.

- [ ] **Step 8: Commit**

Stage only the two files (explicit paths, never `git add -A`):
```
apps-microservices/api-detection-langue-fr/app/core/domain_fr.py
apps-microservices/api-detection-langue-fr/tests/test_soft_french_lexical.py
```
Bilingual EN+FR Conventional Commit via a temp message file written with the Write tool (NOT a bash heredoc — it trips a force-push blocker), then `git commit --file=<tmp>`. EN subject: `fix(detection): accept soft-French NLP corroborated by the lexical signal`

---

## Deploy (after the task, user-controlled)

- **RAG-HP-PUB** `features/poc`: `git push origin features/poc` + **rebuild the `api-detection-langue-fr` Docker image on the VM**. No BO, no migration, no env var. One rebuild carries this plus the two earlier detection fixes on this branch.

## Post-deploy verification

```bash
curl -s -X POST "https://api.hellopro.eu/detection_site_fr-service/api/v1/detect-debug" \
  -H "Content-Type: application/json" \
  -d '{"mode":"complete","url":"http://amt-lavage.com","use_nlp_detection":true,"include_full_content":false}' | jq \
  '{ok:.result.ok, method:.result.method, conf:.result.confidence,
     decision:.debug.decision, nlp:.debug.nlp.lang, nlp_conf:.debug.nlp.confidence,
     signal:.debug.nlp.details.french_signal}'
```

Expect `ok: true`, `method` containing `french_lexical_signal`, `decision` = `Case 8b: …`, with `nlp: "fr"`, `nlp_conf ≈ 0.72`, `signal ≈ 0.58`. `/detect-debug` bypasses the Redis cache; the stale `nok` persists 7 days, so run `/detect` with `force_refresh=true` afterwards to refresh the cached verdict the BO reads.

Compare against the pre-change capture in `scratchpad/dd_5582_amt.json`.
