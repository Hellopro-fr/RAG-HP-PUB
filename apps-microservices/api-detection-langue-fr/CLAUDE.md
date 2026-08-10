# api-detection-langue-fr

Detects whether a website is in French or has a French version. Uses URL analysis, HTML lang tags, hreflang links, NLP content detection (fastText + langdetect/langid), and a 9-case decision matrix with confidence scoring.

## Tech Stack

- **Language:** Python 3.10
- **Framework:** FastAPI + Uvicorn
- **Scraping:** Camoufox (stealth Firefox, default) via Playwright; Chromium fallback via `CAMOUFOX_ENABLED=false` or on Camoufox launch failure. Apify proxy mandatory for both.
- **NLP:** fastText (primary), langdetect + langid (cross-check)
- **HTML parsing:** BeautifulSoup4 + lxml
- **Cache:** Redis (optional, graceful degradation) via the shared `common_utils.redis.cache_service` pool (`libs/common-utils`) — bounded connections, socket timeouts, health checks, named client (`SERVICE_NAME`). `init_redis_pool()`/`close_redis_pool()` run in `main.py`'s lifespan; `DomainCache` and `JobStore` read `cache_service.redis_client` live at each call (None → cache invisible / async submit 503). Same system as crawler-service and image-comparison-service.
- **Shared libs:** `libs/common-utils` (Redis only — installed from `/opt/libs/common-utils` in the Dockerfile so the dev bind mount on `/app` can't hide it)

## Build / Run

- **Port:** 8999
- **Prerequisite (local run + tests):** `pip install -e libs/common-utils` (from repo root) — `main.py`/`domain_fr.py`/`async_jobs.py` import `common_utils.redis` unconditionally. The Docker image installs it at build time.
- **Run:** `uvicorn main:app --host 0.0.0.0 --port 8999 --proxy-headers --timeout-keep-alive 300`
- **Tests:** `pytest tests/`
- **Docker build:** installs Playwright + Chromium (fallback) and fetches the Camoufox binary at build time. Camoufox's ~200MB browser is stored in the image. `libs/common-utils` is installed **editable** from `/opt/libs/common-utils` (its `setup.py` `find_packages` would exclude `common_utils/redis` from a wheel — no `__init__.py`; `/opt` so the dev bind mount on `/app` can't hide it).
- **Required env vars:** `APIFY_PROXY` (proxy password)
- **Optional env vars:** `REDIS_URL` (cache; read from the process env by `cache_service` — the lifespan bridges a `.env`-file value into `os.environ`), `SERVICE_NAME` (Redis client name, set in docker-compose), `REDIS_MAX_CONNECTIONS`/`REDIS_SOCKET_TIMEOUT_S`/`REDIS_SOCKET_CONNECT_TIMEOUT_S`/`REDIS_HEALTH_CHECK_INTERVAL_S` (pool tuning, defaults 20/10/5/30), `REDIS_RECONNECT_INTERVAL_S` (default 30 — lifespan retry loop re-runs `init_redis_pool()` while the pool is down, so Redis unavailable at boot heals without a restart)

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
| `POST` | `/api/v1/detect-batch` | Batch detection (max 100 URLs, 2-pass parallel+retry, first_match mode). Sync; shares `_run_batch_core` with the async worker. |
| `POST` | `/api/v1/detect-batch-async` | Submit a batch async → `202 {job_id}` (or `200` on idempotent re-submit). Poll-based; decouples callers from the gateway 180s ceiling. |
| `GET`  | `/api/v1/detect-batch-async/{job_id}` | Poll an async job: `pending\|running\|completed\|failed\|stale`; `results` populated when terminal; `404` when unknown/expired. |
| `GET`  | `/api/v1/check-url` | URL-only check (no HTML fetch) |
| `POST` | `/api/v1/detect-debug` | Debug mode with full pipeline trace (fetch, cleaning, URL, HTML, NLP, alternatives, decision) |
| `GET`  | `/api/v1/health` | Health check |

