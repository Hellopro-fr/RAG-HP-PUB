# Detection-Langue-FR — Crawler Carve-Out from Admission Pool

> **Date:** 2026-05-17
> **Status:** Approved — ready for plan writing
> **Companion:** `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`
> **Service:** `apps-microservices/api-detection-langue-fr`
> **Branch:** `features/poc`

---

## 1. Problem

During high-load periods driven by BO batches (`detectBatchUrls` from `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php`), the production admission pool of `api-detection-langue-fr` reaches `ADMISSION_MAX_SLOTS` (default 12). Once saturated, the admission middleware emits HTTP 503 + `Retry-After` to **every** incoming request on `/detect`, `/detect-batch`, and `/check-url`, regardless of whether that request will actually launch a browser.

The `crawler-service` (Node.js / Crawlee) calls `/detect` with `html_content` already pre-fetched by the crawler's own Playwright session. That code path never touches Camoufox/Chromium inside the detection service — it only runs `DomainFR.check_page_if_french(html, mode)`. Yet the admission middleware does not differentiate: a crawler-service call competes for the same 12 slots as a BO-originated call that *will* perform a real fetch via Apify proxy.

Symptom: under sustained BO traffic, `crawler-service` sees a flood of HTTP 503 from `DetectionLangueClient.detect()`, exhausts its `DETECTION_MAX_RETRIES=2` retry budget, and either delays the crawl (stuck in retry loop) or fails outright with `Detection API error: HTTP 503`. The crawler's contention is not on a resource the detection service actually needs to protect — it is fully accidental.

Two consumer profiles, one shared pool:

| Caller | Sends `html_content`? | Real cost on detection service |
|---|---|---|
| BO PHP `detectBatchUrls` | No | Full pipeline: cache miss → Playwright launch via Apify proxy → validate → DomainFR |
| crawler-service `DetectionLangueClient.detect` | Yes (always) | Cache skip → DomainFR only (in-process, no browser) |

The 180-second BO timeout problem (`https://api.hellopro.eu/detection_site_fr-service/api/v1/detect-batch: Operation timed out after 180001 milliseconds`) is a separate root cause (gateway `DOWNSTREAM_TIMEOUTS_S["api-detection-langue-fr-service"] = 180.0` + long batches with many slow URLs). It is **out of scope** for this spec — addressed in a follow-up after BO-side batch-duration data is collected.

## 2. Goals

- Eliminate `crawler-service` HTTP 503s caused by BO contention.
- Keep the existing browser-pool protection for callers that *do* need a fetch.
- Preserve the BO PHP retry contract (`http_code === 503` on saturation for single-URL calls).
- Keep the kill switch `ADMISSION_ENABLED=false` working as a single-flag rollback.
- Surface admission rejection as a per-item result inside `/detect-batch` so the caller can keep partial batch results.

## 3. Non-Goals

- BO PHP code change to retry `admission_rejected` items (separate follow-up spec).
- BO 180s timeout fix (separate follow-up, needs duration distribution data first).
- Async / job-queue rework of the API (rejected upstream — too heavy for the symptom).
- Tuning `ADMISSION_MAX_SLOTS` (defer to post-rollout observation).

## 4. Architecture

The admission gate moves from middleware to inside the route, scoped to the actual fetch operation rather than the entire request lifetime.

### 4.1 Pipeline (current `_detect_single_url`)

```
[middleware admission acquire ←─ saturated here = 503 for everyone]
  ↓
cache lookup
  ↓ (miss)
inflight dedup → fetch_html via Playwright + Apify
  ↓
validate_page
  ↓ (invalid + homepage_fallback)
homepage fetch_html
  ↓
challenge / DomainFR
  ↓
[middleware admission release]
```

### 4.2 Pipeline (new)

