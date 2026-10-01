# Case 2a validated-FR-alternative fall-through — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `.fr` site whose homepage is genuinely English but which serves a validated French version must be reported `ok=true` with the French alternative as its URL, instead of being rejected by Case 2a.

**Architecture:** Three surgical edits in `DomainFR.check_page_if_french` (`app/core/domain_fr.py`): hoist the pure `reliable_alternatives` filter above the decision matrix, gate Case 2a's rejection on "no validated alternative to examine", and make Case 2b the `else` branch so a strongly-contradicting homepage cannot fall into `tld_trusted`. Control then reaches the **existing, unmodified** Case-6 loop, which fetches the alternative, rejects challenge pages, NLP-confirms it, and returns the alternative's URL.

**Tech Stack:** Python 3.10, pytest + pytest-asyncio. Service `apps-microservices/api-detection-langue-fr`.

**User decisions (already made):**
- Approach **A** (fall through to Case 6) over **B** (trust the validated hreflang without fetching): `validated:true` only means the URL resolved, not that its content is French, so B would trade one wrong verdict for another.
- `validate_alternatives=false` callers (crawler-service) keep today's `ok=false` — consistent with that flag's contract; this fix benefits BO batches only.
- Accepted: when the declared alternative turns out NOT to be French, the verdict stays `ok=false` but the `method` string changes from `nlp_override_tld_fr` to Case 7's `nlp_not_confirmed`.

**Spec:** `docs/superpowers/specs/2026-07-28-detection-case2a-hreflang-alt-design.md`

**Prereq for local tests:** `common_utils` must be installed editable **from the main checkout** (`pip install -e D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils`) — installing it from a worktree breaks once that worktree is removed. Run pytest from `apps-microservices/api-detection-langue-fr`. On Windows set `PYTHONIOENCODING=utf-8` (French test output crashes cp1252 stdout).

---

### Task 1: Case 2a falls through to the Case-6 alternative confirmation

**Goal:** Case 2a rejects only when there is no validated alternative to examine; otherwise Case 6 decides on the alternative's own content.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` (~1286-1290 hoist; ~1312-1376 Case 2 restructure; ~1422 remove the now-duplicated filter line)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_case2a_alt_fallthrough.py` (create)

**Acceptance Criteria:**
- [ ] `.fr` + English homepage (`strongly_contradicts`) + validated hreflang alt whose content IS French → `ok=True`, `url` == the alternative, `method` contains `alternative_hreflang`
- [ ] Same but the alternative's content is English → `ok=False` (alternative was examined, no false positive)
- [ ] Same but `detect_alternative_languages` returns no validated alternative → `ok=False`, `method == 'nlp_override_tld_fr'` (unchanged behaviour)
- [ ] Same but `validate_alternatives=False` → `ok=False`, `method == 'nlp_override_tld_fr'` (unchanged behaviour)
- [ ] Sub-case 2b still returns `ok=True` for a `.fr` homepage that does NOT strongly contradict (e.g. `nlp_soft_french`) — no regression
- [ ] `reliable_alternatives` is computed exactly once; Case 6 still uses it
- [ ] Case 6's body is unmodified

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_case2a_alt_fallthrough.py -v` → 5 passed; then `python -m pytest tests/ --ignore=tests/test_api.py -q` → `269 passed, 7 failed` (the 7 pre-existing `test_domain_fr.py` failures, unchanged)

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/api-detection-langue-fr/tests/test_case2a_alt_fallthrough.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_case2a_alt_fallthrough.py -v`
Expected: `test_validated_french_alt_is_accepted` and `test_lying_alt_is_rejected` FAIL — the first asserts `ok is True` but Case 2a returns `ok=False`/`nlp_override_tld_fr`; the second currently "passes for the wrong reason" (Case 2a returns `ok=False` without ever examining the alternative), so treat only the first as the decisive red. The other three must already pass (they assert unchanged behaviour).

Report which tests failed and with what message before writing the fix.

- [ ] **Step 3: Hoist the `reliable_alternatives` filter**

In `app/core/domain_fr.py`, find the alternatives computation (~1286-1289):

```python
        # Étape 5 : Recherche liens alternatifs (mode COMPLETE uniquement)
        alternatives = []
        if mode == DetectionMode.COMPLETE:
            alternatives = await self.detect_alternative_languages(content)
```

Append the hoisted filter directly after it:

```python
        # Étape 5 : Recherche liens alternatifs (mode COMPLETE uniquement)
        alternatives = []
        if mode == DetectionMode.COMPLETE:
            alternatives = await self.detect_alternative_languages(content)

        # Filtre pur (aucune I/O) remonté ici : le cas 2a en a besoin pour
        # savoir s'il existe une alternative à examiner avant de rejeter.
        # Le cas 6 (plus bas) réutilise la même variable.
        reliable_alternatives = [a for a in alternatives if a.validated]
```

- [ ] **Step 4: Gate Case 2a and make Case 2b its `else`**

Find the Case 2 block (~1312-1376). It currently reads:

```python
        # Cas 2 : TLD .fr (signal FORT) — accepté sauf contradiction NLP forte
        if is_strong_url:
            # Sous-cas 2a : NLP contredit fortement (>0.9 confiance dans une autre langue)
            # → Rare mais possible (ex: site .fr en anglais)
            if nlp_strongly_contradicts:
                logger.info(
                    f"TLD .fr mais NLP détecte {nlp_lang} avec confiance {nlp_confidence:.3f} — rejet"
                )
                return DetectionResponse(
                    ok=False,
                    url=url,
                    method='nlp_override_tld_fr',
                    confidence=nlp_confidence,
                    alternative_urls=alternatives,
                    error=f"TLD .fr mais contenu détecté comme {nlp_lang} ({nlp_confidence:.0%})"
                )
            
            # Sous-cas 2b : NLP soft-confirme, ou NLP indisponible, ou NLP faiblement contredit
            # → Le TLD .fr est un signal suffisamment fort pour valider
```

