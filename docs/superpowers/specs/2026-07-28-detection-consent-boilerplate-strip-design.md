# Design — strip consent boilerplate from NLP input (`data-nosnippet`)

**Date:** 2026-07-28
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO, no migration, no new env var.

## Problem

French sites are detected as non-French because an untouched English cookie-consent block dominates the text handed to fastText.

Live `/detect-debug` on DSPI id **39 · pesage88.com** (`https://pesage88.com/`):

| signal | value |
|---|---|
| `html lang` | `fr-FR` (French ✓) |
| content | unambiguously French — "passer au contenu principal", "Notre société", "Métrologie légale", "20 rue de Grandrupt 88190 Golbey Tel 03.29.82.36.29" |
| fastText | **`en` 0.667** / `fr` 0.125 |
| `french_signal` | **0.79** (French ✓) |
| verdict | `ok=false`, `method=nlp_not_confirmed`, Case 7 |

The `cleaned_text` (2585 chars) contains ~900 chars of English consent legalese: *"Privacy Overview This website uses cookies to improve your experience while you navigate through the website. Out of these, the cookies that are categorized as necessary… Necessary Necessary Toujours activé…"*.

### Root cause

`_remove_cookie_consent_elements` (`app/services/language_detector.py:319-373`) strips by CSS class/id substring. The site runs WebToffee "GDPR Cookie Consent":

```html
<div id="cookie-law-info-bar"    data-nosnippet="true">   <!-- stripped today: matches 'cookie-law' -->
<div id="cookie-law-info-again"  data-nosnippet="true">   <!-- stripped today -->
<div class="cli-modal" id="cliSettingsPopup" data-nosnippet="true" aria-hidden="true">  <!-- SURVIVES -->
```

The bar matches an existing selector; the **settings modal** (`cli-modal` / `cliSettingsPopup`, which holds the long English "Privacy Overview" text) matches nothing. All three elements, however, carry **`data-nosnippet`** — Google's standard "this is not page content" directive, which consent platforms set precisely because this text must not be indexed.

### Measured on the three domains analysed (raw HTML from `/detect-debug`)

| page | total page text | `[data-nosnippet]` | `[aria-hidden="true"]` |
|---|---|---|---|
| pesage88.com | 4228 | 3 el / **3173 chars** — all consent | 2 el / 2868 chars (same modal) |
| amt-lavage.com | 1112 | 0 | 8 el / **0 chars** (decorative icons) |
| sumca.fr | 7027 | 1 el / 0 chars (empty Axeptio mount) | 10 el / **1288 chars = real customer testimonials** (slick-slider clones) |

On pesage88 the consent block is **75% of all page text**. `data-nosnippet` produced **zero false positives**; where it is not consent it is an empty JS mount. `aria-hidden="true"` carries genuine content (sumca's testimonials) and is therefore **not** usable as a strip rule.

## Design

Append to the existing `cookie_consent_selectors` list in `_remove_cookie_consent_elements`. No new function, no new call site, no config:

```python
# data-nosnippet : directive standard « pas du contenu de page » — les CMP
# (WebToffee, Complianz…) la posent sur le bandeau ET la modale. Une seule
# règle couvre tous les vendeurs, au lieu d'une liste par plugin.
'[data-nosnippet]',
# Filets pour un vendeur qui n'exposerait pas data-nosnippet :
'[class*="cli-modal"]', '[id*="cliSettingsPopup"]',
# CookieYes : test par token de classe au lieu de substring (évite sticky-*).
'[id^="cky-"]',
# Après la boucle de sélecteurs :
def _has_cky_class(css_class) -> bool:
    tokens = css_class if isinstance(css_class, list) else (css_class or '').split()
    return any(t.startswith('cky-') for t in tokens)
for el in soup.find_all(class_=_has_cky_class):
    el.decompose()
```

**Deliberately NOT stripped:** `[aria-hidden="true"]` — carousel/slider clones are marked `aria-hidden` and hold real content (evidence above). A test asserts this stays.

### Why this shape

The cleaner is the shared input to both fastText and `french_signal`, so fixing the *input* corrects every downstream decision case at once — strictly better than special-casing verdicts. `data-nosnippet` is vendor-agnostic, so it ends the per-plugin selector chase rather than extending it by one more entry.

### Blast radius

`_remove_cookie_consent_elements` runs for every detection that analyses HTML. Verdicts may shift in both directions — intended. Over-stripping is the only hazard and the measurement above shows none for `data-nosnippet`. Cached Redis verdicts (30d ok / 7d nok) do **not** change until TTL expiry or `force_refresh=true`; re-measure through `/detect-debug` (bypasses cache) or `force_refresh`.

## Verification

- One test (`tests/test_consent_strip.py`): synthetic HTML with (a) a French body, (b) a `data-nosnippet` div of English consent legalese, (c) an `aria-hidden="true"` slider div of French text. Assert the consent English is absent from the cleaned text, the French body is present, and **the slider text is still present** (regression guard for the rejected `aria-hidden` variant). No fixture files, no new dependencies.
- Existing suite must stay green: `pytest tests/` (the pre-existing `tests/test_api.py` `app.main` collection error is unrelated and out of scope).
- Post-deploy: re-run `/detect-debug` on `https://pesage88.com/` — expect the "Privacy Overview" text gone from `debug.cleaning.cleaned_text_full`, `debug.nlp.lang` = `fr`, and `result.ok=true` (Case 1 path, no other change needed).

## Out of scope (next iterations, in this order)

1. **sumca.fr (id 90)** — `Case 2a` (`app/core/domain_fr.py:1316-1327`) returns `ok=false` on `nlp_strongly_contradicts` **before** the Case-6 alternative-confirmation loop, discarding a `reliability=high`, `validated=true` hreflang alt (`https://www.sumca.fr/fr/`). The homepage really is English; the site really has a French version, so `ok=false` is the wrong answer to "is FR **or has** a FR version".
2. **amt-lavage.com (id 5582)** — fastText `fr` at **0.723** vs `NLP_MIN_CONFIDENCE=0.75` → `soft_french`, no URL signal (`.com`), `lang="en-US"` (WordPress default, wrong) → falls through Cases 3/4 to Case 9 "No French indicators found", which is factually false (`soft_french=true`, `nlp.lang=fr`, `french_signal=0.577`). `domaine_francais.est_valide_df=1` from an earlier run — i.e. it flaps across the 0.75 boundary. The existing `Cas 8` lexical escape hatch (`french_signal > 0.3`, `domain_fr.py:1554`) is gated `if not nlp_available:` and so never fires here.

Both must be re-measured **after** this change lands, since it alters their NLP input. Also noted for later: `lang="en-US"` was wrong on 2 of 3 sites (WordPress theme default) — a weak negative signal worth down-weighting against a deliberate `fr-FR`.

Raw `/detect-debug` captures kept for before/after comparison: `scratchpad/dd_{39_pesage88,90_sumca,5582_amt}.json`.
