# content-extractor-api-service — Hardening + Async + Result Cache (Design)

- **Date:** 2026-06-20
- **Status:** Approved (design); pending implementation plan
- **Service:** `apps-microservices/content-extractor-api-service`
- **Cross-repo touch:** `apps-microservices/api-gateway` (one config line). **No Hellopro BO code change.**
- **Author:** Tech Lead (brainstorm session)

---

## 1. Problem & diagnosis

### 1.1 Observed symptom
Intermittent gateway error on both endpoints:

```
erreur réseau (Hellopro API cURL Error for
https://api.hellopro.eu/extractor-service/extract/header-footer:
Operation timed out after 30001 milliseconds with 0 bytes received)
```

`0 bytes received` after 30 s = the gateway never got a single response byte. This is **queue time, not compute time**.

### 1.2 Root cause (verified against the code)
Both handlers are declared `async def` but run **synchronous, CPU-bound** work **directly inside the coroutine**:

- `app/routers/clean.py:16-26` — `async def clean_html` calls `BoilerpyExtractor.*.get_content()/get_marked_html()` inline.
- `app/routers/extract.py:16-24` — `async def extract_header_footer` constructs `HeaderFooterExtractor(request.main_html)` then calls `extract_with_fallback` / `extract_all_debug` inline.
- `libs/common-utils/src/common_utils/extractor/HeaderFooterExtractor.py` — **706 lines** of pure-synchronous BeautifulSoup work using `html.parser` (the slowest backend), nested `find_all` loops, `difflib.SequenceMatcher` diffing, plus boilerpy3 cleaning, re-parsing `main_html` **and every reference page**.

Because this synchronous CPU work runs on the event loop, **a single in-flight extraction blocks the entire process** — every other request (including `/clean` and even `/health`) queues behind it. The service runs a **single uvicorn worker** (`Dockerfile:28` — `uvicorn main:app ...`, no `--workers`), so there is exactly one event loop. Under any concurrency, requests pile up until the gateway's 30 s ceiling fires with 0 bytes.

### 1.3 "The constraint" stated plainly
The service is **stateless but not concurrent**: single process, event-loop-blocking handlers, no admission control, no caching. It cannot absorb concurrent load and has no backpressure — it degrades into timeouts instead of shedding gracefully.

---

## 2. Goals / non-goals

### Goals
1. Eliminate event-loop blocking → no more `0 bytes / 30 s` timeouts.
2. Add **batched async** endpoints (submit → poll) for **both** `/clean` and `/extract/header-footer`.
3. Add a **Redis-backed result cache** (content-hash → result) and a **Redis job store** for async.
4. Make the service **scale to ~7 crawler-service replicas** via processes × replicas + cache + admission control.

### Non-goals
- Rewriting `HeaderFooterExtractor` or boilerpy3 logic (behaviour preserved exactly).
- Migrating the Hellopro BO call to async (explicitly decided against — see §4).
- `ProcessPoolExecutor` parallelism (GIL discussion in §5.1 — the lever is worker processes × replicas).
- Building the crawler-service integration itself (separate, later effort; this design only makes the server ready for it).

---

## 3. Decisions (locked in brainstorm)

| # | Decision | Choice |
|---|---|---|
| D1 | Request shape for heavy load | **Hybrid**: hardened sync + batched async |
| D2 | Async coverage | **Both** endpoints get an async variant |
| D3 | Redis usage | **Job store + result cache** |
| D4 | Existing BO call handling | **Harden sync + raise gateway timeout** (no BO code change) |

---

## 4. Rationale for D4 (harden sync, not async, for BO)

The BO caller `validate_header_footer_combination()` (`Hellopro/BO/script/rag/alimentation_site_web/script_build_jsonl_header_footer.php:163`) is a **synchronous validation gate** — it decides immediately whether to add a URL to the JSONL dataset. Therefore:

