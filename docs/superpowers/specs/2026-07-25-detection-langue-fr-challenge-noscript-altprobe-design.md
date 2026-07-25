# Detection langue FR — challenge patterns, noscript repair, alternative probing

**Date:** 2026-07-25
**Service:** `apps-microservices/api-detection-langue-fr`
**Origin:** detect-debug deep-dive on 5 NON-FR domain IDs (5672, 5789, 5166, 5184, 5856) — 5-agent
investigation with live probes + adversarial verification of each root cause.

## Findings

| ID | Domain | Really FR? | Verdict today | Root cause |
|---|---|---|---|---|
| 5672 | outilbox.fr | YES | `fetch_empty_content` | LiteSpeed lazy-loader nests GTM's `<noscript>` inside a second `<noscript>`; outer never closes; every parser puts 99% of the body inside noscript; cleaner decomposes noscript → 16 visible chars |
| 5789 | metaga.fr | NO (correct) | `Check_nok_v2` | metaga.fr 301→metaga.es; WPML switcher advertises a dead FR URL; debug trace mislabels the run "Case 6" and 120s browser fetch wasted on a self-redirecting candidate |
| 5166 | probst-handling.com | blocked | `http_error` 7d | ALTCHA-style "Bot check" JS proof-of-work served HTTP 401 on every path; pattern unknown to `detect_challenge_page` |
| 5184 | siderosengineering.com | YES (`/home-page-fr` live, `lang=fr`) | `Check_nok_v2` | Italian homepage advertises zero FR URLs (hreflang declares only self-referencing `it`); scanner is purely extractive |
| 5856 | lagff.com | blocked (La GFF = Générale Frigorifique France, Shopware shop) | `http_error` 7d | rescaled-waf PoW interstitial (HTTP 403); pattern unknown; scraper's existing 45s challenge-resolution poll never engaged |

## Fixes

### 1. Challenge patterns (`app/services/language_detector.py` — `detect_challenge_page`)
- `Rescaled_WAF`: ≥2 of {`/.well-known/rescaled-waf/`, `rescaled-waf:challenge-`, `<title>rescaled waf`}.
- `JS_PoW_bot_check`: anchor `<title>bot check</title>` + ≥1 of {`?create_challenge`,
  `your request is being verified`, `javascript is needed to access this site`, `brix/crypto-js`}.
- All markers verified present in the real captured pages (counts ≥1 each).
- One function feeds three consumers: scraper 45s resolution poll (`scraper.py:406`), `/detect`
  challenge-wins reclass (`routes.py:232`, commit b6b7742e), Case-6 alternative guard (`domain_fr.py:1218`).

### 2. Scraper stale-status trap (`app/services/scraper.py:~478`)
`status_code` is taken from the INITIAL `goto` response and never refreshed after the challenge
poll's `window.location.replace` navigation. A resolved challenge therefore still returns the
interstitial's 401/403 and `validate_page` rejects the real page. Fix: hoist `challenge_resolved`
to function scope; `status_code = 200 if challenge_resolved else (response.status if response else 0)`.

### 3. noscript-unwrap fallback (`app/services/language_detector.py` — `clean_html_to_text`)
When the cleaned text is `< NLP_MIN_TEXT_LENGTH` AND `len(html) > 20_000` (a real page cannot have
<100 visible chars in >20KB of HTML — mirrors `_STUB_MAX_HTML_LEN`), re-clean ONCE with `noscript`
*unwrapped* instead of decomposed. Tested on the captured outilbox.fr page: recovers 11,628 chars of
French. Rejected alternatives (both tested): always keeping noscript leaks EN/IT "enable JavaScript"
boilerplate into normal pages; regex-stripping well-formed pairs leaves the orphan open tag which
still swallows the body. **Review hardening:** the repaired text is accepted only when
≥ 5× `NLP_MIN_TEXT_LENGTH` (500 chars) — a swallowed body frees thousands of chars, a well-formed
"enable JavaScript" noscript frees ~100-200; without the floor, a legitimately thin >20KB page
would feed EN boilerplate to NLP and flip a transient `fetch_empty_content` into a definitive verdict.

### 4. Lang-substitution probe (`app/core/domain_fr.py` — `detect_alternative_languages`)
Only on the zero-candidate path: harvest self-referencing canonical/hreflang URLs, substitute the
declared non-fr lang token (word-boundary regex) with `fr` (e.g. `/home-page-it` → `/home-page-fr`),
queue at most 2 same-host candidates as method `lang_substitution` (medium). Existing HTTP validation
+ Case-6 NLP-fr confirmation gate wrong guesses — one-directional change (some NON-FR → FR, never
the reverse). **Review hardening:** one candidate per token occurrence (`/it/it-support` →
`/fr/it-support` + `/it/fr-support`, never `/fr/fr-support`), token case mirrored (`/IT/` → `/FR/`).

### 5. Alternative-validation hygiene (`app/core/domain_fr.py`, from the metaga.fr case)
- `_validate_single_url`: reject a candidate whose final redirected URL equals the page under
  analysis (`_compare_without_scheme` vs `self.homepage` / `self.original_homepage`) — dead WPML
  switcher links no longer trigger a wasted 120s Case-6 browser fetch. **Review carve-out:**
  cookie switchers (`/?lang=fr` → Set-Cookie + 302 back to the same host+path) are exempt —
  rejecting them would flip detectable-FR sites to `Check_nok_v2` (adversarial review finding).
- `_identify_decision_case`: report "Case 6: … found" only when `result.method.startswith('alternative_')`;
  otherwise "Case 6 attempted: N validated alternative(s), none confirmed French" (+ "→ Case 9"
  only when the result really is `Check_nok_v2`, else "(result: <method>)").
- ~~Case 9 response: include `alternative_urls=alternatives`~~ **REVERTED after review**: crawler
  `routes.ts:676-687` sets a different `crawlErrorMessage` when `ok=false` comes with non-empty
  `alternative_urls`, and BO `not_french_signal.php` exact-matches that string — exposing
  found-then-rejected alternatives would silently flip `not_french` → `insufficientData` in the BO
  pipeline (and `script_launch_crawl_csv.php` would re-check already-rejected candidates). Case 9
  keeps `alternative_urls` empty; diagnosis uses `/detect-debug`'s `debug.alternatives`.

### 6. Debug trace honesty (`app/models/schemas.py` + `app/api/routes.py`)
- `DebugFetchInfo.status_code: Optional[int]` populated from the fetch result (both blocked domains
  required live probes just to learn the HTTP status). Note: normalized to 200 when the scraper
  resolved a challenge in-browser (fix 2) — documented in the field description.
- Mirror the b6b7742e challenge-wins / transient reclass into the `/detect-debug` validate override
  so debug reports the method prod would return (`challenge_page` / `http_error_transient` instead of
  raw `http_error`).

## Non-goals
- Solving the PoW for `JS_PoW_bot_check` beyond what the existing 45s poll already does.
- Generic "verifying your browser" heuristic (kept narrow; revisit if a third WAF vendor shows up).
- BO-side report reclassification (separate backlog item).

## Ops notes
- Deploy b6b7742e first/along: it alone converts both 7d `http_error` verdicts to 6h retryable.
- After deploy: re-run 5166/5184/5856 with `force_refresh=true` (7d cached rejections).
- 5672 self-heals: `fetch_empty_content` is transient (6h) and the live site now serves balanced
  noscripts again; the code fix targets the recurring LiteSpeed+GTM class.