### Async Batch Job API (`/detect-batch-async`)

In-process asyncio worker + Redis job store (`app/core/async_jobs.py`), wired via a FastAPI `lifespan` in `main.py` (`app.state.job_manager`). The worker reuses the same `_run_batch_core` as the sync `/detect-batch` (DRY) and the shared prod admission pool — **crawler-service is immune** because it passes `html_content` (bypasses admission).

**Jobs execute from a FIFO queue** (spec `2026-07-19`): submits are enqueued and consumed by `JOB_WORKER_CONCURRENCY` workers (default **1** = serialized — each job gets the whole browser pool instead of sharing it with up to 7 others, which caused the 300s-timeout storms). `MAX_ACTIVE_JOBS` keeps its exact meaning: cap on **pending+running** (503 + Retry-After beyond). A queued job polls as `pending` — a keeper task refreshes its `last_activity` every `HEARTBEAT_INTERVAL_S` so it never falsely derives `stale`; after a crash/restart the keeper is gone and queued records go `stale` normally (fail-fast contract unchanged). Shutdown drains the queue: never-started jobs are marked `failed(service_shutdown)` like running ones.

- **Submit** (`POST /detect-batch-async`, body = `AsyncBatchSubmitRequest`): `202 {job_id, status, total, poll_after_seconds}`. With `client_job_id` set, a re-submit returns the existing job (`200`, atomic `SET NX` idempotency) — but ONLY while that job is alive (`pending`/`running` non-stale) or `completed`; a `failed`/stale/expired target releases the index and the re-submit starts a NEW job (`202`) per the fail-fast contract (before: the index served the dead job for up to 1h — a BO re-launch polled a `failed` corpse and stopped).
- **Poll** (`GET /detect-batch-async/{job_id}`): `AsyncBatchStatusResponse`. `stale` is computed on read (heartbeat older than `STALE_THRESHOLD_S` → dead worker, e.g. OOM restart).
- **Terminal-write hardening** (2026-07-26 incident, job `9597267b`): the heartbeat is stopped **cooperatively** via an `asyncio.Event` (never `cancel()` mid-Redis-command — a cancelled command can poison the pooled connection that the terminal get/write then reuse), and the terminal record write is **retried 3× with backoff** and logs loudly (`écriture terminale PERDUE`) if all attempts fail. Before this, a finished batch could silently stay `running` (frozen heartbeat copy: `done=N`, `results=null`) until `stale`, discarding all its work.
- **503 differentiation:** capacity (`MAX_ACTIVE_JOBS` reached) → `Retry-After` header set (`retryable:true`); kill-switch (`ASYNC_JOBS_ENABLED=false`) or Redis-unavailable → **no `Retry-After`** (`retryable:false`). Callers key off the header presence.
- **Restart = fail-fast:** no resume. Stale/failed jobs are re-enqueued by the caller (BO `domaine_fr_retry`). Graceful shutdown marks running jobs `failed(service_shutdown)`.
- **Redis required for async** (cache stays optional): if `REDIS_URL` is unset/unreachable, submit returns `503`; sync endpoints are unaffected.
- **TTL invariant:** `JOB_RESULT_TTL_S < JOB_TTL_ACTIVE_S`; callers must poll within `JOB_RESULT_TTL_S`.
- Metrics: `detect_async_jobs_submitted_total`, `detect_async_jobs_active` (reserved = pending+running), `detect_async_jobs_queued` (FIFO depth), `detect_async_jobs_terminal_total{status}`, `detect_async_job_duration_seconds`, `detect_async_job_capacity_rejected_total`. Per-item async fetches reuse `ADMISSION_REJECTED{endpoint="/api/v1/detect-batch-async"}`.

