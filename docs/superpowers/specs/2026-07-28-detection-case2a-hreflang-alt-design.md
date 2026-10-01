# Design — Case 2a must not discard a validated French alternative

**Date:** 2026-07-28
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO, no migration, no new env var.

## Problem

A `.fr` site whose homepage is genuinely English, but which **declares and serves a French version**, is reported as non-French. The BO's question is "is this site French **or does it have** a French version", so `ok=false` is the wrong answer.

Live `/detect-debug` on DSPI id **90 · sumca.fr** (`https://www.sumca.fr/`):

| signal | value |
|---|---|
| `url_check` | `direct_match`, `is_strong_url: true` (`.fr` TLD) |
| `html_tags` | `lang="en-US"` → `is_french: false` |
| `nlp` | fastText **`en` 0.916**, `french_signal 0.0`, `strongly_contradicts: true` |
| `alternatives` | **1 candidate: `https://www.sumca.fr/fr/`, method `hreflang`, reliability `high`, `validated: true`** |
| verdict | `ok=false`, `method=nlp_override_tld_fr`, `Case 2a: TLD .fr but NLP strongly contradicts` |

The NLP verdict on the homepage is **correct** — that page is English. The defect is that the validated French alternative is discarded unexamined.

### Root cause

`domain_fr.py:1312-1327` — inside `if is_strong_url:`, sub-case 2a returns immediately on `nlp_strongly_contradicts`:

```python
if is_strong_url:
    if nlp_strongly_contradicts:
        return DetectionResponse(ok=False, url=url, method='nlp_override_tld_fr',
                                 confidence=nlp_confidence, alternative_urls=alternatives, ...)
```

The Case-6 alternative-confirmation loop — which fetches each validated alternative, rejects challenge pages, and NLP-confirms it — lives further down at **1419-1510**. Case 2a returns before ever reaching it.

**Case 2a is the only early exit past Case 6.** Verified by reading the full matrix:
- `alternatives` is computed at **1289**, *before* the decision matrix (which is why Case 2a can already pass `alternative_urls=alternatives`).
- `reliable_alternatives = [a for a in alternatives if a.validated]` is a pure one-line filter at **1422** — no I/O.
- Cases 3 (1379), 4 (1393) and 5 (1403) sit between 2a and Case 6 but cannot fire for this shape: 3 and 4 both require `nlp_soft_french`, 5 requires `not nlp_available`; sumca is `en @ 0.916` with NLP available.
- Case 7 (1540) sits *after* Case 6, so it already benefits from alternative consideration.

Corroborating evidence that 2a is the anomaly: the same site shape on a **`.com`** homepage (English homepage + validated `/fr/`) already flows into Case 6 today and returns `ok=true`. Only the strong `.fr` URL signal triggers the early return.

## Design

Reject in Case 2a **only when there is no validated alternative to examine**; otherwise let control reach the existing Case-6 confirmation loop, which decides on the alternative's own content.

1. **Hoist the filter.** Move `reliable_alternatives = [a for a in alternatives if a.validated]` from 1422 up to just after `alternatives` is computed (after 1289). It is a pure list comprehension over already-computed data — no behavioural change, no I/O, and Case 6 keeps using the same variable.

2. **Gate Case 2a's rejection.** Reject only when there is nothing to check:
   ```python
   if nlp_strongly_contradicts:
       if not (self.validate_alternatives and reliable_alternatives):
           return DetectionResponse(ok=False, url=url, method='nlp_override_tld_fr', ...)
       # sinon : ne pas trancher ici — le cas 6 (ci-dessous) va chercher le
       # contenu de l'alternative validée et décide sur SON contenu.
   else:
       ... existing sub-case 2b (unchanged) ...
   ```
   The `self.validate_alternatives` term matters: when that flag is off, Case 6 is skipped entirely, so falling through would land on Case 7/9 instead of returning the clearer `nlp_override_tld_fr`. Keeping the early return in that configuration preserves today's message.

3. **Guard Case 2b.** Sub-case 2b currently returns `ok=true` for every non-2a path under `is_strong_url` (including `nlp_weak_disagree`). It must become the `else` of the `nlp_strongly_contradicts` test so a strongly-contradicting homepage can never fall into `tld_trusted` on its way to Case 6.

