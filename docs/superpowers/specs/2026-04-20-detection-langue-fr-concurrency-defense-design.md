# api-detection-langue-fr — Concurrency Defense Design Spec

**Date:** 2026-04-20
**Status:** Draft (pending user review)
**Author:** Rindra + Claude

## Problem Statement

The `api-detection-langue-fr` service (port 8999, Camoufox-primary + Chromium-fallback via Playwright) shows warning signs under concurrent load from its two known callers (`crawler-service` and `api-gateway`-relayed traffic):

- **Memory/CPU growth** — container RAM climbs during sustained load; occasional OOM pressure
- **Playwright `TargetClosedError` flood** — the resource-blocking `_route_handler` in `scraper.py` fires on already-closed pages because `scrape_html` never calls `page.unroute_all(behavior='ignoreErrors')` before `context.close()`. Under load this is amplified: more in-flight route callbacks → larger error cascade → accumulating unhandled coroutine references (silent memory leak)
- **Event-loop starvation** — observed in api-gateway logs as "Failed to fetch schema" ×4 from `/openapi.json` (a trivial endpoint that never touches Playwright). Proves the single Uvicorn worker was saturated and couldn't respond to anything

**Root causes identified in code:**

1. **Browser lifecycle is per-request, never reused.** Every `scrape_html` call does `async_playwright()` → `_launch_browser()` → `close()`. Camoufox cold start can take up to 45s under load before falling back to Chromium. Amortized per fetch = huge overhead.
2. **Recursive browser acquisition on alternative URLs.** When `DomainFR` finds validated alternative French URLs, `check_page_if_french` calls `fetch_html` again per alternative (up to 3 × 120s timeout each). One `/detect` call can hold browser slots sequentially for 200s+.
3. **No inflight deduplication.** Five callers asking for the same URL in a 30s window = five independent browser launches. The Redis cache only fills after the first completes.
4. **No cross-request admission control.** FastAPI accepts unlimited concurrent requests. All pile onto `_BROWSER_SEMAPHORE(10)`. The queue grows in memory with no signal to callers that the service is saturated.
5. **No caller-side discipline.** Both known callers lack timeouts matched to the service's behavior, lack retry logic for transient saturation, and lack per-caller concurrency caps.
6. **No resource ceilings in Docker.** No `mem_limit`, no `cpus`, no healthcheck — a misbehaving container has no automatic circuit breaker.

**Critical caller findings:**

- `crawler-service` calls `/detect` **per-URL** (not `/detect-batch`), with 120s axios timeout, **no retry logic, no concurrency cap**. Bound only by its own `MAX_CONCURRENT_CRAWLS ~10` — one crawler instance can already saturate the detection service.
- `api-gateway` is a transparent proxy with `timeout=None` (infinite) on its `httpx.AsyncClient`. When detection hangs, the gateway hangs, which cascades to the gateway's callers.

## Goals

- **Fast-fail instead of hang** under saturation — callers must get an actionable signal (503 + Retry-After) within milliseconds, not timeout after 120–300s
- **Bounded resource usage** — container-level memory and CPU ceilings so a misbehaving process is circuit-broken rather than dragging the host down
- **No cascading failures** — when detection is overloaded, `/health`, `/openapi.json`, and other trivial endpoints must continue to respond
- **Reusable caller contract** — a documented, shared pattern (env vars + helper module) that current and future callers adopt to call this service responsibly. Directly supports the user's stated goal of applying the pattern to other services.
- **Observable ceilings** — Prometheus metrics that make saturation, dedup effectiveness, and browser-launch cost visible. Data-driven decision for any future Approach 3 refactor.
- **Preserve detection quality** — no changes to the detection decision matrix, NLP pipeline, challenge detection, or alternative-URL discovery. This spec is about defense, not logic.

## Non-Goals

- Browser pool / warm reuse (risks breaking Camoufox per-session fingerprinting; requires a separate investigation)
- Queue-based worker refactor (large blast radius; API contract shift to async submit+poll)
- Horizontal scaling (stays single-replica with 1 Uvicorn worker)
- Redis-backed admission slot pool (keeping it in-process for now; can migrate later if horizontal scaling is adopted)
- Timeout fixes on gateway downstream calls other than `api-detection-langue-fr-service` (risks breaking services that legitimately need long timeouts; out of scope)
- Grafana dashboard (metrics endpoint is the deliverable; dashboard is a follow-up)