1. The caller must block on the result regardless → async submit→poll adds latency + Redis round-trips for zero benefit.
2. The timeout was **queue time, not compute time** (§1.2). Axis-1 hardening removes the queue at the root; the sync call then returns in its natural few seconds.
3. Jobs are for **long** work (detection went async for 180 s+ batches); header/footer extraction is seconds.
4. The **result cache** makes repeat domains near-instant — async does not add this.
5. **Blast radius**: harden-sync = RAG repo + one gateway line; async migration = Hellopro BO PHP change (separate repo + deploy), poll/stale/404 handling, idempotent `client_job_id`.

The one legitimate argument *for* async — a long sync call holds an HTTP connection + a gateway worker for its full duration, tying up gateway slots under high concurrency — is **real, and is exactly why the crawler ×7 path uses async** in this design. Principled split: **high-volume/batch caller (crawler) → async; low-volume blocking gate (BO builder) → hardened sync.** (Assumes the JSONL builder is low-volume; if it later loops over hundreds–thousands of URLs per run, revisit "harden now, migrate later".)

---

## 5. Architecture — two orthogonal axes

### 5.1 Axis 1 — capacity + responsiveness (mandatory; fixes the timeout at root)

**Stop blocking the loop.** Handlers stay `async def` but the CPU call is offloaded:

```python
result = await asyncio.to_thread(clean_core, html, fmt)
```

The event loop is now free during extraction — `/health` and other requests never queue behind a big page.

**GIL reality (stated honestly).** BeautifulSoup is pure-Python; the GIL means **one process executes one extraction at a time** no matter how many threads. Threads only keep the *loop* responsive (and overlap the small Redis I/O). **True CPU parallelism = processes**:

- `uvicorn --workers N` (configurable via `UVICORN_WORKERS`) → N processes per container.
- `R` replicas behind the existing gateway/load-balancer.
- Concurrent extraction capacity ≈ **N × R**.

`ProcessPoolExecutor` is rejected by default: pickling multi-MB HTML payloads across the process boundary is costly and fragile; workers × replicas achieves the same parallelism with far less complexity.

### 5.2 Axis 2 — request shape (the hybrid)

- **Sync** `/clean`, `/extract/header-footer`: cache-lookup → `to_thread(core)` → optional admission `503` when overloaded. Signatures unchanged.
- **Async** `POST /clean-async`, `POST /extract/header-footer-async`: accept a **batch**, return `job_id`; `GET /jobs/{job_id}` polls. Job record lives in Redis so **any worker or replica can serve the poll**; the worker that accepted the job runs it in-process (asyncio task) and writes status/result to Redis.

---

## 6. Components

| Component | New/Changed | Mirrors (file:line) |
|---|---|---|
| `app/core/extractor_core.py` | **new** — pure functions `clean_core(html, fmt) -> str`, `header_footer_core(main_html, reference_htmls, debug) -> dict` | detection `_run_batch_core` (extract-once, reuse for sync + async) |
| `app/routers/clean.py` | **changed** — cache check → `await asyncio.to_thread(clean_core, ...)` → cache set; admission guard | — |
| `app/routers/extract.py` | **changed** — same pattern around `header_footer_core` | — |
| `app/routers/async_jobs.py` | **new** — `POST /clean-async`, `POST /extract/header-footer-async`, `GET /jobs/{job_id}` | detection `api/routes.py:835-857` (503/Retry-After) |
| `app/core/result_cache.py` | **new** — versioned content-hash cache, `get`/`set`, graceful-degrade | image-comparison `app/core/feature_cache.py:19-103` |
| `app/core/async_jobs.py` | **new** — `JobStore` + `JobManager` + `poll_status` | detection `app/core/async_jobs.py:38-291` (near-copy) |
| `app/core/admission.py` | **new** — in-process inflight guard `try_acquire()`/`release()`; optional global Redis counter | image-comparison `app/core/job_manager.py:20-48` |
| `app/schemas/async_jobs.py` | **new** — submit + status pydantic models | detection `app/models/schemas.py:294-330` |
| `app/core/config.py` | **changed** — Redis/async/cache/admission settings | both |
| `app/core/metrics.py` | **changed** — async + cache metrics | detection `app/core/metrics.py:70-92` |
| `main.py` | **changed** — lifespan: `init_redis_pool`/`close_redis_pool`, `JobManager` start/`shutdown()`, include async router | detection lifespan |
| `Dockerfile` | **changed** — `--workers`, Redis env passthrough | — |
| `requirements.txt` | **changed** — ensure `redis` (via common-utils) available | — |
| `apps-microservices/api-gateway/app/core/settings.py` | **changed** — one entry in `DOWNSTREAM_TIMEOUTS_S` | detection entry at line 81 |

