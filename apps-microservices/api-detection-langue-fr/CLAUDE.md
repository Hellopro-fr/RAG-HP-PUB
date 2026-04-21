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
3. **Challenge detection** — Identifies Cloudflare, DataDome, Squid, Imperva, HTTP 4XX/5XX error pages.
4. **URL analysis** — TLD `.fr` (strong signal), `/fr/` path, `lang=fr` query, `fr.` subdomain.
5. **HTML tags** — `<html lang>`, `<meta og:locale>`, `<meta name=LANGUAGE>`, `<meta http-equiv=content-language>`.
6. **NLP** — fastText primary → langdetect+langid cross-check when uncertain. Cookie consent banners stripped before analysis.
7. **Alternative links** — hreflang, data-lang, data-gt-lang, `/fr/` links, option tags. Sorted by reliability (high/medium/low), validated via HTTP.
8. **Decision matrix** — 9 cases combining URL/HTML/NLP signals with confidence scores.

## Conventions

- Three modes: `simple` (URL + lang attr), `complete` (+ NLP + alternatives), `first_match` (batch grouped, stop at first FR per group).
- Batch has 2-pass: parallel processing (with stagger) then sequential retry for failures.
- All external HTTP calls go through Apify proxy (APIFY_PROXY env var).
- Detects Cloudflare/WAF/Squid/HTTP error challenge pages and reports them as errors.
- Cache uses different TTLs based on result quality (definitive vs transient failures).
- `force_refresh` parameter bypasses cache read but still writes (overwrites stale data).
- Alternative URLs include method, reliability tier, validation status, and region priority.

## Concurrency & Admission Control

Under concurrent load the service applies three layers of protection:

1. **Admission middleware** rejects with `503 + Retry-After` when in-flight count reaches `ADMISSION_MAX_SLOTS` (default 12). `/detect-debug` has an isolated budget via `ADMISSION_DEBUG_SLOTS` (default 2).
2. **Inflight URL dedup** coalesces concurrent fetches of the same URL to a single browser launch. Bypassed when `force_refresh=True`.
3. **Browser semaphore** caps concurrent Camoufox/Chromium instances at `BROWSER_SEMAPHORE_SIZE` (default 10).

Prometheus metrics exposed at `/metrics` for all three layers.

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

## Dependencies on Other Services

None (standalone). Requires Apify proxy (`APIFY_PROXY` env var). Optionally uses Redis for caching (`REDIS_URL` env var).