## Architectural Overview

Three layers of defense, each independently valuable and reversible:

```
┌─── Caller layer (C) ─────────────────────────────────────────────┐
│                                                                  │
│   libs/common-utils/detection_client.py              [NEW]       │
│     • Per-instance Semaphore capped at DETECTION_MAX_CONCURRENCY │
│     • 503-aware retry wrapper honoring Retry-After               │
│     • Used by any current or future Python caller                │
│                                                                  │
│   api-gateway/main.py                                [MODIFY]    │
│     • Per-service timeout map — detection=180s                   │
│     • All other services unchanged (timeout=None preserved)      │
│     • 503 pass-through with Retry-After header                   │
│                                                                  │
│   crawler-service/DetectionLangueClient.ts           [MODIFY]    │
│     • p-limit (or existing concurrency lib) capping /detect      │
│     • 503 → parse Retry-After → wait → retry (max N)             │
│     • axios timeout aligned to DETECTION_REQUEST_TIMEOUT_S=180   │
│                                                                  │
├─── Container layer (B) ──────────────────────────────────────────┤
│                                                                  │
│   docker-compose.yml (api-detection-langue-fr-service)           │
│     • mem_limit: 4500m                                           │
│     • cpus: 4                                                    │
│     • healthcheck: curl /api/v1/health (interval 30s, timeout 10s)│
│     • restart: unless-stopped (unchanged)                        │
│     • Uvicorn --limit-concurrency=50 (hard ceiling)              │
│                                                                  │
├─── In-service layer (A) ─────────────────────────────────────────┤
│                                                                  │
│   scraper.py                                         [MODIFY]    │
│     • page.unroute_all(behavior='ignoreErrors') before close     │
│     • Browser lifecycle in try/finally                           │
│     • BROWSER_SEMAPHORE_SIZE env-configurable                    │
│                                                                  │
│   app/middleware/admission.py                        [NEW]       │
│     • Global atomic counter + 503+Retry-After when saturated     │
│     • Separate slot budget for /detect-debug                     │
│                                                                  │
│   app/core/inflight_dedup.py                         [NEW]       │
│     • Coalesce concurrent fetches of same URL to one             │
│     • TTL-based, in-process only                                 │
│                                                                  │
│   app/core/metrics.py                                [NEW]       │
│     • Prometheus histograms + counters + gauges                  │
│     • /metrics endpoint exposed                                  │
│                                                                  │
│   apps-microservices/api-detection-langue-fr/CLAUDE.md [MODIFY]  │
│     • Fix stale "Playwright (Chromium)" — Camoufox is default    │
│     • Document new env vars                                      │
│     • Reference caller contract                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## In-Service Layer (A) — Detailed Design

### A.1 Route handler leak fix (`scraper.py`)

Two changes in `scrape_html`:

1. **Wrap the entire browser lifecycle in `try/finally`.** Currently, an exception mid-request leaks the browser entirely because `context.close()` / `browser.close()` only run on the happy path (e.g., the navigation error re-raise for permanent errors already does this explicitly; other exception paths do not).
2. **Call `await page.unroute_all(behavior='ignoreErrors')` before `context.close()`.** This is Playwright's documented way to drain in-flight route callbacks. Suppresses the `TargetClosedError` flood on teardown.

Make `_BROWSER_SEMAPHORE` size env-configurable via `BROWSER_SEMAPHORE_SIZE` (default 10). Ops can tune without redeploy.

Applies to both `scrape_html` and `scrape_html_with_redirects` (same pattern).

### A.2 Admission control middleware (`app/middleware/admission.py` — NEW)

**Design choice: non-blocking counter, not bounded-wait.** We want fast-fail, not deeper queuing. At `max_inflight` already, a new request returns 503 + `Retry-After` immediately, without waiting.

```
class AdmissionController:
    _counter: int = 0
    _max: int
    _lock: asyncio.Lock

    async def acquire() -> bool:  # returns False if rejected
    async def release() -> None:

# Middleware flow:
# 1. Pick controller based on request path:
#      - /api/v1/detect-debug          → debug_controller
#      - /api/v1/{detect,detect-batch,check-url} → prod_controller
#      - other paths (/, /health, /metrics, /openapi.json, /docs) → no middleware
# 2. if not await controller.acquire(): return 503 + Retry-After
# 3. try: response = await call_next(request)
#    finally: await controller.release()
```

**Two separate controllers:**
- **Production:** `ADMISSION_MAX_SLOTS` (default 12). Covers `/detect`, `/detect-batch`, `/check-url`.
- **Debug:** `ADMISSION_DEBUG_SLOTS` (default 2). Covers `/detect-debug`. Isolated so dev calls never starve production.

**Rationale for max=12 (not 10):** semaphore allows 10 Camoufox browsers; 2 extra request-slots = brief headroom for requests already past admission control but waiting on the browser semaphore. Tighter than that and transient bursts are rejected unnecessarily.

**Retry-After value:** static, env-configurable `ADMISSION_RETRY_AFTER_SECONDS` (default 30). Migration to dynamic (p95-based) computation is a follow-up once metrics have 2–4 weeks of production data.

**Kill switch:** `ADMISSION_ENABLED` (default `true`). When `false`, middleware is a no-op.

### A.3 Inflight URL dedup (`app/core/inflight_dedup.py` — NEW)

Purpose: coalesce concurrent requests for the same URL to a single fetch. **Not a cache** — only lives for the duration of the in-flight fetch.

```
_inflight: dict[normalized_url, asyncio.Future]

async def coalesce(url: str, fetch_coro: Callable[[], Awaitable[T]]) -> T:
    if url in _inflight:
        return await _inflight[url]          # hit: wait on existing
    fut = loop.create_future()
    _inflight[url] = fut
    try:
        result = await fetch_coro()
        fut.set_result(result)
        return result
    except Exception as e:
        fut.set_exception(e)                 # propagate to all waiters
        raise
    finally:
        _inflight.pop(url, None)
```

**Integration:** wraps the `fetch_html` call inside `_detect_single_url` in `routes.py`, keyed by normalized URL (lowercase host + path). **Skipped when `force_refresh=True`** (user explicitly wants a fresh fetch).

**Normalization:** same as `DomainCache._normalize_domain` but includes path (not just domain), to avoid over-coalescing different pages of the same domain.

**Kill switch:** `INFLIGHT_DEDUP_ENABLED` (default `true`).

### A.4 Metrics (`app/core/metrics.py` — NEW)

Using `prometheus-client` (platform standard per project CLAUDE.md). Exposed at `/metrics` via FastAPI route.

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `detect_request_duration_seconds` | Histogram | endpoint, status | End-to-end request duration distribution |
| `detect_browser_launch_duration_seconds` | Histogram | browser (camoufox\|chromium) | Cost of browser cold-start |
| `detect_admission_rejected_total` | Counter | endpoint | 503s emitted by admission middleware |
| `detect_dedup_hits_total` | Counter | — | Number of coalesced duplicate fetches |
| `detect_inflight_requests` | Gauge | — | Current concurrent admitted requests |
| `detect_browser_semaphore_waiters` | Gauge | — | Queue depth on `_BROWSER_SEMAPHORE` |

After 2–4 weeks of production data, these tell us whether Approach 3 (browser pool / queue refactor) is actually needed.

### A.5 CLAUDE.md update

Update `apps-microservices/api-detection-langue-fr/CLAUDE.md`:
- Fix stale "Scraping: Playwright (Chromium) via Apify proxy (mandatory)"
- Replace with "Scraping: Camoufox (stealth Firefox, default) via Playwright, with Chromium fallback (`CAMOUFOX_ENABLED=false` or on Camoufox launch failure). Apify proxy mandatory for both."
- Document the new env vars (see Configuration Reference below)
- Reference the caller contract: "Callers MUST use `libs/common-utils/detection_client.py` (Python) or mirror its env vars (other languages)."

## Container Layer (B) — Detailed Design

All changes in `docker-compose.yml` for `api-detection-langue-fr-service`:

### B.1 Resource limits

```yaml
mem_limit: 4500m
cpus: 4
```

- **Memory 4.5GB:** Camoufox is Firefox-class (~300–500MB). Max 10 concurrent = 3–5GB in browsers. Plus Python runtime + `lid.176.bin` (~125MB). Tight enough that runaway memory is caught quickly by OOM (→ container restart with `restart: unless-stopped`); loose enough that normal operation never hits it.
- **CPU 4 cores:** Browser processes are CPU-intensive during JS evaluation. Cap forces the *browser semaphore* to be the bottleneck rather than CPU contention starving other services on the host.

Both numbers are first estimates; the new metrics will inform adjustment within the first 2–4 weeks.

### B.2 Healthcheck

Currently **none** on this service (only implicit TCP liveness). Add:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS http://localhost:8999/api/v1/health || exit 1"]
  interval: 30s
  timeout: 10s
  start_period: 30s
  retries: 3
```