```
[no middleware admission for /detect, /detect-batch, /check-url]
  ↓
cache lookup (free)
  ↓ (miss)
inflight dedup wrapper:
  leader path  → admission.acquire() → fetch_html → release()
  follower path → wait on leader's future, no acquire
  ↓
validate_page
  ↓ (invalid + homepage_fallback)
homepage admission.acquire() → fetch_html → release() (with separate dedup key)
  ↓
challenge / DomainFR
```

Free paths (no admission acquire):

- `html_content` provided → fetch branch skipped entirely.
- Cache HIT (domain-keyed) → return immediately.
- Inflight dedup followers → wait on leader's future without separate slot acquire.
- `/check-url` (URL-only check, no HTML fetch) → middleware bypass, no route-level gate.

`/detect-debug` keeps the existing middleware admission against the debug pool. Its dev-traffic isolation budget is unchanged.

### 4.3 Why this matches the actual resource

The protected resource is the browser semaphore (`BROWSER_SEMAPHORE_SIZE`, default 10) plus the Apify proxy budget. Admission was always meant to fast-fail before those caps were hit, not to gate request count. Moving the gate inside the route makes the abstraction honest: only requests that will *actually fetch* are accounted for.

## 5. Endpoint Contract

| Endpoint | Before | After |
|---|---|---|
| `POST /detect` | Middleware admission; 503 + `Retry-After` on saturation. | Route-level admission gated on fetch. `html_content` provided → never 503 (no fetch). No `html_content` + saturated → 503 + `Retry-After` (caller contract preserved). |
| `POST /detect-batch` | Middleware admission. Saturated batch → whole-batch 503 (caller retries entire payload). | Per-item gating inside route. Items with `html_content` bypass admission. Items without `html_content` that hit saturation → inline `DetectionResponse{ok: false, method: 'admission_rejected', error: 'Service temporarily saturated'}`. No whole-batch 503. |
| `GET /check-url` | Middleware admission. | Bypasses admission entirely (URL-only check, no HTML fetch). |
| `POST /detect-debug` | Middleware admission against debug pool. | Unchanged. |
| `GET /health`, `GET /metrics`, `GET /`, `GET /docs`, `GET /openapi.json` | Middleware bypass. | Unchanged. |

### 5.1 New `method` value

`admission_rejected` — only ever surfaces in `/detect-batch` per-item results. Single `/detect` translates the underlying `_AdmissionRejected` into HTTP 503 to preserve the BO PHP retry contract.

### 5.2 Pass 2 retry set

Batch Pass 2 (sequential, 2s gap, fresh fetch) extends from `{fetch_failed, challenge_page}` to `{fetch_failed, challenge_page, admission_rejected}`. Rationale: admission saturation is transient — the slot may free by the time Pass 2 runs. Same applies inside the `first_match` group retry.

### 5.3 Cache

`'admission_rejected'` is added to `DomainCache._NEVER_CACHE_METHODS`. Saturation is service state, not a domain property. Persisting the rejection would surface a stale "this domain is rejected" result on subsequent calls.

### 5.4 Caller-side impact

| Caller | Required change |
|---|---|
| `crawler-service` `DetectionLangueClient` (always sends `html_content`) | None. Never encounters `admission_rejected`. |
| BO PHP `detectBatchUrls` (never sends `html_content`) | None **required** to ship this spec. However, items with `method='admission_rejected'` will surface as `ok=false` results — current PHP loop (`script_identifier_site_fr_v2.php`) would persist them as `est_fr='0'` (non-FR), which is wrong. **Follow-up spec** (out of scope here) will add `admission_rejected` to the retry-eligible set in `enfiler_url_retry_fr()`. Until that lands, BO continues to suffer the same total throughput; per-item rejection is at worst no worse than whole-batch 503 it replaces. |

## 6. Server Implementation

### 6.1 Files touched

