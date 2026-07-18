# Detection-Langue-FR — Transient HTTP-Error Retry + Stub-Page Hop — Design

**Date:** 2026-07-18
**Status:** Approved (implemented same day)
**Scope:** `apps-microservices/api-detection-langue-fr` only. Additive method value for callers.
**Related:** Revises one decision of `2026-05-05-detection-langue-fr-invalid-page-rejection-design.md` ("validator verdicts are definitive — never retried"). Complements `2026-06-01-detection-langue-fr-async-job-api-design.md` (throughput fix — deployment, not code).

---

## Problem

Field audit of 11 BO crawl-relaunch runs (2026-07-12, 55 unique domains classified NON-FR, each live-verified):

| Bucket | Count | Verified ground truth |
|---|---|---|
| `error` = Timeout global item (300s) | 33 | Not a language verdict. Whole batches that timed out at 16:10 passed FR at 16:17. |
| `http_error` | 9 | 6 false negatives (transient 429/403-challenge/401-WAF), 2 dead sites (correct), 1 blocked |
| `fetch_empty_content` | 6 | 5 false negatives (live FR sites; incl. 1 "page moved" stub), 1 geo-blocked |
| `Check_nok_v2` / `nlp_not_confirmed` | 7 | genuine matrix verdicts (out of scope here) |

Root causes in code:

1. **`http_error` is terminal and cached 7 days** regardless of status code (`routes.py` rejection sites; `INVALID_PAGE_TTL_HARD_S`). A transient Vercel 429 (airmaxgroupe.fr) poisons the domain for a week. The 2026-05-05 decision targeted real 404s; it over-reaches on 401/403/408/429/5xx.
2. **Validator wins over challenge detection.** `validate()` fires on `status 400-599` *before* `detect_challenge_page` runs (`routes.py` [3] precedes [4]). A Cloudflare 403 **with a challenge body** becomes terminal `http_error` instead of retryable `challenge_page` (instron.com, pinetteemidecau.eu, probst-handling.com).
3. **Batch Pass 2 retry set is too narrow**: `{fetch_failed, challenge_page, admission_rejected}` (`routes.py:582/598`, first_match `:503/:536`). `http_error` (even transient) and `fetch_empty_content` never get a second chance. Also: a Pass-2 retry without `force_refresh` would hit the cache entry written seconds earlier in Pass 1 (transient failures are cached 6h) — retry must bypass cache read.
4. **Tiny stub homepages rejected as `fetch_empty_content`.** A live site whose homepage is a "Page has moved → click here" stub (<100 visible chars, single link, ucmasn.fr) or a meta-refresh page is rejected by the Case-2b guard (`domain_fr.py:1118`) even though the real (French) site is one hop away.
5. **Latent bug:** Pass 2 runs `_process_item_core` with **no `asyncio.wait_for`** — one hanging retry hangs the entire batch indefinitely.

## Goals

- Transient HTTP failures (401/403/407/408/425/429, 5xx) become retryable and short-cached; definitive ones (404 & co.) keep today's behavior exactly.
- Challenge bodies win over raw status: 403+Cloudflare page → `challenge_page` (existing retry + proxy-rotation semantics).
- Pass 2 actually re-fetches (cache-read bypass) and is time-bounded.
- One-hop follow of stub pages (meta-refresh, single same-host link) before the empty-content reject.
- No caller change required; new method value is additive.

## Non-Goals