Catches the "Failed to fetch schema" pattern observed in api-gateway logs: if `/health` can't respond in 10s, the event loop is starved → unhealthy after 3 retries (~90s) → Docker restarts the container.

### B.3 Uvicorn hard ceiling

Update the Dockerfile `CMD`:

```
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8999",
     "--proxy-headers", "--timeout-keep-alive", "300",
     "--limit-concurrency", "50"]
```

Above the admission ceiling (12) by a wide margin, but **hard** — Uvicorn itself rejects beyond 50 concurrent connections. Belt-and-braces safety net if admission middleware ever fails open.

### B.4 Unchanged

- `restart: unless-stopped` — restarts on OOM or healthcheck failure
- `init: true` — proper PID1 for signal handling
- Volume mount on app code (dev RW) — flagged in existing CLAUDE.md TODO for prod removal; out of scope

## Caller Layer (C) — Detailed Design

### C.1 The contract — single source of truth via env vars

Gateway is Python, crawler is TypeScript. **Env vars are the source of truth**, Python callers get a helper module, other languages mirror the values.

**Env vars (set in each caller's `.env`):**

```
DETECTION_MAX_CONCURRENCY=5       # max concurrent /detect calls per caller
DETECTION_REQUEST_TIMEOUT_S=180   # HTTP client timeout
DETECTION_MAX_RETRIES=2           # on 503, how many retries
DETECTION_BACKOFF_BASE_S=2        # exponential backoff starting point
```

**Concurrency math:** admission slots on server = 12. Two known callers. Per-caller budget = 5 → worst case 10 concurrent across callers, fits within 12 with headroom.

**New file `libs/common-utils/common_utils/detection_client.py`:**

```
class DetectionClient:
    """HTTP client wrapper enforcing the detection-langue-fr call contract.

    - Per-instance asyncio.Semaphore caps concurrency
    - Honors 503 + Retry-After with bounded exponential retry
    - Used from any Python caller of api-detection-langue-fr
    """
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._sem = asyncio.Semaphore(int(os.getenv("DETECTION_MAX_CONCURRENCY", "5")))
        self._timeout = float(os.getenv("DETECTION_REQUEST_TIMEOUT_S", "180"))
        self._max_retries = int(os.getenv("DETECTION_MAX_RETRIES", "2"))
        self._backoff_base = float(os.getenv("DETECTION_BACKOFF_BASE_S", "2"))

    async def detect(self, url: str, mode: str = "complete", **kwargs) -> dict: ...
    async def detect_batch(self, items: list[dict], **kwargs) -> dict: ...
    async def check_url(self, url: str) -> dict: ...

    # Internal _request_with_retry(method, path, body):
    #  - Acquires self._sem for concurrency cap
    #  - Uses httpx.AsyncClient with self._timeout
    #  - On 503, waits based on precedence: server Retry-After header if present,
    #    else exponential backoff (self._backoff_base * 2**attempt)
    #  - Retries up to self._max_retries; other status codes raise immediately
```

### C.2 Gateway fix (`api-gateway/main.py`) — scoped to detection only

Two changes:

1. **Per-service timeout map** — `timeout=None` becomes the default, detection gets an override. Other services completely unchanged.

   ```
   # settings.py
   DOWNSTREAM_TIMEOUTS_S: dict[str, float] = {
       "api-detection-langue-fr-service": 180.0,
       # Others unset → timeout=None preserved
   }

   # main.py proxy()
   timeout_s = settings.DOWNSTREAM_TIMEOUTS_S.get(target_service_name)
   timeout = httpx.Timeout(timeout_s, connect=10.0) if timeout_s else None
   ```

2. **503 + Retry-After propagation** — relay to upstream caller with original status + `Retry-After` header intact. Log 503s as WARNING (they're a load-shedding signal, not a bug).

**Scope note:** other services still have the infinite-timeout vulnerability. That is a separate conversation and a separate spec; deliberately out of scope here to avoid unknown blast radius.

### C.3 Crawler integration (`crawler-service/.../DetectionLangueClient.ts`)

Three additions to the existing `DetectionLangueClient` class:

```typescript
// Per-caller concurrency cap (check existing deps; use p-limit if not already present)
const detectionLimit = pLimit(
  parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5")
);

// Wrap existing axios calls
async detect(url: string, html: string, mode: string) {
  return detectionLimit(() => this._detectWithRetry(url, html, mode));
}

// Retry on 503 honoring Retry-After; fall back to exponential backoff if header absent
private async _detectWithRetry(...): Promise<DetectionResult> {
  const maxRetries = parseInt(process.env.DETECTION_MAX_RETRIES ?? "2");
  const backoffBase = parseFloat(process.env.DETECTION_BACKOFF_BASE_S ?? "2");
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await this.axios.post('/detect', { url, html_content: html, mode });
    } catch (err) {
      if (err.response?.status === 503 && attempt < maxRetries) {
        // Precedence: Retry-After header (server's guidance) > exponential backoff (client default)
        const retryAfterHeader = err.response.headers['retry-after'];
        const waitS = retryAfterHeader
          ? parseFloat(retryAfterHeader)
          : backoffBase * Math.pow(2, attempt);
        await sleep(waitS * 1000);
        continue;
      }
      throw err;
    }
  }
}
```

**Dependency decision:** prefer `p-limit` (3kb, zero-dep, MIT). **Prerequisite check** during implementation: grep `crawler-service/package.json` for existing concurrency libs (`p-limit`, `p-queue`, `async-sema`, `semaphore-async-await`). Crawlee uses `p-queue` internally, so it is likely already transitively available. If present → use what's there. If not → add `p-limit`.

**Kept unchanged:**
- Existing disk-based domain-level cache (valuable; untouched)
- Axios timeout: bump from 120s to 180s to align with `DETECTION_REQUEST_TIMEOUT_S`

### C.4 Documentation

- Top-level note in `apps-microservices/api-detection-langue-fr/CLAUDE.md`: "Callers MUST use the contract (see `libs/common-utils/detection_client.py` for Python, mirror the env vars for other languages)"
- Matching references in `apps-microservices/api-gateway/CLAUDE.md` and `apps-microservices/crawler-service/CLAUDE.md`

## Request Lifecycle & Failure Modes

### Happy path end-to-end

```
Caller (crawler)
  │ pLimit(5) — caller-side cap
  │ axios 180s timeout
  ↓
Gateway (for indirect callers only)
  │ httpx 180s timeout (scoped, detection only)
  ↓
Detection service
  │ ① Uvicorn --limit-concurrency=50 (hard ceiling)
  │ ② Admission middleware (counter ≥12 → 503 + Retry-After:30)
  │      counter++
  │ ③ Inflight dedup (in-flight same URL → await existing future)
  │ ④ Redis cache lookup (existing)
  │ ⑤ fetch_html → scrape_html
  │      BROWSER_SEMAPHORE(10) acquire
  │      Camoufox launch (45s timeout) | Chromium fallback
  │      navigate, extract
  │      try/finally: unroute_all + close (no leak)
  │ ⑥ DomainFR detection pipeline (untouched)
  │ ⑦ Cache write, dedup future resolve, counter--
  │ Prometheus metrics emitted throughout
```

### Failure-mode matrix

| Failure | First defense | Next defense | Observable signal |
|---|---|---|---|
| Service saturated (≥12 in flight) | Admission middleware → 503+Retry-After | Uvicorn `--limit-concurrency=50` | `detect_admission_rejected_total` increments |
| Service OOM | `mem_limit=4500m` → container kill | `restart: unless-stopped` | Docker restart event; caller retries |
| Event-loop hang | Healthcheck fails 3× | Container restart | Healthcheck logs |
| Browser leak on request exception | `try/finally` in `scrape_html` | `mem_limit` | Memory histogram stable |
| `TargetClosedError` on teardown | `page.unroute_all(behavior='ignoreErrors')` | — | Error count drops to ~0 |
| Camoufox launch timeout | 45s timeout → Chromium fallback (existing) | `scrape_html` returns None or raises | Launch duration histogram tail |
| Duplicate concurrent URL fetches | Inflight dedup future | — | `detect_dedup_hits_total` increments |
| Caller burst beyond per-caller budget | `p-limit(5)` queues client-side | Server admission 503 | Caller-side queue depth |
| Gateway-proxied call hangs | `httpx.Timeout(180, connect=10)` raises | Gateway returns 504 | Gateway timeout logs |
| Caller receives 503 | Parse Retry-After, wait, retry (up to `DETECTION_MAX_RETRIES=2`) | Retries exhausted → propagate | Caller-side retry metric (future) |

### Graceful degradation properties

- **No single failure cascades.** OOM kills one container; auto-restart. Admission saturation returns 503, not hang. Browser leak is bounded by `mem_limit`. Hanging event loop is caught by healthcheck.
- **Dev traffic isolated.** `/detect-debug` has its own admission budget (2 slots). Dev debugging can never starve prod.
- **Fast failure preferred over slow degradation.** 503 + Retry-After is more actionable for callers than a 30s+ queued request, and the service event loop stays responsive to `/health`, `/metrics`, `/openapi.json`.

## Configuration Reference

All tuning knobs exposed as env vars (no redeploy needed):

| Variable | Default | Purpose |
|---|---|---|
| `ADMISSION_ENABLED` | `true` | Kill switch for admission middleware |
| `ADMISSION_MAX_SLOTS` | `12` | Production endpoint slot budget |
| `ADMISSION_DEBUG_SLOTS` | `2` | `/detect-debug` slot budget |
| `ADMISSION_RETRY_AFTER_SECONDS` | `30` | Value of 503 `Retry-After` header |
| `INFLIGHT_DEDUP_ENABLED` | `true` | Kill switch for URL dedup |
| `BROWSER_SEMAPHORE_SIZE` | `10` | Max concurrent Camoufox/Chromium instances |
| `DETECTION_MAX_CONCURRENCY` | `5` | Per-caller cap (contract) |
| `DETECTION_REQUEST_TIMEOUT_S` | `180` | Caller HTTP timeout |
| `DETECTION_MAX_RETRIES` | `2` | Caller retry count on 503 |
| `DETECTION_BACKOFF_BASE_S` | `2` | Caller exponential backoff base |

## Testing Strategy

### Unit tests

| Component | Key assertions |
|---|---|
| `AdmissionController` | Accepts up to max; rejects beyond with 503 + Retry-After; atomic under concurrent asyncio load; debug controller independent from prod controller |
| `InflightDedup` | Two concurrent calls for same URL → one fetch, both get same result; exception propagates to all waiters; `force_refresh=True` bypasses; cleanup removes future on completion |
| `scraper.py` route fix | `unroute_all` called before `context.close()`; `try/finally` guarantees browser close even when `scrape_html` raises; env-configurable semaphore size applied |
| `metrics.py` | Histograms record; counters increment on admission reject / dedup hit / 503 emit; browser launch label correct (camoufox vs chromium) |
| `DetectionClient` (libs) | Semaphore caps concurrency; 503 triggers retry honoring `Retry-After`; max-retries respected; non-503 errors propagate without retry |

### Integration tests (FastAPI TestClient)

- POST `/detect` under saturation → 503 with valid Retry-After header
- After saturation clears, next request succeeds
- `/health` responds < 1s even when all browser slots are busy (proves event loop isn't starved)
- `/detect-debug` has independent slot pool (fill `/detect` budget, verify `/detect-debug` still accepts)

### Load test

Single script: `tests/load_test.py` using `httpx` + `asyncio.gather`. 50 concurrent requests for 60s.

**Assertions:**
- Memory stable (check container stats)
- 503 rate > 0 (proves admission fires)
- p95 latency under target
- No unhandled exceptions in logs
- `TargetClosedError` count = 0

## Rollout — 4 Phases, Independently Reversible

### Phase 1 (day 1–2) — In-service bug fixes *(low risk)*

- `scraper.py`: `unroute_all` + `try/finally` + env-configurable semaphore
- `CLAUDE.md`: fix stale Chromium/Camoufox text, document new env vars

**Gate:** after 48h, `TargetClosedError` log count drops to ~0. If not → investigate before moving on.

### Phase 2 (day 3–4) — Container + observability *(infrastructure)*

- `docker-compose.yml`: `mem_limit`, `cpus`, healthcheck
- Dockerfile: Uvicorn `--limit-concurrency=50`
- `app/core/metrics.py` + `/metrics` endpoint

**Gate:** metrics endpoint populated with real data; healthcheck demonstrably triggers restart under synthetic stress.

### Phase 3 (day 5–6) — Admission control + dedup *(behavioral change)*

- `app/middleware/admission.py`, `app/core/inflight_dedup.py`
- **Ship dark:** deploy with `ADMISSION_ENABLED=false`. Smoke-test. Then flip to `true`.

**Gate:** under real load, 503 rate is non-trivial but not overwhelming (not 100%, not 0 under observed peak). Dedup hit rate > 0 confirms it's doing work.

### Phase 4 (day 7–10) — Caller rollout

- `libs/common-utils/detection_client.py` (new; no consumers yet — zero risk)
- `api-gateway/main.py`: per-service timeout map (detection=180, rest untouched) — deploy first, smaller blast radius
- `crawler-service/DetectionLangueClient.ts`: concurrency cap + 503 retry — deploy after gateway verified

**Gate:** induce a 503 via load test; verify crawler logs show retry after Retry-After delay.

### Rollback strategy

Each phase is a separate PR, merged in order. Rollback = revert the PR or flip the env kill switch (faster).

- **Highest-risk phase:** Phase 4 gateway change. If it breaks, detection via gateway starts timing out, but direct crawler calls still work → partial outage, not total.
- **Lowest-risk phase:** Phase 1 (only removes buggy behavior).

## Follow-Up Considerations

### Approach 3 gate (review 2–4 weeks post-rollout)

After 2–4 weeks of metrics data, reassess whether a larger refactor is needed:

- If `detect_admission_rejected_total` is consistently high at real peak load → capacity exceeded, consider Approach 3 (browser pool + queue)
- If memory sits well below `mem_limit` at peak → browser pool would likely add more throughput per container
- If p95 request duration is dominated by `detect_browser_launch_duration_seconds` → browser pool would be a direct win
- If Camoufox launch times out frequently → investigate pool feasibility, including fingerprinting implications

### Dynamic Retry-After

Once histograms are populated (2–4 weeks), switch `Retry-After` from static `30s` to a dynamic value derived from request-duration p95. Small follow-up PR.

### Grafana dashboard

Build a dashboard on the Prometheus metrics for operational visibility. Panels: request duration, admission rejection rate, dedup hit rate, browser launch duration, inflight gauges, memory usage vs limit.

### Other services using the gateway

The `DOWNSTREAM_TIMEOUTS_S` map introduces a clean pattern. Future work: audit other services called through the gateway, apply per-service timeouts where appropriate. **Not part of this spec.**

## Success Criteria

- `TargetClosedError` log rate drops to near-zero after Phase 1
- Container memory stays below `mem_limit` at observed peak load
- `/health`, `/metrics`, `/openapi.json` respond < 1s under saturation (no event-loop starvation)
- Under induced overload, callers receive 503 + Retry-After (not 120s timeouts)
- Crawler logs show retry-after-wait-and-succeed behavior under induced 503
- New Prometheus metrics populated with data usable for the Approach 3 decision
- CLAUDE.md reflects current browser architecture (Camoufox primary, Chromium fallback)