| Path | Change |
|---|---|
| `app/main.py` | `AdmissionMiddleware` constructed with only `debug_controller`. `prod_admission` controller still created here but exposed at module level for route import. |
| `app/middleware/admission.py` | Drop `_PROD_PATHS` set, drop `prod_controller` parameter. Middleware only handles `_DEBUG_PATH`. Health/metrics/docs paths still bypass. |
| `app/api/routes.py` | `_detect_single_url` adds `_fetch_with_admission(url, proxy_url)` helper used inside `_inflight_dedup.coalesce()`. Single `/detect` handler catches `_AdmissionRejected` → `HTTPException(status_code=503, headers={'Retry-After': ...})`. Batch `_process_item_core` catches → returns `DetectionResponse(method='admission_rejected', ok=False)`. Homepage fallback fetch wrapped in its own `_fetch_with_admission` call (separate dedup key = homepage URL). |
| `app/api/routes.py` (batch Pass 2) | Retry-eligible method set: `{'fetch_failed','challenge_page','admission_rejected'}`. Same change inside `first_match` `process_group()` retry-set. |
| `app/core/domain_fr.py` | `DomainCache._NEVER_CACHE_METHODS` adds `'admission_rejected'`. |
| `app/core/metrics.py` | Reuse existing `ADMISSION_REJECTED{endpoint}` counter. Document new label values (route-level increments). `INFLIGHT_REQUESTS` semantic change documented in CLAUDE.md (see §10). |

### 6.2 Admission helper pattern

```python
class _AdmissionRejected(Exception):
    pass

async def _fetch_with_admission(
    url: str,
    proxy_url: Optional[str],
    endpoint_label: str,
) -> ScrapeResult:
    admitted = await _prod_admission.acquire()
    if not admitted:
        ADMISSION_REJECTED.labels(endpoint=endpoint_label).inc()
        raise _AdmissionRejected
    try:
        return await fetch_html(url, proxy_url)
    finally:
        await _prod_admission.release()
```

Composition with dedup:

```python
fetch_result = await _inflight_dedup.coalesce(
    dedup_key,
    lambda: _fetch_with_admission(url, proxy_url, '/api/v1/detect'),
)
```

Only the dedup *leader* enters `_fetch_with_admission` → only the leader acquires a slot. Followers wait on the leader's awaitable future. If the leader raises `_AdmissionRejected`, the existing dedup propagation surfaces the same exception to every follower in the wait-group.

### 6.3 Single vs batch translation

```python
# /detect handler
try:
    return await _detect_single_url(...)
except _AdmissionRejected:
    raise HTTPException(
        status_code=503,
        detail={"detail": "Service temporarily saturated",
                "retry_after_seconds": settings.ADMISSION_RETRY_AFTER_SECONDS},
        headers={"Retry-After": str(settings.ADMISSION_RETRY_AFTER_SECONDS)},
    )

# /detect-batch _process_item_core
try:
    return await _detect_single_url(...)
except _AdmissionRejected:
    return DetectionResponse(
        ok=False, url=url, method='admission_rejected',
        error='Service temporarily saturated',
    )
```

### 6.4 Why leader-only acquire (not "acquire before dedup")

If admission is acquired *before* entering `coalesce()`, then 5 concurrent callers for the same URL each acquire a slot — 4 are wasted because only the leader runs `fetch_html`. Putting admission *inside* the coalesced function ensures only the leader contends for a slot. Followers ride the leader's future. Same correctness, cleaner resource use.

### 6.5 Homepage fallback

Homepage fallback fetches a *different* URL (the domain root). It runs through its own `_fetch_with_admission` call wrapped in a separate `_inflight_dedup.coalesce(homepage_key, ...)`. Multiple sibling requests that all trigger fallback for the same homepage are deduped at the homepage layer; only one leader acquires a slot for the homepage fetch.

If the homepage fetch raises `_AdmissionRejected`, the route surfaces `admission_rejected` to the caller (single → 503, batch → inline `DetectionResponse{method='admission_rejected'}`). Do NOT downgrade to the original validator verdict (`http_error` / `soft_404` / `redirected_to_home`) — those are domain properties cached for 7d / 6h; admission rejection is service saturation and must never be cached. Routing path: the homepage-side `_AdmissionRejected` bubbles up through the same exception path as the initial fetch — `_detect_single_url` does not catch it, and `_process_item_core` / single-handler translation logic is identical for both fetch sites.

