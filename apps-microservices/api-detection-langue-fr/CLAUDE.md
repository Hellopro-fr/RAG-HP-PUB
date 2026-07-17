# api-detection-langue-fr

Detects whether a website is in French or has a French version. Uses URL analysis, HTML lang tags, hreflang links, NLP content detection (fastText + langdetect/langid), and a 9-case decision matrix with confidence scoring.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Scraping:** Camoufox (stealth Firefox, default) via Playwright; Chromium fallback via `CAMOUFOX_ENABLED=false` or on Camoufox launch failure. Apify proxy mandatory for both.
- **NLP:** fastText (primary), langdetect + langid (cross-check)
- **HTML parsing:** BeautifulSoup4 + lxml
- **Cache:** Redis (optional, graceful degradation)
- **No shared libs** (standalone service)

## Build / Run

- **Port:** 8999
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8999 --proxy-headers --timeout-keep-alive 300`
- **Tests:** `pytest tests/`
- **Docker build:** installs Playwright + Chromium (fallback) and fetches the Camoufox binary at build time. Camoufox's ~200MB browser is stored in the image.
- **Required env vars:** `APIFY_PROXY` (proxy password)
- **Optional env vars:** `REDIS_URL` (cache)

## Folder Structure

```
api-detection-langue-fr/
  main.py                        # FastAPI app
  app/
    api/
      routes.py                  # /detect, /detect-batch, /check-url, /detect-debug, /health
    core/
      config.py                  # Settings (pydantic-settings + .env)
      domain_fr.py               # DomainFR detector, DomainCache (Redis)
    models/
      schemas.py                 # Request/Response models, AlternativeUrl, Debug models
    services/
      language_detector.py       # NLP detection, challenge page detection
      scraper.py                 # Playwright scraping (proxy, UA rotation, resource blocking)
      redirect_tracker.py        # fetch_html (retry cascade + URL variants)
  tests/
    test_api.py
    test_domain_fr.py
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/detect` | Detect French for a single URL (simple/complete mode) |
| `POST` | `/api/v1/detect-batch` | Batch detection (max 100 URLs, 2-pass parallel+retry, first_match mode) |
| `GET`  | `/api/v1/check-url` | URL-only check (no HTML fetch) |
| `POST` | `/api/v1/detect-debug` | Debug mode with full pipeline trace (fetch, cleaning, URL, HTML, NLP, alternatives, decision) |
| `GET`  | `/api/v1/health` | Health check |

## Detection Pipeline

1. **Cache Redis** — Lookup by normalized domain. TTL: 30d (ok=true), 7d (ok=false definitive), 6h (transient failures). Bypass via `force_refresh=true`.
2. **Fetch HTML** — Playwright headless via Apify proxy. 3 retries (auto rotation) + fallback URL variants (http/https, www/sans-www).
3. **Page validation** — Classifies the fetched page: `valid` / `http_error` (4XX/5XX) / `soft_404` (200 OK + body looks like "page not found") / `redirected_to_home` (deep path 302'd to root). Invalid → optional one-hop homepage fallback.
4. **Challenge detection** — Identifies Cloudflare, DataDome, Squid, Imperva, HTTP 4XX/5XX error pages.
5. **URL analysis** — TLD `.fr` (strong signal), `/fr/` path, `lang=fr` query, `fr.` subdomain.
6. **HTML tags** — `<html lang>`, `<meta og:locale>`, `<meta name=LANGUAGE>`, `<meta http-equiv=content-language>`.
7. **NLP** — fastText primary → langdetect+langid cross-check when uncertain. Cookie consent banners stripped before analysis.
8. **Alternative links** — hreflang, data-lang, data-gt-lang, `/fr/` links, option tags. Sorted by reliability (high/medium/low), validated via HTTP.
9. **Decision matrix** — 9 cases combining URL/HTML/NLP signals with confidence scores.

## Conventions

- Three modes: `simple` (URL + lang attr), `complete` (+ NLP + alternatives), `first_match` (batch grouped, stop at first FR per group).
- Batch has 2-pass: parallel processing (with stagger) then sequential retry for failures.
- All external HTTP calls go through Apify proxy (APIFY_PROXY env var).
- Detects Cloudflare/WAF/Squid/HTTP error challenge pages and reports them as errors.
- Cache uses different TTLs based on result quality (definitive vs transient failures).
- `force_refresh` parameter bypasses cache read but still writes (overwrites stale data).
- Alternative URLs include method, reliability tier, validation status, and region priority.

## Concurrency & Admission Control

Under concurrent load the service applies multiple layers of protection.

**Layer model (post 2026-05-17 carve-out):**

1. **Route-level admission gate** for production paths (`/detect` and `/detect-batch`). The gate is acquired ONLY when an actual `fetch_html` call is required — meaning no `html_content` was provided in the request, no cache HIT short-circuited the request, and the caller is not an inflight-dedup follower riding a leader's future. On saturation:
   - `POST /detect` → HTTP 503 + `Retry-After` header.
   - `POST /detect-batch` → per-item `DetectionResponse{method='admission_rejected', ok=False, error='Service temporarily saturated'}` inline; no whole-batch 503. Pass 2 (sequential retry, 2s gap) retries items in `{fetch_failed, challenge_page, admission_rejected}` — admission saturation is transient.
   - `GET /check-url` → **bypasses admission entirely**. No HTML fetch needed; no slot consumed.
2. **Debug admission middleware** for `/detect-debug` only — isolated `_debug_admission` controller (`ADMISSION_DEBUG_SLOTS`, default 2) keeps dev traffic from starving production. Returns 503 + `Retry-After` on saturation.
3. **Inflight URL dedup** coalesces concurrent fetches of the same URL into a single browser launch. The dedup leader acquires the admission slot; followers wait on the leader's future and do NOT acquire their own slot.
4. **Browser semaphore** caps concurrent Camoufox/Chromium instances at `BROWSER_SEMAPHORE_SIZE` (default 10).

`'admission_rejected'` is in `DomainCache._NEVER_CACHE_METHODS` — service saturation must never be persisted as a domain answer.

**`INFLIGHT_REQUESTS` gauge semantic shift (2026-05-17):** previously "admitted requests in middleware"; now "active fetches at route level". Lower in absolute terms — cache HITs, `html_content` bypass calls, and dedup followers no longer contribute. Grafana panels referencing this gauge need a panel-description update only; data integrity is unchanged.

**`ADMISSION_REJECTED{endpoint}` label cardinality (2026-05-17):**
| Before | After |
|---|---|
| `/api/v1/detect` (middleware) | `/api/v1/detect` (route helper; batch items emit here too) |
| `/api/v1/detect-batch` (middleware) | _no longer emitted_ — batch items fold into `/api/v1/detect` |
| `/api/v1/check-url` (middleware) | _no longer emitted_ — `/check-url` bypasses admission entirely |
| `/api/v1/detect-debug` (middleware) | `/api/v1/detect-debug` (unchanged) |

Grafana panels filtering on `endpoint=~"detect-batch\|check-url"` will go silent. Update PromQL accordingly.

Prometheus metrics exposed at `/metrics` for all layers.

Spec: `docs/superpowers/specs/2026-05-17-detection-langue-fr-crawler-admission-carveout-design.md`.

### Env vars

| Variable | Default | Purpose |
|---|---|---|
| `BROWSER_SEMAPHORE_SIZE` | `10` | Max concurrent Camoufox/Chromium instances |
| `CAMOUFOX_ENABLED` | `true` | Use Camoufox; `false` falls back to Chromium |
| `ADMISSION_ENABLED` | `true` | Kill switch for admission middleware |
| `ADMISSION_MAX_SLOTS` | `12` | Production endpoint in-flight limit |
| `ADMISSION_DEBUG_SLOTS` | `2` | `/detect-debug` in-flight limit |
| `ADMISSION_RETRY_AFTER_SECONDS` | `30` | `Retry-After` header value in 503 responses |
| `INFLIGHT_DEDUP_ENABLED` | `true` | Kill switch for URL dedup |

Callers MUST use the shared contract: `libs/common-utils/src/common_utils/detection_client.py` (Python) or mirror its env vars (`DETECTION_MAX_CONCURRENCY`, `DETECTION_REQUEST_TIMEOUT_S`, `DETECTION_MAX_RETRIES`, `DETECTION_BACKOFF_BASE_S`) in other languages.

### Method values added by the carve-out

| Method | Where surfaced | Caller action |
|---|---|---|
| `admission_rejected` | `/detect-batch` per-item only (single `/detect` translates to HTTP 503) | Retry the affected item after `Retry-After`. Never persist as a domain verdict. |

## Invalid Page Rejection & Homepage Fallback

Three new method values surface in `DetectionResponse.method` when the requested page is rejected:

| Method | Meaning | Cache TTL |
|---|---|---|
| `http_error` | Hard 4XX/5XX status | 7 days |
| `soft_404` | 200 OK but body matches not-found heuristic (title/H1 regex + thin content, or URL path 404 marker) | 6 hours |
| `redirected_to_home` | Requested non-root path, server redirected to `/` | 7 days |

Callers should treat these as definitive failures (do NOT retry).

When validation rejects, the service tries the domain's homepage once. If the homepage is valid, the request returns `ok=True` with `analyzed_url=<homepage>` set. If the homepage also fails, the original verdict is returned.

`analyzed_url` is also set on cache HITs where the cached entry was originally seeded by a different URL on the same domain (e.g., requesting `/some/page` returns a cached homepage answer because the cache is keyed by domain).

### Per-request flag

- `homepage_fallback: bool = true` on `DetectionRequest` and `BatchDetectionRequest`. Set `false` for strict URL-level mode.

### Env vars

| Variable | Default | Purpose |
|---|---|---|
| `INVALID_PAGE_DETECTION_ENABLED` | `true` | Master kill switch for the validator. `false` = pre-validation behavior (page-validator skipped entirely). |
| `HOMEPAGE_FALLBACK_ENABLED` | `true` | Master kill switch for the homepage fallback hop. `false` = always return rejection on invalid page. |
| `SOFT_404_TITLE_THIN_THRESHOLD` | `2000` | Visible-text char limit when title regex matches. |
| `SOFT_404_H1_THIN_THRESHOLD` | `1500` | Visible-text char limit when H1 regex matches. |
| `INVALID_PAGE_TTL_HARD_S` | `604800` (7d) | Cache TTL for `http_error` + `redirected_to_home`. |
| `INVALID_PAGE_TTL_SOFT_S` | `21600` (6h) | Cache TTL for `soft_404`. |

### Endpoint behavior

| Endpoint | Validate? | Homepage fallback? |
|---|---|---|
| `/detect` | Yes | Yes (default ON) |
| `/detect-batch` (all modes) | Yes | Yes (default ON, per item) |
| `/detect-debug` | Yes (overrides result.ok / result.method / result.error if non-VALID — pipeline trace preserved) | **OFF** (debug shows requested URL's actual pipeline state) |
| `/check-url` | N/A (no HTML fetch) | N/A |

Batch Pass 2 retry: `fetch_failed`, `challenge_page`, and `admission_rejected` (admission saturation is transient — slot may free in the 2s inter-retry gap). The validator method values (`http_error`, `soft_404`, `redirected_to_home`) are NOT retried — they are domain properties that should not change between Pass 1 and Pass 2.

### Metrics

- `detection_validation_verdicts_total{verdict}` — counter, label values: `valid`, `http_error`, `soft_404`, `redirected_to_home`.
- `detection_homepage_fallback_triggered_total{outcome}` — counter, label values: `success`, `rejected`, `network_failure`.

## Dependencies on Other Services

None (standalone). Requires Apify proxy (`APIFY_PROXY` env var). Optionally uses Redis for caching (`REDIS_URL` env var).