| Variable | Default | Purpose |
|---|---|---|
| `ASYNC_JOBS_ENABLED` | `true` | Kill switch for the async job API (`false` → submit 503, not retryable). |
| `MAX_ACTIVE_JOBS` | `8` | Max **pending+running** async jobs (capacity 503 + `Retry-After` beyond this). |
| `JOB_WORKER_CONCURRENCY` | `1` | Jobs executing simultaneously; the FIFO queue absorbs the rest up to `MAX_ACTIVE_JOBS`. |
| `JOB_TTL_ACTIVE_S` | `7200` | TTL of a pending/running job record (refreshed by heartbeat). |
| `JOB_RESULT_TTL_S` | `3600` | TTL of a terminal job record (poll window). |
| `STALE_THRESHOLD_S` | `120` | No-heartbeat window after which poll reports `stale`. |
| `HEARTBEAT_INTERVAL_S` | `5` | Wall-clock heartbeat tick. |
| `ASYNC_SUBMIT_RETRY_AFTER_S` | `15` | `Retry-After` value on capacity 503. |
| `ASYNC_POLL_HINT_MAX_S` | `30` | Upper bound on the server `poll_after_seconds` hint. |
| `SHUTDOWN_GRACE_S` | `5` | Bound on `JobManager.shutdown()` task drain. |

Spec: `docs/superpowers/specs/2026-06-01-detection-langue-fr-async-job-api-design.md`. Plan: `docs/superpowers/plans/2026-06-01-detection-langue-fr-async-job-api.md`.

## Detection Pipeline

