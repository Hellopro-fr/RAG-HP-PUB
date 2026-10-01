# Design — soft-French NLP corroborated by the lexical signal

**Date:** 2026-07-28
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO, no migration, no threshold change to `NLP_MIN_CONFIDENCE`.

**Correction (2026-07-29, final whole-branch review):** the original text of this spec said "no new env var" — false after the fix wave below. The review found the safety argument broken in two independent places (see "Why this placement" and "Accepted risk"); the fix adds a second setting, `NLP_SOFT_MIN_CONFIDENCE` (default `0.5`), and a `method`-origin guard. See "The two guards" and "Rollback" further down.

## Problem

A plainly French site is reported non-French, and it flaps across the confidence boundary between runs.

Live `/detect-debug` on DSPI id **5582 · amt-lavage.com** (`http://amt-lavage.com`):

| signal | value |
|---|---|
| content | unmistakably French — *"Notre site internet est actuellement en travaux"*, *"Expert des systèmes de lavage auto & laveries automatiques"*, *"Siège Social 385 rue François Rabelais ZI Port L'Ardoise 30290 Laudun-L'Ardoise"*, *"Téléphone 04 66 82 55 62"*, `commercial@amt-lavage.fr` |
| `url_check` | `no_match` — `.com`, no `/fr/`, no `lang=fr` |
| `html_tags` | `lang="en-US"` → `is_french: false` (WordPress theme default, factually wrong) |
| `nlp` | **`lang=fr`, confidence 0.723** vs `NLP_MIN_CONFIDENCE=0.75` → `soft_french: true`, `confirms_french: false`, `contradicts_french: false` |
| `french_signal` | **0.577** |
| alternatives | none |
| verdict | `ok=false`, `method=Check_nok_v2`, `Case 9: No French indicators found` |

`domaine_francais.est_valide_df = 1` from an earlier run — the site has already been judged French once, so it is **flapping across the 0.75 boundary**, 0.027 short.

Re-baselined after the consent-strip fix (`178619bc`): cleaned text unchanged at 1109 chars, `french_signal` unchanged at 0.577 — this defect is independent of that change.

### Root cause

`soft_french` is only ever accepted when something else corroborates it, and for this shape nothing can:

- **Case 3** (`domain_fr.py:1396`) needs `url_indicates_french` — `.com`, so no.
- **Case 4** (`:1410`) needs `html_indicates_french` — `lang="en-US"`, so no.
- **Case 7** (`:1556`) needs `html_indicates_french or url_indicates_french` — neither, so it doesn't even produce its clearer message.
- **`Cas 8`** (`:1565-1590`) *is* the lexical-corroboration path (`french_signal > 0.3` → `ok=true`), and control does reach it — but it is gated **`if not nlp_available:`**, so a page whose NLP *is* available and softly says `fr` is turned away.

The verdict then falls to Case 9, whose label *"No French indicators found"* is factually false: `nlp.lang` is `fr`, `soft_french` is true, and the lexical signal is 0.577.

## Design

Widen `Cas 8`'s gate from *"NLP unavailable"* to *"NLP unavailable **or** NLP says `fr` below threshold"*. The lexical signal **corroborates** the NLP; it never overrides it.

```python
        if not nlp_available or nlp_soft_french:
```

Inside the block:
- **Reuse the already-computed signal.** `french_signal` is returned in `nlp_result['details']` by both NLP paths, so read `(nlp_result.get('details') or {}).get('french_signal')` first and only fall back to the existing BeautifulSoup recompute when it is absent (i.e. the NLP-unavailable case). This is cheaper (no second parse of a possibly-100KB page) **and** more accurate: the `details` value was computed on `clean_html_to_text` output — consent-stripped, exactly the text fastText scored — whereas the recompute uses a cruder strip that does **not** remove cookie banners.
- **Distinguish the outcome.** `method='nlp_soft_confirmed+french_lexical_signal'` when arriving via `nlp_soft_french`, keeping `method='french_lexical_signal'` for the NLP-unavailable path. Both tokens already exist in the service's method vocabulary, so no new value is introduced for consumers.
- **Confidence** = the NLP's own `nlp_confidence` (~0.72) on the soft path, matching Cases 3/4; the NLP-unavailable path keeps `round(min(0.7, french_signal), 3)`.
- **Threshold unchanged** at `french_signal > 0.3`, and `NLP_MIN_CONFIDENCE` is **not** touched.

Preserve the existing `len(visible_text) >= 50` behaviour on the recompute branch: when the text is too short, no signal is produced and no rescue happens.

### Why this placement, and why corroboration is required

`Cas 8` sits **last**, after Cases 1-7 have all declined, so widening it cannot preempt any existing case — the fall-through order does the safety work. Inserting a new case earlier in the matrix would, for example, let a soft-FR page with a validated FR alternative return `ok=true` on its own homepage instead of confirming the alternative (Case 6).