---

## 7. API contracts

### 7.1 Sync (signatures unchanged; behaviour hardened)
`POST /clean` and `POST /extract/header-footer` keep their existing request/response schemas (`app/schemas/clean.py`, `app/schemas/extract.py`). New behaviour:
- Cache hit → returns the cached result immediately (no CPU).
- CPU work offloaded via `asyncio.to_thread` → never blocks the loop.
- When `SYNC_MAX_INFLIGHT > 0` and exceeded → **`503` + `Retry-After`** (caller retries / gateway-LB fails over). Default `0` = guard off (preserve current always-accept behaviour until sized).

### 7.2 Async submit
```
POST /clean-async
{
  "items": [ { "html": "<...>", "format": "TEXT" }, ... ],
  "max_concurrency": 4,          # optional, omitted → DEFAULT_MAX_CONCURRENCY (current default 4)
  "force_refresh": false,        # optional, bypass cache
  "client_job_id": "opt-string"  # optional, idempotency key
}

POST /extract/header-footer-async
{
  "items": [ { "main_html": "<...>", "reference_htmls": ["<...>","<...>"], "debug": false }, ... ],
  "max_concurrency": 4,
  "force_refresh": false,
  "client_job_id": "opt-string"
}
```
Response (`202` new submit, `200` idempotent re-submit when `client_job_id` already known):
```
{ "job_id": "uuid", "status": "pending", "total": N, "poll_after_seconds": 2 }
```

### 7.3 Poll (unified)
```
GET /jobs/{job_id}
→ {
    "job_id": "uuid",
    "job_type": "clean" | "header_footer",
    "status": "pending" | "running" | "completed" | "failed" | "stale",
    "total": N,
    "done": k,
    "results": [ ... ],     # present only when completed (per-item, order-aligned with submit)
    "error": "...",          # present only when failed
    "poll_after_seconds": 2
  }
```
`404` when the job has been evicted (TTL expired). `status` is **computed on read** (`stale` derived from `now - last_activity > STALE_THRESHOLD_S`), never mutated into the stored record (detection `poll_status` pattern). `results` are **order-aligned with the submitted `items`** (see §9 — fixed-size indexed write); `done` counts items in any terminal per-item state (success, per-item failure, or cache-hit); a per-item failure surfaces as an error object in that item's `results` slot rather than failing the whole job.

### 7.4 `503` discriminator (BO/crawler read the header, not the body)
Same convention as detection (`call_api_hellopro` collapses error bodies, so the signal rides a header):
- **Capacity exceeded** (`MAX_ACTIVE_JOBS`) → `503` **with `Retry-After: ASYNC_SUBMIT_RETRY_AFTER_S`** → caller retries.
- **Kill-switch** (`ASYNC_JOBS_ENABLED=false`) or **Redis unavailable** → `503` **without** `Retry-After` → caller does not retry the async path (falls back / fails fast).

---

## 8. Result cache design (mirrors image-comparison `feature_cache.py`)