1. **Cache Redis** — Lookup by normalized domain. TTL: 30d (ok=true), 7d (ok=false definitive), 6h (transient failures). Bypass via `force_refresh=true`.
2. **Fetch HTML** — Playwright headless via Apify proxy. 3 retries (auto rotation) + conditional fallback URL variants (http/https, www/sans-www) — see "URL-Variant Fallback Gate" below.
3. **Page validation** — Classifies the fetched page: `valid` / `http_error` (4XX/5XX) / `soft_404` (200 OK + body looks like "page not found") / `redirected_to_home` (deep path 302'd to root). Invalid → optional one-hop homepage fallback.
4. **Challenge detection** — Identifies Cloudflare, DataDome, Squid, Imperva, Rescaled WAF, generic JS proof-of-work "Bot check" gates, HTTP 4XX/5XX error pages. The scraper polls up to 45s for auto-resolving challenges; on resolution the `ScrapeResult.status_code` is forced to 200 (the initial goto's 401/403 is stale after the post-solve navigation).
5. **URL analysis** — TLD `.fr` (strong signal), `/fr/` path, `lang=fr` query, `fr.` subdomain.
6. **HTML tags** — `<html lang>`, `<meta og:locale>`, `<meta name=LANGUAGE>`, `<meta http-equiv=content-language>`.
7. **NLP** — fastText primary → langdetect+langid cross-check when uncertain. Cookie consent banners stripped before analysis. `clean_html_to_text` has a noscript-repair fallback: if the cleaned text is < `NLP_MIN_TEXT_LENGTH` on a > 20KB page (symptom of an unclosed nested `<noscript>` swallowing the body — LiteSpeed Cache wrapping GTM's noscript, cf. outilbox.fr), it re-cleans once with noscript *unwrapped* instead of decomposed.
8. **Alternative links** — hreflang, data-lang, data-gt-lang, `/fr/` links, option tags, plus a last-resort lang-substitution probe (zero-candidate pages only: declared lang token in self-referencing canonical/hreflang URLs substituted with `fr`, e.g. `/home-page-it` → `/home-page-fr`; method `lang_substitution`). Sorted by reliability (high/medium/low), validated via HTTP. A candidate whose redirect chain lands on a DIFFERENT page that turns out to be the page under analysis is a dead switcher link: before rejecting it, a **sitemap rescue** reads the candidate's `/sitemap_index.xml` (or `/wp-sitemap.xml`) and substitutes the first same-host inner page — apex-only redirect misconfigurations (metaga.fr: `/` 301s to metaga.es but `/contact/` serves `lang=fr-FR`) hide live French sites behind "dead" roots (method suffix `_sitemap`). Cookie switchers (`/?lang=fr` → 302 back to same host+path) are exempt — they are judged on content. `Check_nok_v2` (Case 9) deliberately keeps `alternative_urls` empty: crawler `routes.ts` + BO `not_french_signal.php` treat "ok=false + non-empty alternatives" as a distinct signal from not_french; diagnosis lives in `/detect-debug`'s `debug.alternatives`.
9. **Decision matrix** — 9 cases combining URL/HTML/NLP signals with confidence scores.

### URL-Variant Fallback Gate

Phase 2 (http/https, www/sans-www variants) is skipped only when **every** retry attempt failed pointless-for-variants (`Timeout` or `Contenu vide ou trop court`) — a variant can't fix a slow/empty page. A single non-pointless attempt, even infra noise, re-enables all variants (safe-direction cost). **Accepted loss:** an apex that *times out* but whose `www`/`http` variant would have answered is no longer rescued — a timeout is far more often a dead/slow site than a variant-fixable misconfiguration. Skip is logged as `[VARIANTES] ignorées ... (saw_repairable=False)`.

**Post-verdict rescue (`+variant_rescue`).** The gate above only ever engages on a fetch that **fails**. A fetch that **succeeds** but yields an unusable verdict (`Check_nok_v2`, `fetch_empty_content`) never reaches Phase 2 at all — the URL form under test stays locked in, even though this is exactly the case a variant can repair: a redirect to the real site that only exists on `http` (groupe-denis.com → ibyd.fr) or on the apex (rgb-solutions.green). `_variant_rescue` (`app/api/routes.py`) re-probes the http/https and www/apex forms of the URL *after* the decision matrix has run — the only point where verdict and requested URL coexist. **One** `scrape_html` probe per variant, never the retry cascade, with `validate_alternatives=False` hardcoded so the Case-6 alternative-confirmation loop can't open extra browsers outside the rescue budget (same probe pattern as the Case-6 confirmation probe, `domain_fr.py:1460-1463`). The first variant whose analysis yields `ok=True` wins; its `method` is suffixed `+variant_rescue` and `analyzed_url` carries the retained URL — observable in the BO report with zero BO-side change.

Every other outcome — no variant, a failed or timed-out probe, ANY exception during a variant's analysis, an invalid page, a challenge page, no French variant — leaves the original verdict **unchanged**. It is deliberately never turned into a timeout: that would degrade a `Check_nok_v2` into `method='error'`, which Pass 2 does not retry and which carries no cause — worse than the false negative the rescue exists to fix. Never triggers when the caller supplied `html_content`: **crawler-service is immune**.

*Effective budget.* `VARIANT_RESCUE_BUDGET_S` (default `120`, `0` disables) is not the whole story. The budget actually used is `min(VARIANT_RESCUE_BUDGET_S, _ITEM_WALL_CLOCK_S - elapsed_s - _RESCUE_MARGIN_S)`: `_ITEM_WALL_CLOCK_S` (`300`) is the same per-item ceiling already enforced by the four batch `wait_for()` calls (one constant now backs all four literals); `elapsed_s` is what this item has already spent before the rescue is even considered (primary fetch + validation + stub-hop); `_RESCUE_MARGIN_S` (`15`) is headroom left so the rescue finishes comfortably before the caller's own 300s `wait_for` fires — without it, an item already close to the ceiling would be pushed over by the rescue itself. Before probing each variant, the loop also checks that at least `_MIN_PROBE_S` (`30`) remains and stops if not — below that a probe is more likely to be cancelled mid-navigation than to answer, the exact condition for the orphaned Playwright protocol callbacks documented at `domain_fr.py:1451-1459`; above it, each probe's own timeout is exactly whatever remains, not a fixed constant, so one slow variant can't overrun the budget by itself. **Consequence for tuning:** raising `VARIANT_RESCUE_BUDGET_S` has no effect once an item is already near the 300s ceiling — the remaining-headroom cap silently wins.

*Page-validation guard.* Each probed variant is re-validated with `validate_page` (gated on `INVALID_PAGE_DETECTION_ENABLED`) before its verdict is accepted, mirroring the check the primary fetch runs. This is deliberate, not incidental: without it, a variant serving a French 404 / soft-404 / redirect-to-home page could turn a rescue into a false **positive** — the wrong direction to open in a chantier whose entire point is fewer false negatives.

*Known limits:*
- The rescued response's `url`/`analyzed_url` becomes the retained variant's **final** URL, which on the motivating case is a **different domain** (groupe-denis.com → ibyd.fr). This mirrors the existing homepage-fallback precedent (cache key stays the original domain, `analyzed_url` carries the target) — but it is the same shape as a cross-domain result-pairing bug previously fixed on the BO side. Verify what BO callers do with a cross-domain `analyzed_url` before trusting this path silently.
- A `Check_nok_v2` produced through the **homepage-fallback branch** (the fallback's own `check_page_if_french` call, which returns before `[4]`/`[4bis]` run) gets **no rescue** — same false-negative class, outside this chantier's single insertion point. Documented as a known limit, not fixed here.

Metric: `detection_variant_rescue_total{outcome=success|budget_exhausted|no_variant_french}` — only recorded once the probe loop is entered. The two early returns before the loop (budget `<= 0`, or `_generate_url_variants` producing no variants) increment no label at all, so a kill-switch-off rescue and a URL with no variant forms are both invisible to this counter, not counted under any outcome.

## Lexical-Signal Observation at Case 9 (inert)

`_count_french_exclusive_distinct` (`app/services/language_detector.py`) publishes into `details` the number of **distinct** exclusively-French words found in the analyzed text — a discriminant deliberately kept separate from the existing aggregate score, `_compute_french_signal`.

**Why the aggregate cannot be used as a discriminant.** Re-measured 2026-08-10 against the repo's own samples (`tests/test_lexical_observation.py`), by the implementer and the reviewer independently, with an exact match between the two:

| Sample | `french_signal` (aggregate) | exclusive distincts |
|---|---|---|
| FR (prose) | 1.000 | **8** |
| ES (prose) | 0.833 | 0 |
| PT (prose) | 0.814 | 1 (`mais`) |
| IT (prose) | 0.417 | 0 |
| EN (prose) | 0.000 | 0 |
| FR catalogue (no prose) | 0.000 | 0 |

The aggregate **saturates** and cannot discriminate — Spanish sits at 0.833, well above the `> 0.3` floor Case 8 reads — while the distinct count separates cleanly. These are the figures to trust; the spec's §3 table used non-reproducible extracts (see the 2026-08-10 correction note appended to that section).

At Case 9, once the count reaches `LEXICAL_OBSERVATION_MIN_DISTINCT`, a diagnostic is written into `error` (`"lexical: N mots exclusifs distincts — rattrapage candidat"`). **The verdict never changes**: `ok=False`, `method='Check_nok_v2'`, exactly as before this chantier.

**Why inert.** The motivating false negative (automatismes.net — clean French prose, no `html lang`, no hreflang, no distinctive TLD, fastText confidently wrong) never reaches Case 8: its guard `soft_from_fasttext` requires that fastText itself said `fr`, which it didn't here. Widening that guard needs a threshold, and the only evidence for one so far is six short samples. `LEXICAL_OBSERVATION_MIN_DISTINCT=3` is an **observation** threshold — deliberately permissive, meant to surface borderline cases — distinct from the **activation** threshold under consideration (5), which is **not implemented**.

**Three limits to know:**
- `mais` is in `FRENCH_EXCLUSIVE_STOPWORDS` but is ordinary Portuguese — which is why a threshold of 1 would be wrong (Portuguese alone scores 1, on that word).
- A French page **without prose** (a bare product/brand catalogue) scores 0 — this mechanism can only ever rescue pages that contain written text.
- The count only exists when an NLP verdict ran: `exclusive_distinct` is read out of `nlp_result['details']`, which is absent when NLP itself was unavailable. A Case 9 reached because NLP never ran publishes no count and carries no diagnostic — the census of "`Check_nok_v2` with a lexical note" therefore covers only the NLP-available subset of Case 9, not all of it. Sizing the activation threshold off that census without accounting for this undercounts the NLP-unavailable population.

Spec: `docs/superpowers/specs/2026-08-10-detection-faux-negatifs-design.md` (§3's 2026-08-10 correction note carries the re-measurement).

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
4. **Browser semaphore** caps concurrent Camoufox/Chromium instances at `BROWSER_SEMAPHORE_SIZE` (default 10; compose deploys 6 after an OOM incident — see docker-compose comment).
5. **Server-side batch-concurrency clamp** (spec `2026-07-19`): `_run_batch_core` clamps the requested `max_concurrency` to `ADMISSION_MAX_SLOTS` for any batch containing fetch items — a request above the pool size would structurally bounce the excess as `admission_rejected` on every wave. Batches that are 100% `html_content` (crawler-service) are NOT clamped (they never touch admission).

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

Method values surfaced in `DetectionResponse.method` when the requested page is rejected:

| Method | Meaning | Cache TTL | Retryable? |
|---|---|---|---|
| `http_error` | Definitive 4XX (404, 410, …) | 7 days | No — definitive |
| `http_error_transient` | 401/403/407/408/425/429/5xx **without** a challenge body — fetch conditions (WAF/auth/rate-limit/server incident), not a page property | 6 hours | Yes (batch Pass 2) |
| `soft_404` | 200 OK but body matches not-found heuristic (title/H1 regex + thin content, or URL path 404 marker) | 6 hours | No |
| `redirected_to_home` | Requested non-root path, server redirected to `/` | 7 days | No |

A 4xx/5xx whose **body** is a WAF/challenge page (Cloudflare, DataDome, …) is classified `challenge_page` (retryable), not `http_error` — the raw status check does not win over challenge detection. The generic `HTTP_xxx_blocked` verdict (thin error page) does NOT trigger this reclassification: a real thin 404 stays `http_error`.

Callers should treat `http_error`, `soft_404`, `redirected_to_home` as definitive failures (do NOT retry); `http_error_transient` may be retried later (the 6h cache absorbs immediate re-asks).

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
| `STUB_PAGE_HOP_ENABLED` | `true` | One-hop follow of stub pages (meta-refresh or lone same-host link, visible text < `NLP_MIN_TEXT_LENGTH`) instead of rejecting them as `fetch_empty_content`. Never recursive; on hop-fetch failure the stub content flows on. `analyzed_url` discloses the hop target. |
| `VARIANT_RESCUE_BUDGET_S` | `120` | Total clock budget for the post-verdict variant-rescue probes (`_variant_rescue`), checked BEFORE each variant and further capped by the item's remaining headroom under `_ITEM_WALL_CLOCK_S` (see "URL-Variant Fallback Gate"). Exceeded → original verdict unchanged. `0` disables (kill-switch). Default is an **estimate**, not measured on the VM. |
| `LEXICAL_OBSERVATION_MIN_DISTINCT` | `3` | Threshold of distinct exclusively-French words at or above which Case 9 writes a diagnostic into `error` (`>=`, inclusive). Observation only — no verdict depends on it. `0` disables (kill-switch). |

### Endpoint behavior

| Endpoint | Validate? | Homepage fallback? |
|---|---|---|
| `/detect` | Yes | Yes (default ON) |
| `/detect-batch` (all modes) | Yes | Yes (default ON, per item) |
| `/detect-debug` | Yes (overrides result.ok / result.method / result.error if non-VALID — pipeline trace preserved; mirrors the prod challenge-wins/transient reclass so debug reports `challenge_page`/`http_error_transient` like `/detect` would; `debug.fetch.status_code` records the raw HTTP status) | **OFF** (debug shows requested URL's actual pipeline state) |
| `/check-url` | N/A (no HTML fetch) | N/A |

Batch Pass 2 retry set (`_PASS2_RETRYABLE_METHODS`): `fetch_failed`, `challenge_page`, `admission_rejected`, `http_error_transient`, `fetch_empty_content`. Pass-2 retries run with `force_refresh=True` (the Pass-1 transient rejection was just cached 6h and would short-circuit the retry via cache HIT) and are bounded by the same 300s per-item `wait_for` as Pass 1. Definitive verdicts (`http_error`, `soft_404`, `redirected_to_home`) are NOT retried — page properties that don't change between passes. `error` (incl. `Timeout global item (300s)`) is deliberately NOT retried either: a timed-out item already consumed 300s of work inside the same saturated batch; the fix for timeouts is throughput (async job API) + caller re-run. Spec: `docs/superpowers/specs/2026-07-18-detection-langue-fr-transient-error-retry-design.md`.

### Metrics

- `detection_validation_verdicts_total{verdict}` — counter, label values: `valid`, `http_error`, `soft_404`, `redirected_to_home`.
- `detection_homepage_fallback_triggered_total{outcome}` — counter, label values: `success`, `rejected`, `network_failure`.
- `detection_orphaned_protocol_futures_total` — counter, no labels. Orphaned Playwright protocol callbacks drained by the loop exception handler in `main.py` (a cancelled scrape leaves `page.goto`'s callback pending; `Connection.cleanup()` sets `TargetClosedError` on it and nobody can retrieve it). **A value of zero is ambiguous** — it is consistent both with "no orphans occurred" and with "the handler is not installed"; pair it with checking that `Future exception was never retrieved` is absent from the log.

## Fetch Failure Detail (`failure_detail`)

Optional field on `DetectionResponse` (`app/models/schemas.py:113-118`), format
`"<stage>: <cause>"`. **No classification**: `cause` is the engine's own error message
(first line only), truncated to `FAILURE_CAUSE_MAX_LEN` = 200 chars
(`app/services/scraper.py:147`) — never a guessed label.

`_record_failure` (`app/services/scraper.py:150-167`) writes into an `error_sink` dict
supplied by the caller, first-writer-wins (a navigation error is the root cause of the
"content too short" that follows it in the same call, so it must not be overwritten).
`_format_failure_detail` (`app/api/routes.py:82-87`) turns that sink into the publishable
string, or `None` if nothing was captured — called at the two `fetch_failed` response
sites, `/detect` (`app/api/routes.py:219`) and `/detect-debug` (`:880`).

| `stage` | Set at | Trigger |
|---|---|---|
| `runtime` | `scraper.py:424` | Playwright not installed (`ImportError`) |
| `proxy` | `scraper.py:427-437`, `redirect_tracker.py:244` | Proxy missing or unparseable — **the proxy value itself is never published** (`scraper.py:435-436`): it carries a password |
| `navigation` | `scraper.py:479` (the `except` branch around `page.goto`) | `page.goto` raised |
| `content` | `scraper.py:598` | Page fetched but body empty or ≤100 chars |
| `browser` | `redirect_tracker.py:56` (`_derive_failure`) | Failure outside the 4 instrumented points above — browser launch (`scraper.py:442`), `new_context` (`:457`), `new_page` (`:463`), etc. The sink never got a `cause`, so `_derive_failure` falls back to this stage from the raw exception, still never analyzing its text |

`stage` always comes from the **call site** in the code — the literal argument passed to
`_record_failure`, or the hardcoded fallback in `_derive_failure` — never from parsing
`cause`'s text. That is what guarantees no error label is presupposed.

**The three Chromium error-code lists stay dead, on purpose.** Two of them are real
Chromium `ERR_*` strings that the deployed engine (Camoufox/Firefox,
`CAMOUFOX_ENABLED=True` by default, `app/core/config.py:30`) never emits, so the
membership tests that consult them never match in production: `_PERMANENT_NAV_ERRORS`
(`scraper.py:137-142`) and `_VARIANT_ELIGIBLE_ERRORS` (`redirect_tracker.py:13-17`). The
third, `_FATAL_ERRORS` (`redirect_tracker.py:20-24`), is not actually a Chromium list —
it holds this service's own French config-error strings (`'Proxy obligatoire'`, …) — but
it is dead for a different reason: `scrape_html` never raises with those messages on a
proxy failure, it returns `None` instead (`scraper.py:427-437`), so the `except`-branch
check that reads it (`redirect_tracker.py:295`) is never reached that way. Repairing any
of the three on a guessed label is exactly the failure mode this chantier avoids —
harvesting the real labels is a manual procedure: spec
`docs/superpowers/specs/2026-08-06-detection-failure-cause-and-retire-proposal-design.md`
§6.

**Never cached on `fetch_failed`.** `fetch_failed` is in `DomainCache._NEVER_CACHE_METHODS`
(`app/core/domain_fr.py:53`, enforced at `:113`): the whole response — `failure_detail`
included — is never written to Redis for that method.

**Known limits:**
- Under `INFLIGHT_DEDUP_ENABLED` (`app/api/routes.py:91`, default `true`), only the
  *leader* for a given URL runs the fetch and fills the sink; a *follower* waiting on the
  same coalesced result gets `failure_detail=None` (`app/api/routes.py:211-220`).
- The field is not produced for the homepage-fallback network failure
  (`app/api/routes.py:270-295` — `_fetch_with_admission` is called there without
  `error_sink`) nor for the stub-page hop (`:359-382`, same omission) — out of scope for
  this chantier (spec §3).
- Across a multi-attempt fetch, the published cause is the **last** attempt tried, not
  the root cause. `last_failure` is unconditionally reassigned on every Phase 1 retry
  (`redirect_tracker.py:278`, `:289`) and every Phase 2 URL-variant attempt (`:360`,
  `:362`), and only that final value reaches `_publish_failure` (`:335`, `:373`) — by
  design, last-non-empty-attempt wins, there is no aggregation across attempts. So if
  attempt 1 hits a real `navigation`/`proxy` cause but a later retry or variant ends in
  the generic "content too short" (`scraper.py:598`), that generic message is what gets
  published, not the earlier, more informative one. A `failure_detail` read off a
  multi-attempt fetch is the last attempt's story, not necessarily the whole one.

## Alternative-URL Validation Skip (`validate_alternatives`)

`validate_alternatives: bool = true` on `DetectionRequest`, `BatchDetectionRequest`, and `AsyncBatchSubmitRequest` (threaded via `BatchOpts`). When **false**, COMPLETE-mode detection still **parses** alternatives from the HTML but performs **zero HTTP/browser work** on them:

- skips the httpx Phase-1 + Phase-2 browser validation (`_validate_alternative_urls` → `scrape_html`),
- skips the Case-6 browser NLP-confirmation loop (a single `scrape_html` probe per validated alt, not a retry cascade).

Returned alts: hreflang → `validated:true` (trusted declaration, unchanged); medium (`data-lang`/`link`/`option`) → `validated:false, reliability:'low'`. Default **true** ⇒ existing callers (BO) keep full validation.

**Why:** `crawler-service` sends `html_content` for the homepage in `complete` mode; the alt-validation browser opens (not the initial page) were the residual OOM / `socket hang up` source. Setting `validate_alternatives=false` removes them while preserving the hreflang prefixes the crawler's Regional Path Exclusion consumes.

**Deliberate behavior change (flagged calls only):** a site whose provided homepage content is not NLP-confirmed French but exposes an NLP-confirmable French alternative previously returned `ok=true` via Case 6; with the flag off it returns `ok=false` (falls through to Case 7/9). `/detect-debug` **ignores** the flag (always validates, to show the full pipeline).

Metric: `detection_alt_validation_skipped_total` (no labels) — increments once per flagged skip with ≥1 candidate.

## Dependencies on Other Services

No other microservice. Uses `libs/common-utils` for the shared Redis pool (`common_utils.redis.cache_service`). Requires Apify proxy (`APIFY_PROXY` env var). Optionally uses Redis for caching (`REDIS_URL` env var; required for the async job API).