**`french_signal` is not safe alone.** It is `(exclusive×2 + shared×0.5) / words × 10` (`language_detector.py:288-317`). The shared set (`le, la, les, de, des, un, que, si, au, aux…`) overlaps heavily with Spanish and Italian. **Measured** (2026-07-29 review), not estimated: Spanish industrial prose **0.990** with ZERO exclusive-French words (19 shared hits on `de`/`la`/`le`/`un`), Spanish e-commerce **0.679**, Portuguese **0.407**, Italian **0.275**, English **0.000**, the target French page **1.000**. So `> 0.3` screens English but barely screens Spanish/Portuguese — worse than the original "0.5-0.6" estimate in this section, which undersold the exposure.

**Correction (2026-07-29 review) — `nlp_soft_french` does NOT guarantee the `fr` decision came from fastText.** The original text here claimed *"Requiring `nlp_lang == 'fr'` is what makes 0.3 safe here"* and *"A contradicting NLP still never reaches this branch"* — both false. At `domain_fr.py:1257-1272`, when fastText returns a non-`fr` label below 0.75, the langdetect+langid secondary detector runs and `nlp_result = secondary_result` replaces it **wholesale**; `nlp_lang`/`nlp_confidence`/`nlp_soft_french` are then computed from that substitute. The substitute's `fr` verdict can be **caused by `french_signal` itself**: `language_detector.py:589-592` adds `french_signal * 0.3` to the `fr` bucket whenever `french_signal > 0.5`. The widened `Cas 8` branch then reads that same number back out of `nlp_result['details']` and treats it as independent corroboration — circular. Concrete flip: langdetect `fr` (weight 0.4) vs langid `es` (weight 0.6) → without the bonus `fr`=0.4 loses to `es`=0.6; with it `fr`=0.697 wins at confidence 0.537 → soft French → would have been rescued. By contrast fastText (`language_detector.py:693-698`) sets `final_lang = main_lang` unconditionally and lets `french_signal` adjust only the confidence — a fastText label can never be moved by the lexical signal.

**The fix — two guards, not one.** `Cas 8`'s gate now requires `soft_from_fasttext` = `nlp_soft_french AND nlp_result['method'] == 'nlp_detection_fasttext' AND nlp_confidence >= NLP_SOFT_MIN_CONFIDENCE` (see "The two guards" below), instead of `nlp_soft_french` alone. `Cas 8`'s own comment in the code has been corrected to state this — no residual code comment still claims the single-check story.

### Mandatory sub-fix — the decision label would otherwise lie

`_identify_decision_case:1818` gates the Case-8 label on `not nlp_available and 'french_lexical_signal' in method`. With the widened gate, the soft path returns `ok=true` with a `french_lexical_signal` method **while NLP is available**, so that check fails and control falls to `:1821` `"Case 9: No French indicators found"` — a label directly contradicting `result.ok=true`. This is the same bug class just fixed for Case 2a, and the function already documents a prior instance of it. Two changes:

```python
        if 'french_lexical_signal' in method:
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

`nlp_soft_french` is already a parameter of that function.

**Correction (2026-07-29 review):** after the two guards above, a soft-FR rejection can now happen for three distinct reasons — no lexical corroboration (`french_signal <= 0.3`), the `fr` label came from the langdetect+langid substitute, or the confidence was under `NLP_SOFT_MIN_CONFIDENCE`. The Case-9 parenthetical shown here (`"lexical signal <= 0.3"`) asserted a cause that may not be the real one; it was generalized to `"(no URL/HTML signal, no lexical corroboration)"`, true in all three cases.

### Behaviour change

| Case | Before | After |
|---|---|---|
| NLP soft `fr`, no URL/HTML signal, `french_signal > 0.3` (amt-lavage: 0.577) | `ok=false` `Check_nok_v2`, "Case 9: No French indicators found" | **`ok=true`**, `method=nlp_soft_confirmed+french_lexical_signal`, confidence ≈ NLP's, "Case 8b" |
| NLP soft `fr`, no URL/HTML signal, `french_signal <= 0.3` | `ok=false` `Check_nok_v2` | `ok=false` `Check_nok_v2`, honest label ("soft French but no corroboration") |
| NLP contradicts (any confidence) | unchanged — never enters the branch | unchanged |
| NLP unavailable, `french_signal > 0.3` | `ok=true` `french_lexical_signal` | unchanged (same method, same confidence) |
| NLP soft `fr` **with** URL or HTML signal | already `ok=true` at Case 3/4 | unchanged (never reaches Cas 8) |
| NLP confirms `fr` (≥ 0.75) | already `ok=true` at Case 1 | unchanged |

**Accepted risk:** `0.3` becomes load-bearing for a new population (soft-FR pages). A Romance-language page that fastText genuinely (not via the langdetect+langid substitute — see the correction above and "The two guards" below) labels `fr` **and** scores 0.3-0.5 lexically would now pass.

**Correction (2026-07-29 review) — the confidence-based mitigation was false.** The original text claimed *"the returned confidence stays ~0.72 so downstream sees a deliberately weaker verdict"* — verified false: there are **zero** reads of `confidence` anywhere under `apps-microservices/crawler-service/`, and the only `['confidence']` reads in the BO are Google-reviews matching (unrelated). An 8b verdict is exactly as authoritative downstream as a fastText-0.99 one; no consumer treats it as weaker. The real mitigation is the two guards below, not the confidence value.

**Residual risk after both guards:** a Romance-language page where fastText itself (not the substitute) genuinely mislabels `fr` at ≥ `NLP_SOFT_MIN_CONFIDENCE` (0.5) **and** independently scores `french_signal > 0.3` can still pass. This is strictly narrower than before the fix wave (the circular-substitution path and the no-floor path are both closed), but it is not zero. No test population of real fastText `fr` mislabels on non-French Romance content was available to bound this further; treated as an accepted residual, not a defect to fix in this wave.

### The two guards (2026-07-29 fix wave)

`Cas 8`'s gate is `if not nlp_available or soft_from_fasttext:`, where:

```python
soft_from_fasttext = (
    nlp_soft_french
    and (nlp_result or {}).get('method') == 'nlp_detection_fasttext'
    and nlp_confidence >= settings.NLP_SOFT_MIN_CONFIDENCE
)
```

1. **`method == 'nlp_detection_fasttext'`** — the `fr` decision must come from fastText itself, never from the langdetect+langid substitute installed by the `:1257-1272` cross-check. Closes the circularity described above.
2. **`nlp_confidence >= NLP_SOFT_MIN_CONFIDENCE`** — new setting, default **`0.5`**, in `app/core/config.py` next to `NLP_MIN_CONFIDENCE`. Without it a bare fastText argmax `fr` at 0.18 would pass (the `:1257` cross-check only fires when the label is non-`fr`, so it never catches a low-confidence `fr`).

## Out of scope

- **`lang="en-US"` as a weak negative signal.** Wrong on 2 of the 3 sampled sites (WordPress theme default). Down-weighting a default `en-US` against a deliberate `fr-FR` is a separate, broader change.
- **`NLP_MIN_CONFIDENCE` (0.75).** Deliberately untouched: it is global, and moving it only relocates the flapping boundary.
- **The NLP-unavailable recompute not stripping cookie banners.** Pre-existing wrinkle, now documented in the code comment; the soft path avoids it by reading the cleaned-text value.
- Any change to Cases 1-7 or to the Case-6 alternative loop.

## Verification

- **Unit tests** (`tests/test_soft_french_lexical.py`), no network, stubbing the NLP result as the existing tests do:
  1. soft `fr` (0.723) + `french_signal` 0.577 + `.com` + `lang="en-US"` → `ok=True`, `method == 'nlp_soft_confirmed+french_lexical_signal'`, confidence ≈ 0.723.
  2. soft `fr` + `french_signal` 0.20 → `ok=False`, `method == 'Check_nok_v2'` (below the floor, unchanged).
  3. NLP contradicts (`en` 0.95) + high `french_signal` 0.9 → `ok=False` (the lexical signal must never override a contradicting NLP — this is the regression guard for the safety argument).
  4. NLP unavailable + `french_signal` 0.577 → `ok=True`, `method == 'french_lexical_signal'` (pre-existing path unchanged).
  5. Decision labels via `check_page_if_french_debug`: case 1 → `Case 8b: …`; case 2 → `Case 9: NLP soft French but no corroboration …`; case 4 → `Case 8: Last resort …`.
- Existing suite green. Baseline on this machine is `274 passed, 7 failed` — the 7 pre-existing `tests/test_domain_fr.py` failures (fastText `.bin` absent locally, `ScrapeResult` tuple-unpack drift, and a missing-`await` bug in `test_detect_hreflang`/`test_detect_data_lang`), plus a pre-existing `tests/test_api.py` collection error. All verified byte-identical on unchanged code.
- **Post-deploy:** `/detect-debug` on `http://amt-lavage.com` → expect `ok=true`, `method` containing `french_lexical_signal`, `decision` = `Case 8b: …`. `/detect-debug` bypasses the Redis cache; the stale `nok` otherwise persists 7 days, so use `force_refresh=true` on `/detect` to refresh the cached verdict and let the BO see it.

Raw pre-change capture for comparison: `scratchpad/dd_5582_amt.json`.

### Rollback (added 2026-07-29 fix wave)

There is no feature flag on this branch, and an `ok=true` verdict is cached **30 days** (`TTL_OK`, `app/core/domain_fr.py:43` and `:126`) and writes `est_valide_df=1` — a wrong rescue is sticky, not self-healing. Recipe if a bad soft-FR rescue reaches prod:

1. Redeploy the previous image (before this fix wave, or before the original `d5c896a1` widening, depending on how far back the bad rescue traces).
2. Purge the `fr_detect:*` Redis entries whose cached `method` contains `nlp_soft_confirmed+french_lexical_signal` (the only method token this feature introduces — a plain `Check_nok_v2`/`nlp_confirmed`/etc. entry was never touched by it).
3. Reset the matching `est_valide_df` rows in the BO back to their pre-rescue value (0, or whatever the last legitimate verdict was) so a stale `1` doesn't outlive the purged cache.
