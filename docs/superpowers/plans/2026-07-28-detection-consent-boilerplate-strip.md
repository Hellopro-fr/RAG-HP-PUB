# Consent-boilerplate strip (`data-nosnippet`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop untouched English cookie-consent text from flipping French sites to non-French, by stripping `[data-nosnippet]` (plus two vendor fallbacks) before the text reaches fastText.

**Architecture:** One selector-list addition inside the existing `LanguageDetector._remove_cookie_consent_elements`, which `clean_html_to_text` already calls at cleaning step 3. No new function, no new call site, no config, no env var. Fixing the shared cleaner input corrects every downstream decision case at once.

**Tech Stack:** Python 3.10, BeautifulSoup4 + lxml, pytest. Service `apps-microservices/api-detection-langue-fr`.

**User decisions (already made):**
- Approach **B**: `[data-nosnippet]` + `cli-modal`/`cliSettingsPopup`/`cky-*` vendor fallbacks (A alone was the fix; B's extras are free insurance for the one unverified vendor).
- `[aria-hidden="true"]` **rejected** on measured evidence (sumca.fr slick-slider clones hold 1288 chars of real testimonials) — a test locks this in.
- sumca.fr Case-2a hreflang and amt-lavage.com `soft_french` 0.723 are **out of scope**, to be re-measured after this lands.

**Spec:** `docs/superpowers/specs/2026-07-28-detection-consent-boilerplate-strip-design.md`

**Prereq for local tests:** `pip install -e libs/common-utils` from the repo root (already installed on this machine), then run from `apps-microservices/api-detection-langue-fr`.

---

### Task 1: Strip `[data-nosnippet]` in the consent cleaner

**Goal:** Consent banners/modals carrying `data-nosnippet` (and WebToffee/CookieYes markup) are removed from the text handed to fastText, while `aria-hidden` slider content is preserved.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/language_detector.py:369-371` (append to `cookie_consent_selectors`, inside `_remove_cookie_consent_elements`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_consent_strip.py` (create)

**Acceptance Criteria:**
- [ ] Text inside a `data-nosnippet` element is absent from `clean_html_to_text` output
- [ ] Text inside `.cli-modal` / `#cliSettingsPopup` is absent (WebToffee, even without `data-nosnippet`)
- [ ] Text inside a CookieYes container (`#cky-*`, `.cky-consent*`) is absent, while `sticky-*` content survives
- [ ] Ordinary French body text is still present
- [ ] Text inside an `aria-hidden="true"` element is **still present** (regression guard for the rejected variant)
- [ ] Existing suite unaffected

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_consent_strip.py -v` → 1 passed; then `python -m pytest tests/test_domain_fr.py tests/test_batch_core_refactor.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/api-detection-langue-fr/tests/test_consent_strip.py`:

```python
"""Le boilerplate de consentement ne doit jamais atteindre le NLP.

Cas réel : pesage88.com (DSPI 39) — la modale WebToffee « Privacy Overview »
(anglaise) pesait 75% du texte de la page et faisait basculer fastText sur
`en` alors que le site est français. Voir spec 2026-07-28.
"""
from app.services.language_detector import LanguageDetector

# Anglais dans 3 conteneurs de consentement + français dans le body
# + français dans un slider aria-hidden (qui DOIT survivre).
HTML = """
<html lang="fr-FR"><body>
  <div id="content">
    Nos produits balances industrielles et bascules au sol pour la region Lorraine.
  </div>

  <div id="cookie-law-info-bar" data-nosnippet="true">
    WESHOULDSTRIP_NOSNIPPET We use cookies on our website to give you the most
    relevant experience by remembering your preferences and repeat visits.
  </div>

  <div class="cli-modal" id="cliSettingsPopup" aria-hidden="true">
    WESHOULDSTRIP_CLIMODAL Privacy Overview This website uses cookies to improve
    your experience while you navigate through the website.
  </div>

  <div class="cky-consent-container">
    WESHOULDSTRIP_CKY This website uses cookies to improve your experience.
  </div>

  <div class="slick-slide" aria-hidden="true">
    WEMUSTKEEP_SLIDER Merci a l equipe pour la reactivite et la qualite du travail.
  </div>

  <div class="sticky-header" id="sticky-nav">
    WEMUSTKEEP_STICKY Accueil Nos produits Contact
  </div>
</body></html>
"""


def test_consent_boilerplate_stripped_but_hidden_slider_kept():
    text = LanguageDetector().clean_html_to_text(HTML)
    assert text is not None

    # Consentement retiré (data-nosnippet + filets vendeurs)
    assert "WESHOULDSTRIP_NOSNIPPET" not in text
    assert "WESHOULDSTRIP_CLIMODAL" not in text
    assert "WESHOULDSTRIP_CKY" not in text
    assert "Privacy Overview" not in text

    # Contenu réel conservé
    assert "balances industrielles" in text
    # aria-hidden n'est PAS un critère de suppression : les clones de carrousel
    # (slick-slide) portent du vrai contenu — cf. sumca.fr, 1288 caractères de
    # témoignages. Ce garde-fou verrouille le refus de l'option écartée.
    assert "WEMUSTKEEP_SLIDER" in text
    # `cky-` en substring attraperait `sticky-header`/`sticky-nav` : la nav
    # collante est du vrai contenu et doit survivre.
    assert "WEMUSTKEEP_STICKY" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_consent_strip.py -v`
Expected: FAIL — `assert "WESHOULDSTRIP_NOSNIPPET" not in text` (the `data-nosnippet` bar text survives today; `cli-modal` and `cky-` too). Note `#cookie-law-info-bar` alone already matches the existing `cookie-law` selector, so the decisive first failure is whichever assertion runs first among the three strip markers — all three must end up passing.

- [ ] **Step 3: Add the selectors**

In `app/services/language_detector.py`, inside `_remove_cookie_consent_elements`, the list currently ends:

```python
            '[class*="cookie-law"]', '[id*="cookie-law"]',
            '[class*="cookielaw"]', '[id*="cookielaw"]',
        ]
```

Replace that tail with:

```python
            '[class*="cookie-law"]', '[id*="cookie-law"]',
            '[class*="cookielaw"]', '[id*="cookielaw"]',
            # data-nosnippet : directive standard « pas du contenu de page » que
            # les CMP posent sur le bandeau ET la modale de réglages. Une seule
            # règle agnostique du vendeur, au lieu d'un sélecteur par plugin.
            # Cas pesage88.com : la modale WebToffee (cli-modal) échappait à
            # tous les sélecteurs class/id et pesait 75% du texte de la page,
            # basculant fastText sur `en`. Mesuré sur 3 pages : 0 faux positif
            # (là où ce n'est pas du consentement, c'est un mount JS vide).
            # NB : `aria-hidden="true"` a été ÉCARTÉ — les clones de carrousel
            # (slick-slide) le portent et contiennent du vrai contenu.
            '[data-nosnippet]',
            # Filets si un vendeur n'expose pas data-nosnippet :
            '[class*="cli-modal"]', '[id*="cliSettingsPopup"]',
            # CookieYes : test par token de classe au lieu de substring (évite sticky-*).
            '[id^="cky-"]',
        ]
        # ... après la boucle de sélecteurs :
        def _has_cky_class(css_class) -> bool:
            tokens = css_class if isinstance(css_class, list) else (css_class or '').split()
            return any(t.startswith('cky-') for t in tokens)
        for el in soup.find_all(class_=_has_cky_class):
            el.decompose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_consent_strip.py -v`
Expected: `1 passed`

- [ ] **Step 5: Check for regressions in the existing suite**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_domain_fr.py tests/test_batch_core_refactor.py tests/test_admission_carveout.py -v`
Expected: all pass, 0 failures. (`tests/test_api.py` has a pre-existing, unrelated `ModuleNotFoundError: No module named 'app.main'` collection error — leave it alone.)

If a pre-existing test breaks, STOP and report it rather than editing that test.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/language_detector.py \
        apps-microservices/api-detection-langue-fr/tests/test_consent_strip.py
git commit -m "fix(detection): strip [data-nosnippet] consent boilerplate before NLP"
```
(Commit message body bilingual EN+FR per repo convention.)

---

## Deploy (after the task, user-controlled)

- **RAG-HP-PUB** `features/poc`: `git push origin features/poc` + **rebuild the `api-detection-langue-fr` Docker image on the VM**. No BO, no migration, no env var.

## Post-deploy verification

Re-run the captured case and compare against the pre-change snapshot in `scratchpad/dd_39_pesage88.json`:

```bash
curl -s -X POST "https://api.hellopro.eu/detection_site_fr-service/api/v1/detect-debug" \
  -H "Content-Type: application/json" \
  -d '{"mode":"complete","url":"https://pesage88.com/","use_nlp_detection":true,"include_full_content":true}' | jq \
  '{ok:.result.ok, method:.result.method, nlp:.debug.nlp.lang, conf:.debug.nlp.confidence,
     signal:.debug.nlp.details.french_signal, cleaned:.debug.cleaning.cleaned_text_length,
     privacy_leak:(.debug.cleaning.cleaned_text_full|test("Privacy Overview"))}'
```

Expect: `privacy_leak: false`, `cleaned` well below the pre-change 2585, `nlp: "fr"`, `ok: true` (Case 1 — no decision-matrix change needed). `/detect-debug` bypasses the Redis cache, so no `force_refresh` juggling.

Then re-run the same call for `https://www.sumca.fr/` and `http://amt-lavage.com` — not to fix them (out of scope) but to re-baseline the two deferred items on the new cleaner input before touching thresholds or Case 2a.