## 7. Configuration

| Env var | Default | After |
|---|---|---|
| `ADMISSION_ENABLED` | `true` | Single kill switch for both middleware-debug-pool AND route-level prod gate. `false` disables every admission acquire — all requests proceed. |
| `ADMISSION_MAX_SLOTS` | `12` | Consumed by the route-level `_prod_admission` controller. Same tuning knob. |
| `ADMISSION_DEBUG_SLOTS` | `2` | Consumed by middleware debug controller. Unchanged. |
| `ADMISSION_RETRY_AFTER_SECONDS` | `30` | Used by single `/detect` 503 + by batch inline `error` field text. Unchanged. |

No new env vars. The change is internal refactoring with no operator-visible knob shift.

## 8. Observability

| Signal | Status |
|---|---|
| `ADMISSION_REJECTED{endpoint}` counter | Reused. New labels written by route helper: `/api/v1/detect`, `/api/v1/detect-batch`. Existing `/api/v1/detect-debug` label still emitted by middleware. |
| `INFLIGHT_REQUESTS` gauge | **Semantic shift**. Was: "admitted requests in middleware". Now: "active browser fetches inside route". Lower in absolute terms because cache HITs, html_content paths, and dedup followers no longer increment it. Document the change in `apps-microservices/api-detection-langue-fr/CLAUDE.md` § Concurrency & Admission Control. Grafana dashboards referencing this gauge need a panel description update. |
| `VALIDATION_VERDICTS`, `HOMEPAGE_FALLBACK_TRIGGERED`, `DEDUP_HITS`, `BROWSER_SEMAPHORE_WAITERS` | Unchanged. |

## 9. Testing

Test file: `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` (plus extensions to existing `tests/test_api.py`, `tests/test_admission.py` if present).

| Test | Scenario | Expect |
|---|---|---|
| `test_detect_html_provided_bypasses_admission` | `/detect` with `html_content` while prod pool saturated (mock 0 available slots) | 200 OK, no admission acquire attempted |
| `test_detect_no_html_503_when_saturated` | `/detect` no `html_content`, prod pool saturated | HTTP 503 + `Retry-After: 30` header |
| `test_check_url_bypasses_admission` | `/check-url` while pool saturated | 200 OK, no slot consumed |
| `test_batch_per_item_admission` | `/detect-batch` mixed items (some with html, some without) while saturated | items with html → ok results; items without → `method='admission_rejected'`; HTTP 200 with full `results` array; no whole-batch 503 |
| `test_batch_pass2_retries_admission_rejected` | Pass 1 saturated; slot freed by Pass 2 | Pass 2 succeeds, final result `ok=True` |
| `test_first_match_pass2_retries_admission_rejected` | Same as above but inside `first_match` group retry path | Group succeeds after Pass 2 |
| `test_dedup_follower_no_admission_acquire` | 5 concurrent identical URLs, pool size 1 | 1 leader acquires; 4 followers wait on future; all 5 return same `ScrapeResult`-derived response; only 1 increment of `ADMISSION_REJECTED` would happen if leader rejected |
| `test_dedup_follower_propagates_rejection` | Leader rejected, 4 followers waiting | All 5 surface `admission_rejected` (single → 503, batch → inline) |
| `test_admission_rejected_never_cached` | Force admission rejection, then retry same URL with slot free | Second call performs fresh fetch (cache miss for the rejection) |
| `test_homepage_fallback_admission` | Initial fetch ok but invalid → homepage fetch attempted while pool saturated | Original rejection returned; transient 6h cache TTL applied (does not poison the domain key) |
| `test_debug_pool_isolated` | Prod pool full, `/detect-debug` called | `/detect-debug` proceeds (debug pool independent) — regression guard |
| `test_admission_disabled_kill_switch` | `ADMISSION_ENABLED=false` | No gating anywhere, no `ADMISSION_REJECTED` increments |