- **Key:** `extract:{job_type}:{RESULT_CACHE_VERSION}:{sha256(canonical_input)}`
  - `clean`: `sha256(f"{format}\x00{html}".encode())`
  - `header_footer` (**debug=False**): `sha256(("\x00".join([main_html] + sorted(reference_htmls) + ["False"])).encode())` — sorting is safe here because the returned header/footer strings are order-independent (`HeaderFooterExtractor.run_intersection_logic` uses set-membership `all(sig in r_map for r_map in ref_maps)` + a ratio==1 gate across *every* ref, `HeaderFooterExtractor.py:435,467-474`).
  - `header_footer` (**debug=True**): `sha256(("\x00".join([main_html] + reference_htmls + ["True"])).encode())` — **do NOT sort.** The debug response's `intersections_class` / `intersections_structural` carry order-dependent `text_ref1`/`text_ref2` (`HeaderFooterExtractor.py:480-481`, indexed off input order). Sorting would collide two different-order requests onto one entry that should differ. So: sort refs only when `debug=False`; preserve input order when `debug=True`.
- **Value:** JSON of the response body (cleaned content, or header/footer result dict).
- **TTL:** `RESULT_CACHE_TTL_S` (default `86400` / 24 h — HTML drifts; crawler re-crawls). *Note: image-comparison's `FEATURE_CACHE_TTL_S` is 7 d — the 24 h figure is an intentional extractor choice, not an inherited value (HTML changes faster than an image at a stable URL).*
- **Version:** `RESULT_CACHE_VERSION` (default `v1`) — bump whenever boilerpy3 or `HeaderFooterExtractor` logic changes, instantly invalidating stale entries (image-comparison `FEATURE_CACHE_VERSION` precedent).
- **What is actually borrowed from `feature_cache.py`:** only the **version-segment-in-key** invalidation trick and the **graceful-degrade** discipline. The **content-hash key (sha256 of canonical input) is a NEW design** — image-comparison keys on `uuid5(NAMESPACE_URL, url)` (identity, not content) and does **not** content-hash. Do not infer a hashing precedent from the source.
- **Cache-aside, graceful-degrade — IMPLEMENTATION REQUIREMENT (load-bearing):** the bare shared helpers `get_json` / `set_json` / `set_json_nx` **RAISE `ConnectionError` when `cache_service.redis_client is None`** (`cache_service.py:145-146,156-157,168-169`); they only swallow *connection-time* `RedisError` when a client exists. `feature_cache` achieves "never raise" by **reading `cache_service.redis_client` directly and early-returning `{}` / no-op when it is falsy** (`feature_cache.py:65,92`), bypassing the raising helpers. Therefore `result_cache` MUST do the same: **guard on `cache_service.redis_client` truthy before any helper call (or wrap each call in `try/except ConnectionError`)**. Graceful degradation is a property of *this layer*, not of the shared helpers. A unit test must assert no exception escapes when Redis is absent.
- **`force_refresh`:** bypasses the read, still writes the fresh result.
- **Single-flight dedup** (concurrent identical requests collapse to one compute via `set_json_nx` lock): **deferred to phase 2** (YAGNI for first ship; cache + admission already cover the hot path).

Cache uses shared helpers from `libs/common-utils/src/common_utils/redis/cache_service.py`: `get_json`, `set_json` / `set_json_nx` — **always behind the `redis_client`-truthy guard above.**

---

## 9. Async job subsystem (near-copy of detection `app/core/async_jobs.py`)

- **`JobStore`** — Redis CRUD.
  - Record key: `extract:job:{job_id}` (JSON record).
  - Idempotency index: `extract:jobidx:{client_job_id}` → `job_id` (atomic `SET NX`).
  - TTLs: `JOB_TTL_ACTIVE_S` (active, refreshed by heartbeat) / `JOB_RESULT_TTL_S` (terminal).
  - `ping()` for health / availability check (drives the no-`Retry-After` 503).