Case 6 itself is **not modified** — it already returns `ok=true` with `url=alt_final_url or alt_candidate.url`, `method='alternative_hreflang+…+nlp_confirmed'`, and the alt's own confidence, which is exactly the FR URL the BO should store as `homepage_df` and crawl.

### Why fall through rather than trust the declaration

`validated: true` on an hreflang candidate means the URL **resolved**, not that its content is French — this service marks hreflang as a trusted *declaration* and validates reachability. A site declaring `/fr/` that actually serves English would become a false positive. Falling through makes the `ok=true` earned: fetched, challenge-checked, NLP-confirmed. The cost is one alternative fetch on an uncommon branch (`.fr` + strongly-contradicting homepage + a validated alternative), already bounded by Case 6's `asyncio.wait_for(fetch_html(...), timeout=120)`.

### Behaviour change

| Case | Before | After |
|---|---|---|
| `.fr`, English homepage, validated FR alt that is really French | `ok=false` `nlp_override_tld_fr` | **`ok=true`**, `url=` the FR alt, `method=alternative_hreflang+…+nlp_confirmed` |
| `.fr`, English homepage, validated alt that is NOT French | `ok=false` `nlp_override_tld_fr` | `ok=false` via Case 7/9 (alt examined and rejected) — different method string, same verdict |
| `.fr`, English homepage, no validated alt | `ok=false` `nlp_override_tld_fr` | unchanged |
| `validate_alternatives=false` (crawler-service) | `ok=false` `nlp_override_tld_fr` | unchanged |
| Everything not `is_strong_url` + strongly-contradicting | unchanged | unchanged |

Row 2 is a deliberate trade: the verdict is identical, only the reported `method` differs (and the diagnosis improves, since the alternative was actually examined).

**Known limitation:** `validate_alternatives=false` callers keep today's answer. That is consistent with the flag's documented contract (it exists to remove alt-validation browser work for crawler-service) — so this fix benefits BO batches only. Not a regression.

## Out of scope

- **amt-lavage.com (id 5582)** — `soft_french` 0.723 vs `NLP_MIN_CONFIDENCE=0.75` falling to Case 9. Separate iteration; re-baselined and unaffected by the consent-strip change (cleaned text 1109 chars unchanged, `french_signal 0.577`).
- `lang="en-US"` as a weak negative signal (WordPress theme default, wrong on 2 of 3 sampled sites).
- Any change to Case 6's internals, to the `validate_alternatives` contract, or to the `NLP_MIN_CONFIDENCE` threshold.

## Verification

- **Unit test** (`tests/test_case2a_alt_fallthrough.py`), no network: build a `DomainFR` on a `.fr` URL with English homepage content that yields `strongly_contradicts`, stub `detect_alternative_languages` to return one `validated=True` hreflang candidate, and stub `fetch_html` to return French content for that alternative. Assert `ok=True`, the returned `url` is the alternative, and `method` contains `alternative_hreflang`. Second case: same setup but the alternative's content is English → assert `ok=False` (fell through, alternative examined, no false positive). Third case: no validated alternative → assert `ok=False` and `method == 'nlp_override_tld_fr'` (unchanged behaviour). Fourth: `validate_alternatives=False` → `method == 'nlp_override_tld_fr'`.
- Existing suite must stay green. Baseline on this machine is **269 passed / 7 failed**, the 7 being pre-existing `tests/test_domain_fr.py` failures (fastText `.bin` absent locally, `ScrapeResult` tuple-unpack drift, async harness drift) plus a pre-existing `tests/test_api.py` collection error — all verified byte-identical on unchanged code.
- **Post-deploy:** re-run `/detect-debug` on `https://www.sumca.fr/` — expect `ok=true`, `url=https://www.sumca.fr/fr/`, `method` containing `alternative_hreflang`, and `debug.decision` no longer `Case 2a`. `/detect-debug` bypasses the Redis cache; a cached `nok` otherwise persists 7 days.

Raw pre-change capture for comparison: `scratchpad/dd_90_sumca.json`.