Existing tests on middleware admission for `/detect`, `/detect-batch`, `/check-url` (whole-request 503) will need updates or deletion — those behaviors no longer exist for prod paths.

## 10. Rollout

1. **Phase 1 — Deploy server change with defaults.** `ADMISSION_ENABLED=true`, `ADMISSION_MAX_SLOTS=12`. Crawler 503 rate drops to zero immediately. BO observes per-item `admission_rejected` results replacing whole-batch 503s.
2. **Phase 2 — Observe.** Watch `ADMISSION_REJECTED{endpoint}` per-label split. Crawler endpoint label count should be 0. BO label count should approximate the previous whole-batch-503 rate × average batch size. Tune `ADMISSION_MAX_SLOTS` if BO item rejection rate is too high (consider sizing it against actual browser semaphore + Apify concurrency budget).
3. **Phase 3 — Follow-up spec.** BO PHP retry handling for `admission_rejected` items in `script_identifier_site_fr_v2.php` (route them to `enfiler_url_retry_fr` instead of persisting as `est_fr='0'`).

Kill switch: `ADMISSION_ENABLED=false` → all gating disabled. Safe rollback.

## 11. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `INFLIGHT_REQUESTS` gauge semantic shift breaks dashboard interpretation | Low | Update `CLAUDE.md` § Concurrency. Add panel description note in Grafana. No code dependency on the gauge value. |
| BO PHP mislabels `admission_rejected` items as non-FR (`est_fr='0'`) until follow-up spec ships | Medium | Acknowledge in spec § 5.4. Follow-up scheduled. Current behavior is no worse than the whole-batch 503 it replaces (same items would have been retried by the BO batch retry loop anyway). |
| Dedup leader rejected → all followers rejected = thundering-herd when slot frees | Low | Each follower retries independently afterward (caller's responsibility). Pass 2 retry handles batch case. Single `/detect` callers retry via BO PHP retry loop. |
| Homepage fallback admission rejection cached at 6h might mask a fast recovery | Low | `TTL_TRANSIENT=6h` is the existing transient cache TTL — same behavior as other transient failures. Acceptable. |
| Route-level gate adds latency overhead vs middleware short-circuit | Negligible | Request body already parsed for routing in current middleware path; admission check inside route is a single asyncio.Lock acquire. Microsecond cost. |

## 12. Follow-Ups (out of scope)

- **BO PHP retry handling for `admission_rejected`** — add to retry-eligible set in `script_identifier_site_fr_v2.php`, `script_retry_identifier_site_fr.php`, `pct_recheck_site_non_fr.php`. Mirror existing transient-error retry pattern.
- **BO 180s timeout** — collect batch-duration distribution, decide between (a) raising gateway `DOWNSTREAM_TIMEOUTS_S` ceiling, (b) shrinking BO `array_chunk` size, (c) implementing async pattern (POST returns job_id, separate poll endpoint). Separate spec when data is available.
- **`ADMISSION_MAX_SLOTS` tuning** — post-rollout, size against real browser-semaphore + Apify concurrency budget rather than the current `12` default.

## 13. Implementation Order

1. Server route-level admission helper (`_fetch_with_admission`) + dedup composition.
2. Middleware shrink to debug-only path.
3. `DomainCache._NEVER_CACHE_METHODS` update.
4. Single `/detect` exception → 503 translation.
5. Batch `_process_item_core` exception → inline `admission_rejected` translation.
6. Homepage fallback fetch wrapping.
7. Batch Pass 2 retry-set extension (both standard and `first_match`).
8. Tests (red → green per `test-driven-development` skill).
9. CLAUDE.md doc update for `INFLIGHT_REQUESTS` semantic shift + crawler carve-out behavior.