- **`JobManager`** — submission + in-process worker.
  - `submit(req) -> (job_id, http_status)` — idempotent (claim index `SET NX`; re-read on contention), per-worker capacity reserve (`_inflight >= MAX_ACTIVE_JOBS` → `_JobCapacityExceeded`), increments `_inflight`.
  - `_run_job(...)` — spawned via `asyncio.create_task`; invokes the injected `batch_runner` (the extractor core) and writes the terminal record from its `(results, counts)` return; runs `_heartbeat` alongside; done-callback decrements `_inflight`. **The per-item loop + `asyncio.Semaphore(max_concurrency)` live inside the `batch_runner`/core, not in `_run_job`** (this matches detection: the semaphore is in `_run_batch_core`, `routes.py:386`, not in `JobManager`).
  - **Per-item core loop** — each item = cache-aside + `await asyncio.to_thread(core_fn, ...)`. **Results MUST be written into a fixed-size list indexed by the item's submit position, never appended on completion** — concurrent execution under the semaphore does not preserve submit order otherwise, which would silently break the §7.3 "order-aligned with submit" contract. **Per-item failure is isolated**: a failing item records a per-item error object in its slot and counts toward `done`; it does **not** fail the whole job (the job is `failed` only on a job-level error, e.g. deadline/shutdown). `done` = count of items reaching any terminal per-item state (success **or** per-item-failure **or** cache-hit).
  - `_heartbeat(...)` — every `HEARTBEAT_INTERVAL_S`, refresh `last_activity` + `done` + TTL.
  - `shutdown()` — cancel in-flight tasks within `SHUTDOWN_GRACE_S`, mark still-running jobs `failed=service_shutdown`.
- **`poll_status(record, now, stale_threshold_s)`** — computes `stale` on read.
- **`batch_runner` injection** — `JobManager` receives the per-`job_type` runner that wraps `extractor_core`, exactly as detection injects `_run_batch_core`.

**Multi-worker note:** with `UVICORN_WORKERS > 1`, each process holds its own `JobManager` + `_inflight`, so the global async cap is **soft** = `MAX_ACTIVE_JOBS × workers × replicas`. Because `_inflight` is **per-process** and the gateway/LB may not distribute evenly, **effective capacity before a `503` can be below that soft-cap product** — one worker can saturate (`503`) while another sits idle. The mitigation is a **hard** global cap (optional): a Redis running counter via `cache_service.increment_key` / `safe_decrement_key` (image-comparison `comparator:running_count` precedent) → key `extract:running_count`. Caveat: both helpers return `0` on Redis error (indistinguishable from the floor / first-set, per their docstrings), so the hard counter is **best-effort**. Ship the soft cap first; add the hard cap only if `503`s appear alongside idle workers.

---

## 10. Admission (sync path) — mirrors image-comparison `job_manager.py:20-48`

`app/core/admission.py`: an in-process counter with `try_acquire() -> bool` (atomic check-and-reserve, no `await` between check and increment) and `release()` (idempotent floor-at-0). Sync handlers call `try_acquire`; on `False` return `503 + Retry-After`. Gated by `SYNC_MAX_INFLIGHT` (default `0` = disabled). Keeps overload shedding as `503` instead of degrading into 30 s timeouts.

---

## 11. Configuration (new env vars)