- **Retrying `Timeout global item (300s)` in Pass 2.** Deliberate divergence from the initial recommendation: the 300s clock starts *after* semaphore acquisition, so these items genuinely spent 300s working — retrying them sequentially inside the same saturated job adds up to `N×300s` (worse than the async-job TTL). The timeout bucket is addressed by (a) deploying the async job API (already coded, `2026-06-01` spec) which serializes jobs via `MAX_ACTIVE_JOBS`, and (b) caller re-runs (BO `--ids` re-run is the existing workflow).
- Language-matrix changes (Case 7/9 alt-probe, query-param switchers) — separate, smaller problem (~4 domains); measure after this ships.
- Parked-domain ("Site not installed" / "domain expired") classification — reporting cleanliness, not detection accuracy. Defer.
- Cross-host redirect handling — already correct (Playwright follows; final status is the destination's).

## Design

### 1. Rejection-site classification (`routes.py::_detect_single_url`, block [3])

After `validate_page` returns non-VALID, before the homepage-fallback logic:

```python
verdict_method = verdict.value
verdict_ttl = _ttl_from_verdict(verdict.value)
if verdict == ValidationVerdict.HTTP_ERROR:
    # A 4xx/5xx whose body is a WAF/challenge page is a block, not a page property.
    challenge = detect_challenge_page(fetch_result.html)
    if challenge:
        return DetectionResponse(ok=False, url=url, method='challenge_page',
                                 error=_build_challenge_error_msg(challenge))  # not cached (same as main-path challenge)
    if is_transient_http_status(fetch_result.status_code):
        verdict_method = 'http_error_transient'
        verdict_ttl = domain_cache.TTL_TRANSIENT  # 6h instead of 7d
```

All three rejection returns in the block use `verdict_method` / `verdict_ttl` instead of `verdict.value` / `_ttl_from_verdict(...)`.

`is_transient_http_status` lives in `page_validator.py` (pure):

```python
TRANSIENT_HTTP_STATUSES = frozenset({401, 403, 407, 408, 425, 429})
def is_transient_http_status(code: int) -> bool:
    return code in TRANSIENT_HTTP_STATUSES or 500 <= code < 600
```

Rationale per status: 401/403/407 = auth/WAF/IP-reputation (residential-proxy retry can pass); 408/425/429 = timing/rate-limit; 5xx = server-side transient. 404/410 and other 4xx remain definitive (`http_error`, 7d) — preserves the 2026-05-05 intent.

### 2. Pass-2 retry set + cache bypass + time bound (`routes.py::_run_batch_core`)

```python
_PASS2_RETRYABLE_METHODS = (
    'fetch_failed', 'challenge_page', 'admission_rejected',
    'http_error_transient', 'fetch_empty_content',
)
```

Used at all four sites (complete/simple collect + accept, first_match collect + accept).

`_process_item_core(item, force_refresh_override=None)` — Pass 2 calls it with `force_refresh_override=True` so the cache entry written by Pass 1 (6h transient) cannot short-circuit the retry. `force_refresh` already "bypasses read, still writes", so the retry outcome overwrites the transient entry.

Pass-2 calls gain the missing `asyncio.wait_for(..., timeout=300)` (bug 5).

`fetch_empty_content` needs no cache change: already in `DomainCache`'s transient set (6h), and `force_refresh_override` handles the retry path. `http_error_transient` is added to that same transient method set for defense in depth.

### 3. Stub-page hop (`routes.py` block between [3] and [4], + pure helper in `page_validator.py`)

```python
def find_stub_redirect_target(html: str, base_url: str) -> Optional[str]:
    # Cheap gate: stubs are tiny documents.
    if len(html) > 20_000: return None
    # Visible text must be under NLP_MIN_TEXT_LENGTH (same threshold as the empty-content guard).
    # Signal 1: <meta http-equiv="refresh" content="N;url=...">  → target
    # Signal 2: exactly one distinct same-host <a href> (www-variant tolerated;
    #           '#', mailto:, tel:, javascript: excluded) → target
    # Else None.
```

In `_detect_single_url`, only when `not html_was_provided` and the page validated VALID:

```python
if settings.STUB_PAGE_HOP_ENABLED:
    stub_target = find_stub_redirect_target(html_content, effective_url)
    if stub_target:
        hop = await _fetch_with_admission(stub_target, proxy_url, "/api/v1/detect")
        if hop and validate_page(hop, requested_url=stub_target) == ValidationVerdict.VALID:
            html_content, effective_url, stub_hopped = hop.html, hop.final_url, True
```

One hop, no recursion. On success the final result gets `analyzed_url = <hop target>` (same contract as the homepage fallback). On hop failure, flow continues with the stub content (ends as `fetch_empty_content`, now Pass-2-retryable). Same-host constraint kills the parked-page false positive (parked "buy this domain" links are off-host).

### 4. Config

| Variable | Default | Purpose |
|---|---|---|
| `STUB_PAGE_HOP_ENABLED` | `true` | Kill switch for the stub-page hop |

No env for the transient status set (constant; YAGNI). No new metric: `VALIDATION_VERDICTS` keeps counting raw verdicts; `http_error_transient` visibility comes from batch logs + the method value itself in responses.

### 5. Caller contract (additive)

| Method | Meaning | Cache TTL | Batch Pass 2 |
|---|---|---|---|
| `http_error` | Definitive 4xx (404, 410, …) | 7d (unchanged) | not retried (unchanged) |
| `http_error_transient` | 401/403/407/408/425/429/5xx without challenge body | 6h | retried |
| `challenge_page` | now ALSO covers 4xx/5xx whose body is a WAF/challenge page | not cached at fetch path (unchanged) | retried (unchanged) |
| `fetch_empty_content` | unchanged meaning | 6h (unchanged) | **now retried** |

BO `pct_traitement_crawling_rindra_BO.php` needs no change (displays method strings verbatim).

## Testing

- `test_page_validator.py`: `is_transient_http_status` boundaries; `find_stub_redirect_target` (meta-refresh, single same-host anchor, www-variant, two anchors → None, off-host → None, rich page → None, >20KB → None).
- `test_routes_invalid_page.py`: 403+challenge body → `challenge_page`; 429 → `http_error_transient` + `ttl_override == TTL_TRANSIENT`; 404 → unchanged (`http_error`, 7d, Pass-2 fetch count still 1); batch 429→200 recovery in Pass 2; Pass-2 retry carries `force_refresh=True`; stub-hop end-to-end (stub → FR target, `analyzed_url` set); hop disabled via env.
- `test_batch_core_refactor.py`: `fetch_empty_content` retried; Pass-2 `wait_for` timeout produces the standard timeout response instead of hanging.

## Rollout

Ship enabled (behaviors are strictly retry-more/cache-shorter; `STUB_PAGE_HOP_ENABLED=false` reverts the only novel fetch). Measure by re-running the 2026-07-12 failed IDs through the BO script after deploy and diffing the Non-FR table. Expected recovery: 6 verified http_error/empty false negatives immediately; timeout bucket via async-API deployment.