Replace exactly that portion with (note: the `if nlp_strongly_contradicts:` body gains a guard, and everything from "Sous-cas 2b" onward moves under an `else:`):

```python
        # Cas 2 : TLD .fr (signal FORT) — accepté sauf contradiction NLP forte
        if is_strong_url:
            # Sous-cas 2a : NLP contredit fortement (>0.9 confiance dans une autre langue)
            # → Rare mais possible (ex: site .fr en anglais)
            if nlp_strongly_contradicts:
                # …mais si la page DÉCLARE une version française validée, ne pas
                # trancher ici : laisser le cas 6 (plus bas) récupérer cette
                # alternative et décider sur SON contenu. Sans ce garde-fou, un
                # site .fr à accueil anglais + /fr/ validé était rejeté alors
                # qu'il a bien une version française (cas réel sumca.fr).
                # Si validate_alternatives est off, le cas 6 est sauté : on garde
                # le rejet immédiat et son message plus clair.
                if not (self.validate_alternatives and reliable_alternatives):
                    logger.info(
                        f"TLD .fr mais NLP détecte {nlp_lang} avec confiance {nlp_confidence:.3f} — rejet"
                    )
                    return DetectionResponse(
                        ok=False,
                        url=url,
                        method='nlp_override_tld_fr',
                        confidence=nlp_confidence,
                        alternative_urls=alternatives,
                        error=f"TLD .fr mais contenu détecté comme {nlp_lang} ({nlp_confidence:.0%})"
                    )
                logger.info(
                    f"TLD .fr mais NLP détecte {nlp_lang} ({nlp_confidence:.3f}) — "
                    f"{len(reliable_alternatives)} alternative(s) validée(s) à vérifier (cas 6)"
                )
            else:
                # Sous-cas 2b : NLP soft-confirme, ou NLP indisponible, ou NLP faiblement contredit
                # → Le TLD .fr est un signal suffisamment fort pour valider
```

Then **indent the whole remaining body of sub-case 2b by one level** (4 spaces) so it sits inside that new `else:` — from the `# Guard : si NLP est indisponible PARCE QUE…` comment down to and including the `return DetectionResponse(...)` that ends sub-case 2b (the one returning `method='+'.join(methods)` with `confidence=confidence`). Nothing else in the function changes.

- [ ] **Step 5: Remove the now-duplicated filter line in Case 6**

Find (~1422, just under the `# Cas 6 : …` comment):

```python
        reliable_alternatives = [a for a in alternatives if a.validated]
        if self.validate_alternatives and reliable_alternatives:
```

Delete the first of those two lines only (the variable is now computed at Step 3):

```python
        if self.validate_alternatives and reliable_alternatives:
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_case2a_alt_fallthrough.py -v`
Expected: `5 passed`.

- [ ] **Step 7: Confirm the guard bites**

Temporarily revert Step 4's guard (make Case 2a return unconditionally again) and re-run: `test_validated_french_alt_is_accepted` MUST fail. Restore Step 4 and re-run green. Report both observations — this proves the test is a real guard, not a tautology.

- [ ] **Step 8: Regression run**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/ --ignore=tests/test_api.py -q`
Expected: `269 passed, 7 failed` — the 7 being the pre-existing `tests/test_domain_fr.py` failures (fastText `.bin` absent locally, `ScrapeResult` tuple-unpack drift, async harness drift), byte-identical to the baseline. If any OTHER test fails, STOP and report DONE_WITH_CONCERNS — do not edit unrelated tests.

- [ ] **Step 9: Commit**

Stage only the two files (explicit paths, never `git add -A`):
```
apps-microservices/api-detection-langue-fr/app/core/domain_fr.py
apps-microservices/api-detection-langue-fr/tests/test_case2a_alt_fallthrough.py
```
Bilingual EN+FR Conventional Commit via a temp message file written with the Write tool (NOT a bash heredoc — it trips a force-push blocker), then `git commit --file=<tmp>`. EN subject: `fix(detection): Case 2a falls through to validated FR alternative`

---

## Deploy (after the task, user-controlled)

- **RAG-HP-PUB** `features/poc`: `git push origin features/poc` + **rebuild the `api-detection-langue-fr` Docker image on the VM**. No BO, no migration, no env var.

## Post-deploy verification

```bash
curl -s -X POST "https://api.hellopro.eu/detection_site_fr-service/api/v1/detect-debug" \
  -H "Content-Type: application/json" \
  -d '{"mode":"complete","url":"https://www.sumca.fr/","use_nlp_detection":true,"include_full_content":false}' | jq \
  '{ok:.result.ok, url:.result.url, method:.result.method, decision:.debug.decision,
     alts:[.debug.alternatives.candidates[]?|{url,method,reliability,validated}]}'
```

Expect `ok: true`, `url: "https://www.sumca.fr/fr/"`, `method` containing `alternative_hreflang`, and `decision` no longer `Case 2a`. `/detect-debug` bypasses the Redis cache; a cached `nok` otherwise persists 7 days, so use `force_refresh=true` on `/detect` if you want the cached verdict refreshed too.

Compare against the pre-change capture in `scratchpad/dd_90_sumca.json`.