| Var | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379` | job store + result cache. **Absent → async returns 503 (no Retry-After); sync still works cache-less** — *but only because `result_cache` guards on `redis_client` (see §8); the bare helpers raise if called blindly.* |
| `UVICORN_WORKERS` | `2` | worker processes per replica (CPU parallelism lever) |
| `ASYNC_JOBS_ENABLED` | `true` | async kill-switch |
| `MAX_ACTIVE_JOBS` | `8` | per-worker in-flight async jobs (capacity reserve) |
| `SYNC_MAX_INFLIGHT` | `0` | sync admission guard; `>0` → `503` when exceeded (off by default) |
| `RESULT_CACHE_ENABLED` | `true` | cache kill-switch |
| `RESULT_CACHE_TTL_S` | `86400` | cache entry TTL (24 h) |
| `RESULT_CACHE_VERSION` | `v1` | bump on algorithm change to invalidate |
| `JOB_TTL_ACTIVE_S` | `7200` | active job TTL (heartbeat-refreshed) |
| `JOB_RESULT_TTL_S` | `3600` | terminal job TTL (poll window) |
| `STALE_THRESHOLD_S` | `120` | stale detection on poll |
| `HEARTBEAT_INTERVAL_S` | `5` | heartbeat cadence |
| `ASYNC_SUBMIT_RETRY_AFTER_S` | `15` | capacity `Retry-After` value |
| `ASYNC_POLL_HINT_MAX_S` | `30` | upper bound for `poll_after_seconds` hint |
| `SHUTDOWN_GRACE_S` | `5` | graceful-shutdown task-cancel window |
| `DEFAULT_MAX_CONCURRENCY` | `4` | default per-job item concurrency. **NEW extractor var** — detection has no equivalent setting (it hard-codes the default in the schema `Field(default=10)`); 4 is chosen lower because extraction is CPU/GIL-bound, not I/O-bound |

Existing vars unchanged: `APP_NAME`, `APP_VERSION`, `PORT` (8600), `LOG_LEVEL`, `MAX_PAYLOAD_SIZE_MB`.

---

## 12. Capacity model — the "7 crawlers" answer

Sustained throughput:

```
throughput ≈ cores / (p · (1 − h))
  cores = UVICORN_WORKERS × replicas
  p     = avg CPU seconds per extraction
  h     = cache-hit ratio
```

- **Calibrate `p` from real data:** the service already records `http_request_duration_seconds` (`app/core/metrics.py`) and logs `"Cleaned HTML in %.3fs"` / `"Extracted header/footer in %.3fs"`. Read p50/**p95** from the histogram before sizing — and use p95, because `debug=true` and the non-debug fallback chain can invoke `run_intersection_logic` **twice** per request (class + structural, `HeaderFooterExtractor.py:652,656` / `610,619`), roughly doubling worst-case CPU over the `p=1 s` example below.
- **Worked example:** p = 1 s (header/footer), h = 0.5, 4 replicas × 2 workers = 8 cores → ≈ 16 extractions/s sustained; bursts absorbed by the async queue up to `MAX_ACTIVE_JOBS × cores`, overflow shed as `503`.
- **Levers, in priority order:**
  1. **Cache hit-rate** (biggest, free CPU) — crawlers re-crawl and hit near-duplicate pages.
  2. **Replicas / workers** (linear capacity).
  3. **Async queue** (burst absorption).
  4. **Admission `503`** (graceful shed — never a timeout).

**Verdict:** **Yes, it can serve 7 crawler replicas** provided (1) crawler traffic goes through the **async batch** path, (2) cores are sized to the offered concurrency, (3) the result cache is enabled. As-is (single worker, no cache, blocking loop) it **cannot**.

---

## 13. Resilience & error handling

- **Per-job deadline** via `asyncio.wait_for` → terminal `failed` (no hung loops). (Reuse the `PROCESSING_DEADLINE_S`-style guard from image-comparison if a per-job wall-clock is desired; default off for clean, modest for header/footer — size during plan.)
- **Graceful shutdown:** lifespan cancels tasks, marks running jobs `failed=service_shutdown` (detection `shutdown()`).
- **Redis down / absent:** async submit → `503` (no `Retry-After`). Sync → cache-less compute, **but this is guaranteed only because `result_cache` checks `cache_service.redis_client` (or catches `ConnectionError`) before touching the bare helpers** (§8) — the helpers themselves raise `ConnectionError` when there is no client, which would otherwise surface as a 500. `test_result_cache` must assert no exception escapes when Redis is absent.
- **Cache corruption:** deserialize returns `None` → treated as miss.
- **Payload guard** unchanged (`main.py:38-51`, 413 over `MAX_PAYLOAD_SIZE_MB`); applies to async submit too — note batch bodies are larger, so document that the limit is the whole batch (callers chunk accordingly).

---

## 14. Gateway + BO

- **Gateway:** add one entry to `DOWNSTREAM_TIMEOUTS_S` in `apps-microservices/api-gateway/app/core/settings.py:80-82` (the new line goes at `:82`, inside the closing brace):
  ```python
  DOWNSTREAM_TIMEOUTS_S: Dict[str, float] = {
      "api-detection-langue-fr-service": 180.0,
      "extractor-service": 60.0,   # NEW
  }
  ```
  **Route key RESOLVED (proven, not assumed): `"extractor-service"`.** Chain: BO calls `call_api_hellopro('POST','extractor-service','/extract/header-footer',...)` (`script_build_jsonl_header_footer.php:163`) → public path `/extractor-service/...` → gateway proxy `@app.api_route("/{service}/{path:path}")` (`api-gateway/main.py:158-159`) captures `service="extractor-service"` → `service_key = f"{service}-service" if not service.endswith("-service") else service` (`main.py:189`); `"extractor-service"` already ends in `-service`, so it is left unchanged → `DOWNSTREAM_TIMEOUTS_S.get("extractor-service")` (`main.py:190`). Same rule as the existing `"api-detection-langue-fr-service"` entry. Nginx has no `extractor` location (`nginx.conf` only routes `/crawler/`, `/migration/`, `/comparator/`), so the FastAPI-proxy timeout lookup is the one that fires. Unlisted services keep `timeout=None` (zero blast radius); on timeout the gateway returns **504**.
- **BO:** **no code change.** Hardening + cache + the raised gateway timeout resolve the builder timeout. (Existing call site unchanged: `script_build_jsonl_header_footer.php:163`.)

---

## 15. Metrics (mirror detection `metrics.py:70-92`)

New:
- `extract_async_jobs_submitted_total` (Counter)
- `extract_async_jobs_active` (Gauge)
- `extract_async_jobs_terminal_total{status}` (Counter — `completed`|`failed`)
- `extract_async_job_duration_seconds` (Histogram)
- `extract_async_job_capacity_rejected_total` (Counter)
- `extract_cache_hits_total` / `extract_cache_misses_total` (Counter, label `job_type`)
- (optional) `extract_sync_admission_rejected_total` (Counter) when `SYNC_MAX_INFLIGHT` enabled

Existing 3 sync metrics retained: `http_requests_total`, `http_request_duration_seconds`, `extraction_method_used_total`.

---

## 16. Testing strategy

Per-component pytest (test stems must match production file names for the `tdd-gate` hook):
- `tests/test_extractor_core.py` — output parity: `clean_core` / `header_footer_core` produce byte-identical results to the current inline handler logic (golden fixtures from existing `tests/test_clean.py`, `tests/test_extract.py`).
- `tests/test_result_cache.py` — key determinism, version isolation, roundtrip, graceful-degrade on Redis error, `force_refresh` bypass (adapt image-comparison `test_feature_cache.py`).
- `tests/test_async_jobs.py` — submit idempotency (`client_job_id` → 200 re-submit), poll lifecycle pending→running→completed, `stale` computation, capacity `503` + `Retry-After`, kill-switch `503` without header, Redis-down `503` without header, `shutdown()` marks running jobs failed.
- `tests/test_clean.py` / `tests/test_extract.py` — extend: cache hit returns cached, loop-non-block (handler returns while a slow extraction runs — assert via `to_thread`), admission `503` when `SYNC_MAX_INFLIGHT` exceeded.
- Gateway: a unit assertion that `DOWNSTREAM_TIMEOUTS_S` contains the extractor key.

Constraint: run **targeted** test files (pre-existing broken suites elsewhere; pin `pydantic-core==2.46.4` if env drift reappears).

---

## 17. Rollout (phased, flag-gated)

1. **Phase 1a — pure timeout fix, NO Redis dependency.** Ship the `extractor_core` extraction + `await asyncio.to_thread` offload + `UVICORN_WORKERS=2`. This alone removes the reported `0 bytes / 30 s` symptom and keeps Redis off the critical path. Verify: `/health` responsive while a slow extraction runs; concurrent requests no longer queue.
2. **Phase 1b — result cache (adds Redis, graceful-degrade).** Ship `result_cache` with the `redis_client` guard. Verify: `extract_cache_hits_total` climbing; **Redis-down smoke test** confirms requests still succeed cache-less (no 500). Still `ASYNC_JOBS_ENABLED=false` — zero risk to BO throughout 1a/1b.
3. **Phase 2 — enable async.** `ASYNC_JOBS_ENABLED=true`; smoke a 1-item job through the gateway; confirm `extract_async_jobs_*` metrics and poll lifecycle.
4. **Phase 3 — scale + gateway timeout.** Raise replicas/workers to the measured load; add the gateway `DOWNSTREAM_TIMEOUTS_S` entry (key proven: `"extractor-service"`, §14). Crawler-service integrates against the async endpoints in a separate effort.

---

## 18. Open risks / action items

1. ~~**Gateway route key** — confirm `"extractor-service"` vs `"extractor"`.~~ **RESOLVED** → `"extractor-service"`, proven via `api-gateway/main.py:189` (§14). No longer an open item.
2. **GIL ceiling** — `max_concurrency` within one worker gives limited CPU speedup; processes are the real lever. Documented so operators size replicas, not `max_concurrency`.
3. **Local env drift** — `pydantic-core` may need re-pinning to `2.46.4` for subagent pytest (primer note).
4. **Batch payload size** — async submit bodies are larger than single sync calls; the 413 guard applies to the whole batch. Callers must chunk; document in CLAUDE.md.
5. **Per-job deadline tuning** — header/footer can legitimately take seconds on huge pages; size `wait_for` so we don't fail valid slow jobs.

---

## Appendix A — Reuse map (verified file:line)

| Need | Source to copy/adapt |
|---|---|
| Async `JobStore` + `JobManager` + `poll_status` | `apps-microservices/api-detection-langue-fr/app/core/async_jobs.py:38-291` |
| Async submit/status schemas | `apps-microservices/api-detection-langue-fr/app/models/schemas.py:294-330` |
| 503 / kill-switch / Retry-After discriminator | `apps-microservices/api-detection-langue-fr/app/api/routes.py:835-857` |
| Async config vars + defaults | `apps-microservices/api-detection-langue-fr/app/core/config.py:63-72` |
| Async metrics | `apps-microservices/api-detection-langue-fr/app/core/metrics.py:70-92` |
| Shared extract core pattern (`_run_batch_core`) | `apps-microservices/api-detection-langue-fr/app/api/routes.py` (`_run_batch_core`) |
| Result cache — **version-segment + graceful-degrade pattern ONLY** (content-hash key is new; source keys on `uuid5(URL)`, does not content-hash) | `apps-microservices/image-comparison-service/app/core/feature_cache.py:19-103` |
| Sync admission slot model | `apps-microservices/image-comparison-service/app/core/job_manager.py:20-48` |
| Admission/cache config defaults | `apps-microservices/image-comparison-service/app/core/config.py:7-48` |
| Redis helpers (init/close/get_json/set_json/set_json_nx/safe_decrement_key) | `libs/common-utils/src/common_utils/redis/cache_service.py:77-305` |
| Prometheus WSGI mount | `libs/common-utils/src/common_utils/metrics/prometheus.py:31` |
| Gateway downstream timeout map (new entry at `:82`; key `"extractor-service"`) | `apps-microservices/api-gateway/app/core/settings.py:80-82` + lookup `api-gateway/main.py:189-190` |

## Appendix B — Files touched (summary)

**RAG-HP-PUB (`features/poc`):**
- `apps-microservices/content-extractor-api-service/` — `main.py`, `app/core/{config,metrics}.py`, `app/routers/{clean,extract}.py`, **new** `app/core/{extractor_core,result_cache,async_jobs,admission}.py`, `app/routers/async_jobs.py`, `app/schemas/async_jobs.py`, `Dockerfile`, `requirements.txt`, `tests/*`, `CLAUDE.md`.
- `apps-microservices/api-gateway/app/core/settings.py` — one `DOWNSTREAM_TIMEOUTS_S` entry.

**Hellopro:** none.
