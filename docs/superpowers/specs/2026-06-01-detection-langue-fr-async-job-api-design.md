# Design — Async Job API for `api-detection-langue-fr`

- **Date:** 2026-06-01
- **Status:** Approved (design); hardened via adversarial spec-review (35 findings applied); pending implementation plan
- **Repos touched:** `RAG-HP-PUB` (service), `Hellopro` (BO consumers)
- **Branch:** `features/poc` (RAG-HP-PUB), `main` (Hellopro — per prior session convention for BO)
- **Predecessors:** `2026-05-17-detection-langue-fr-crawler-admission-carveout-design.md`, `2026-05-17-bo-admission-rejected-retry-design.md` (this spec is the deferred "async endpoint" follow-up from both)

---

## 1. Context & Problem

`api-detection-langue-fr` detects whether a website is in French. It exposes synchronous endpoints (`POST /api/v1/detect`, `POST /api/v1/detect-batch`). BO calls `/detect-batch` from `detectBatchUrls()` with `CURLOPT_TIMEOUT = 180` (constant `DETECTION_REQUEST_TIMEOUT_S = 180`), matching the api-gateway 180s ceiling.

**Symptom:** for large batches a single synchronous call exceeds 180s — Camoufox cold-starts, fetch retries, and admission contention compound — and BO observes `Operation timed out after 180001 milliseconds with 0 bytes received`. Shrinking the chunk (already 10 → 5 in a prior spec) reduces but does not eliminate it: a single 5-URL chunk hitting multiple cold browser launches still blows the budget.

**Root cause:** per-URL detection latency is unbounded-ish (browser + network), but the synchronous HTTP contract imposes a hard 180s wall. The two are mismatched for batch work.

**Fix:** decouple BO from the 180s wall via an async job contract — submit returns immediately with a `job_id`; BO polls with tiny short-lived requests; results are fetched when ready. No single request approaches 180s.

### Service-side facts (verified against code)
- Single replica (no `deploy.replicas`), behind api-gateway at `https://api.hellopro.eu/detection_site_fr-service`.
- FastAPI + Uvicorn (`--timeout-keep-alive 300 --limit-concurrency 50`), fully request/response. **No lifespan/startup hook today** (middleware + `_prod_admission` are built at module scope in `main.py`).
- **Redis present** (`REDIS_URL`, `redis[hiredis]>=5.0.0`) — used today only by `DomainCache` (cache, optional, graceful-degradation; lazy connect — see §4.3 caveat).
- Concurrency primitives (in-memory): `AdmissionController` (**default `ADMISSION_MAX_SLOTS=12` in code; pinned `8` in docker-compose**), `InflightDedup`, browser semaphore (**default `BROWSER_SEMAPHORE_SIZE=10` in code; pinned `6` in docker-compose**). `AdmissionController.acquire()` is **non-blocking**: returns `False` on saturation → the item becomes `method='admission_rejected'` (it does NOT queue/park).
- Per-item timeout inside the batch core: `asyncio.wait_for(_process_item_core(item), timeout=300)` (routes.py); alternative-URL fetches up to 120s each; Pass-2 retry uses a 2s inter-item gap.
- **No job queue, no worker, no broker, no persistence beyond the Redis cache.** `requirements.txt` has no celery/rq/arq/pika.

### Consumer-side facts (verified, BO)
- Shared HTTP wrapper `call_api_hellopro($method, $service, $endpoint, $payload=[], $isDownload=false, $timeout=300, array &$responseHeaders=[], ?int $connectTimeout=null)` → `https://api.hellopro.eu/{service}{endpoint}` (base URL hardcoded in `BO/fonctions/fonctions_hellopro.php`). 2xx → decoded JSON; non-2xx → `['success'=>false,'message'=>...,'http_code'=>...]`.
- `detectBatchUrls()` in `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php`: POST `/api/v1/detect-batch`, 180s timeout, 2 retries, handles 503 + `Retry-After` (RFC 7231) and transient codes `[0,408,429,502,504]`, throws `DetectionApiException` / `DetectionApiBackpressureException`. Has `_log_detect_batch_duration()` observability helper.
- 7 consumers total. **Hot path (in scope):**
  - `BO/script/chatgpt/variante_categorie/script_identifier_site_fr_v2.php` — per-upload (HTTP-triggered, `set_time_limit(0)`, can be thousands of URLs), chunk 5, `foreach($tab_siteweb as $payload_siteweb)` (value-only, **no index today**), per-result upsert to `domaine_francais` keyed on `$res_check['url']`, enqueues `domaine_fr_retry`. Returns `nb_total/nb_succes/nb_retry`, reported in an operator email.
  - `BO/script/chatgpt/variante_categorie/script_retry_identifier_site_fr.php` — **cron daily**, `RETRY_LIMIT_PER_RUN=200`, `RETRY_BATCH_SIZE=5`, `RETRY_SLEEP_MS=500`, `foreach($batches as $batch_idx => $batch)` (**index exists**), builds `$results_by_url` (key `trim(trim($r['url']),'/')`) + `$results_by_domain` fallback because *"l'API peut renvoyer une URL différente après redirection"*, reads/updates `domaine_fr_retry`, writes `domaine_francais`. `$nb_admission_rejected` is used but **never initialized** (relies on PHP null→0).
- Helper locations: `enfiler_url_retry_fr()`, `upsert_domaine_francais()`, `recupere_domaine()` live in `fonctions_scrapping.php`. **`marquer_succes_retry()` / `marquer_echec_retry()` are script-local** to `script_retry_identifier_site_fr.php` (NOT in the shared file).
- DB sinks: `domaine_francais` (`est_valide_df` = `1` FR / `0` non-FR / `2` error), `domaine_fr_retry` (`statut_dfr_retry` = `0` pending / `1` success / `2` abandoned; `nb_tentatives_dfr_retry`; `RETRY_MAX_TENTATIVES=3`).

---

## 2. Goals / Non-Goals

### Goals
1. BO never hits the 180s timeout for detection batch work in the hot path.
2. Additive on the service: **sync `/detect-batch` stays behavior-identical** for internal `get_domaine_rub_bo()`, crawler-service, and the 3 low-volume scripts.
3. Restart-safe contract: a service redeploy/OOM never silently loses URLs — they flow back through the existing `domaine_fr_retry` infra.
4. No new infrastructure or heavy dependency (no broker, no worker container).
5. Async contract (`POST` submit / `GET` poll) identical to what a future dedicated-worker backend would expose → backend swap later requires **zero BO changes**.
6. **Async load must not starve the realtime crawler-service / sync callers** (see §4.11 — dedicated admission sub-pool).

### Non-Goals
- Migrating the other 5 consumers. Deferred.
- Durable job resume after restart (explicitly rejected — Decision Q3).
- Horizontal scaling / dedicated worker process (Approach B, deferred).
- Job cancellation (`DELETE`) — deferred, not needed by hot path.
- **Changing how a completed non-ok verdict is recorded.** A submitted URL that is *present in results* with a real non-ok method (`fetch_failed`/`http_error`/`soft_404`/`challenge_page`/`error`) continues to be upserted as `est_valide_df=0`, exactly as today. This is intentional and unchanged. Only `admission_rejected` (already handled) and URLs **entirely absent** from results are treated as "not yet checked" (§5.1).

---

## 3. Decisions (from brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| Scope | Which consumers migrate | **Hot path only**: `script_identifier_site_fr_v2.php` + `script_retry_identifier_site_fr.php`. Sync endpoint untouched. |
| Job model | Submission granularity | **Batched async jobs** (~100 URLs/job, bounded concurrent, poll-to-completion per job). |
| Restart | In-flight job on restart | **Fail-fast + BO re-enqueue.** Status+heartbeat in Redis, no resume. Stale/failed → BO pushes absent URLs to `domaine_fr_retry`. |
| Backend | How work executes | **Approach A** — in-process asyncio worker + Redis job store. |
| Admission | Blast-radius isolation | **Dedicated async admission sub-pool** (see §4.11). *This supersedes the Section-2 "shared pool, sub-pool deferred YAGNI" decision — flagged for the review gate; rationale: async sustained pressure on the shared 8-slot pool would fast-fail crawler-service into 503s.* |

### Rejected alternatives
- **Approach B (dedicated worker + broker, arq/Celery):** true isolation + scale, but a new container, a broker, and shipping Camoufox+Chromium+fastText into the worker image (doubles the ~200MB+ footprint + memory), plus ops burden. Overkill at current volume + single-replica reality. **A→B is a drop-in backend swap later (same HTTP contract), so no BO rework is lost by choosing A now.**
- **In-memory job store (no Redis for jobs):** contradicts durable-status/heartbeat (Q3). Rejected.
- **Keep sync, shrink chunks further:** does not remove the 180s wall on a single cold-browser-heavy chunk. Rejected.

---

## 4. Service-Side Design (`api-detection-langue-fr`)

### 4.1 Endpoints (additive, under `/api/v1`, gateway auto-routes)

#### `POST /api/v1/detect-batch-async` — submit
Request `AsyncBatchSubmitRequest` (extends the existing batch fields; `mode` default uses the enum member `DetectionMode.COMPLETE` per existing convention):
```python
class AsyncBatchSubmitRequest(BaseModel):
    items: list[BatchItem]                      # max BATCH_MAX_URLS (100)
    mode: DetectionMode = DetectionMode.COMPLETE
    proxy_url: Optional[str] = None
    use_nlp_detection: bool = True
    force_refresh: bool = False
    max_concurrency: int = 10                   # 1..50
    homepage_fallback: bool = True
    client_job_id: Optional[str] = None         # BO idempotency key
```
**Precondition:** `items` must contain **no duplicate URLs** (correlation in §5.1 is per distinct submitted URL). BO callers already dedupe per upload; the helper additionally de-dupes defensively before submit.

Responses:
- `202 AsyncBatchSubmitResponse { job_id, status:"pending", total, poll_after_seconds }`.
- `200` — **same shape**, when `client_job_id` resolves to an existing job record (see §4.6 — *exists*, any status). BO then polls to fetch results (no re-run).
- `503` — three causes, **differentiated** (see §4.4 / §5.1):
  - capacity (`MAX_ACTIVE_JOBS` reached): `Retry-After` header set, body `{detail, retry_after_seconds, retryable:true}` → BO retries.
  - kill-switch (`ASYNC_JOBS_ENABLED=false`) or Redis-unavailable: **no `Retry-After`**, body `{detail, retryable:false}` → BO short-circuits to its `catch` (degraded-but-safe), does NOT burn its retry budget.

#### `GET /api/v1/detect-batch-async/{job_id}` — poll
```python
class AsyncBatchStatusResponse(BaseModel):
    job_id: str
    status: str                                 # pending|running|completed|failed|stale
    total: int
    done: int
    success_count: int
    failed_count: int
    error_count: int
    results: Optional[list[DetectionResponse]] = None   # populated when terminal
    processing_time_ms: Optional[float] = None
    error: Optional[str] = None
    poll_after_seconds: int                     # server cadence hint (see §4.9)
```
- `200` for any known job. `404` for unknown/expired `job_id` (BO treats as `stale`).
- `results` = full per-URL `DetectionResponse` list when `status=completed`. On `failed`/`stale` returns whatever items completed (may be empty); BO computes the remainder (§5.1).

`DELETE /{job_id}` — **deferred** (not built).

### 4.2 Status lifecycle
```
pending ──▶ running ──▶ completed              (all items done)
                  └────▶ failed                (job-level fatal OR graceful-shutdown interrupt)
pending/running ─ ─ ─ ▶ stale                  (computed on read — §4.7)
```
Terminal-from-BO = `{completed, failed, stale}`. Terminal-bad = `{failed, stale}` → BO re-enqueues the batch's absent URLs. `stale` is **computed at read time** by the poll handler (a dead worker can't write).

### 4.3 `JobStore` (Redis)
New module `app/core/async_jobs.py`.

- Record key: `detect:job:<job_id>` → JSON:
  ```json
  {
    "job_id":"...", "client_job_id":"...|null",
    "status":"pending|running|completed|failed",
    "total":0, "done":0,
    "success_count":0, "failed_count":0, "error_count":0,
    "results":[ /* DetectionResponse dicts; only on terminal write */ ],
    "error":"...|null",
    "created_at":0.0, "started_at":0.0|null, "finished_at":0.0|null,
    "last_activity":0.0
  }
  ```
  Timestamps are epoch seconds (`time.time()`).
- **Input URL list is NOT persisted** (no resume → smaller blob; BO owns the list).
- Idempotency index: `detect:jobidx:<client_job_id>` → `job_id`.
- **TTL policy (load-bearing — see invariant §5.2):**
  - `pending`/`running` record: `JOB_TTL_ACTIVE_S` (default 7200s = 2h), **refreshed on every heartbeat write** so a long-running job never expires mid-run.
  - Idempotency index: created with TTL `JOB_TTL_ACTIVE_S`; on terminal write, **re-set to `JOB_RESULT_TTL_S`** so the index and the record expire together (no dangling pointer).
  - Terminal record: re-`setex` with `JOB_RESULT_TTL_S` (default 3600s = 1h). Redis auto-evicts afterward — **no cleanup job.**
- **Writer ownership:** `submit` writes the initial `pending` record; the worker coroutine is the sole updater **while running**; the poll handler is read-only; **`shutdown()` becomes the sole updater only after it has confirmed task cancellation** (§4.4). A record already in a terminal state is **never** overwritten.
- **Redis-availability caveat (do NOT copy `DomainCache`'s swallow pattern for the submit path):** `aioredis.from_url()` connects lazily and the `DomainCache` try/except only catches URL-parse errors — connection failures surface later inside `get/set` and are swallowed. The submit path therefore **must actively probe** (`await client.ping()` with a short timeout) and **must check** the first record write (treat any exception as `_JobsUnavailable` → 503 non-retryable). The submit's first write is never fire-and-forget.

### 4.4 `JobManager` (asyncio worker)

**`submit(spec) -> (job_id, http_status)` — ordered to be race-free:**
1. If `not ASYNC_JOBS_ENABLED` → raise `_JobsDisabled` (503, `retryable:false`).
2. `await store.ping()`; failure → raise `_JobsUnavailable` (503, `retryable:false`).
3. **Idempotency claim FIRST, atomic:** if `client_job_id`, `claimed = await redis.set(idx_key, new_job_id, nx=True, ex=JOB_TTL_ACTIVE_S)`. If not `claimed`: `existing = await redis.get(idx_key)`; if `existing` → return `(existing, 200)` **without spawning a task** (regardless of that job's status). (Rare lost-key fallthrough: re-attempt one NX; if still unclaimable and no existing, proceed with a fresh id.)
4. **Capacity reserve — synchronous, no `await` between the check and the increment:**
   `if self._inflight >= MAX_ACTIVE_JOBS: (release idx claim) raise _JobCapacityExceeded` (503 capacity, `Retry-After`). Else `self._inflight += 1` in the same tick. `self._inflight` is a plain int reserved here and decremented exactly once in the task done-callback (or on the abort path below).
5. **Checked initial write:** `await store.write_pending(job_id, spec, client_job_id)`. On exception → `self._inflight -= 1`, release idx claim, raise `_JobsUnavailable` (503).
6. **Spawn + track, synchronously (no `await` between create and add):**
   `task = asyncio.create_task(self._run_job(job_id, spec)); self._active.add(task); task.add_done_callback(self._on_done)` where `_on_done` does `self._active.discard(task); self._inflight -= 1`.
7. Return `(job_id, 202)`.

> The cap check + reserve (step 4) is a single no-`await` critical section, so `_inflight` can never exceed `MAX_ACTIVE_JOBS`. The idempotency claim (step 3) is atomic via `SET NX`, so concurrent identical submits cannot both spawn.

**`_run_job(job_id, spec)`:**
```
try:
    write status=running, started_at=now, last_activity=now        # initial heartbeat
    progress = _Progress()                                          # in-memory counters only
    hb = asyncio.create_task(_heartbeat(job_id, progress))          # see below
    try:
        results, counts = await _run_batch_core(items, mode, opts, progress_cb=progress.update)
    finally:
        hb.cancel(); await asyncio.gather(hb, return_exceptions=True)
    # terminal counts are AUTHORITATIVE from the core return, not from the throttled snapshot
    write status=completed, results, counts, finished_at=now; setex(JOB_RESULT_TTL_S); reset idx TTL
except asyncio.CancelledError:
    raise                                                           # shutdown owns the record write
except Exception as e:
    write status=failed, error=str(e), finished_at=now; setex(JOB_RESULT_TTL_S); reset idx TTL
```
- **`_heartbeat`** is a wall-clock ticker: every `HEARTBEAT_INTERVAL_S` it snapshots `progress` (done + counts) to the record and refreshes `last_activity=now` + the active TTL — **independent of per-item completion**, so `last_activity` advances even while a single slow item (up to the 300s per-item timeout) is in flight. This is what makes the §4.7 stale check correct.
- **`progress_cb`** only mutates in-memory counters (cheap, no Redis per item). The heartbeat ticker is the only intermediate Redis writer; the terminal write supersedes it with authoritative counts from `_run_batch_core`. Per-item detection errors are captured *inside* results (method/`error`) and do NOT fail the job; only an unexpected job-level exception does.

**`shutdown()` (from lifespan) — single-writer protocol:**
1. `for t in self._active: t.cancel()`.
2. `await asyncio.wait(self._active, timeout=GRACE)` (bounded grace).
3. For each job whose record is still `pending`/`running` (read-modify-guarded — never overwrite a terminal state), write `status=failed, error="service_shutdown"` (a cheap `setex`).
4. Any job not marked within `GRACE` (rare) **falls back to the §4.7 stale path** — BO still recovers, just on the stale timeout rather than the next poll. `GRACE` is sized for the failed-write loop (a few Redis `setex`), with cancellation of long browser work allowed to lag.

Routes reach the manager via `request.app.state.job_manager` (set in lifespan §4.8).

### 4.5 DRY refactor — `_run_batch_core` (its OWN commit, before async wiring)
Extract the current batch handler body into a reusable function. The handler `detect_french_batch` spans **routes.py ~358–640**; the per-item machinery to extract is the shared `semaphore`/`processed_count`/`count_lock` locals (~388–398), the `_process_item_core` closure (~400–444), the `process_single` closure (~446–460), the `first_match` grouped block (~465–563), and the `complete`/`simple` 2-pass block (~569–640). These are nested closures capturing `request`, `semaphore`, `processed_count`, `count_lock`, `total_items`, `start_time`, so the extraction reconstructs those locals inside the core from its params:
```python
@dataclass
class BatchCounts:           # NEW type — does not exist today
    success_count: int; failed_count: int; error_count: int

async def _run_batch_core(
    items: list[BatchItem], mode: DetectionMode, opts: BatchOpts,
    progress_cb: Optional[Callable[[int, int, int, int], None]] = None,
) -> tuple[list[DetectionResponse], BatchCounts]:
    ...
```
- `processing_time_ms` and the `BatchDetectionResponse` wrapping **remain in the thin `/detect-batch` route wrapper** (the route re-derives `processing_time_ms` and builds the response from `(results, counts)`).
- Sync `/detect-batch` calls it with `progress_cb=None` → **behavior identical to today** (guarded by a characterization test, §7).
- **Commit-separation enforcement:** the `progress_cb` parameter **and** its guarded in-loop accumulation (a no-op when `progress_cb is None`) land in the **refactor commit**, so the async-wiring commit only *passes* a callback and never edits `_run_batch_core`'s body. This is the mechanism that keeps the refactor reviewable in isolation.

### 4.6 `client_job_id` dedup predicate (one definition, used verbatim in §4.1/§4.4)
> **Return `200` (existing job) iff the idempotency index resolves AND the referenced record exists — regardless of its status (`pending`/`running`/`completed`/`failed`). Otherwise create a fresh job.**

- The claim is atomic (`SET NX`, §4.4 step 3); the **existence guard is REQUIRED and tested**: an index that resolves to an already-evicted record (possible only if TTLs ever diverge) yields a fresh job. With §4.3's aligned index/record TTLs this divergence cannot occur, but the guard remains mandatory as defense-in-depth.
- A re-submit onto a *terminal* job returns 200; BO then polls and reads the cached results (no re-run). See §5.4 for the operator-re-trigger window.

### 4.7 Stale detection (poll handler, read-only)
```python
if record.status in ("pending", "running") and (now - max(record.created_at, record.last_activity)) > STALE_THRESHOLD_S:
    return status as "stale"     # never mutates the record
```
Computed for **both** `pending` and `running` (a process killed between the pending-write and `create_task`, or a dead worker, is recovered within `STALE_THRESHOLD_S` instead of waiting out `JOB_TTL_ACTIVE_S`). With the wall-clock heartbeat ticker (§4.4) refreshing `last_activity` every `HEARTBEAT_INTERVAL_S=5s`, `STALE_THRESHOLD_S=120s` is safely larger than any healthy gap — the 300s per-item timeout no longer causes a false stale, because the ticker fires regardless of item progress.

### 4.8 Lifespan (new)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.job_manager = JobManager(redis_url=settings.REDIS_URL, settings=settings)
    yield
    await app.state.job_manager.shutdown()
app = FastAPI(..., lifespan=lifespan)
```
Existing module-scope middleware/`_prod_admission` setup in `main.py` is left as-is (no behavior change); only the `JobManager` moves into lifespan. Nothing to resume on startup.

### 4.9 Metrics (extend `app/core/metrics.py`)
- `ASYNC_JOBS_SUBMITTED = Counter("detect_async_jobs_submitted_total")`
- `ASYNC_JOBS_ACTIVE = Gauge("detect_async_jobs_active")` — set to `self._inflight`.
- `ASYNC_JOBS_TERMINAL = Counter("detect_async_jobs_terminal_total", labelnames=("status",))` — completed|failed.
- `ASYNC_JOB_DURATION = Histogram("detect_async_job_duration_seconds", buckets=(1,5,15,30,60,120,300,600,1800))`.
- `ASYNC_JOB_CAPACITY_REJECTED = Counter("detect_async_job_capacity_rejected_total")`.
- `ASYNC_ADMISSION_REJECTED = Counter("detect_async_admission_rejected_total")` — per-item rejections from the async sub-pool (kept distinct from the existing prod `ADMISSION_REJECTED` so crawler/sync pressure stays legible).
- Names checked against existing metrics — no collision.

**`poll_after_seconds` server contract:** the server returns a small fixed hint, `poll_after_seconds = max(HEARTBEAT_INTERVAL_S, 5)` on both submit and poll, bounded above by `ASYNC_POLL_HINT_MAX_S = 30`. BO clamps its sleep to `min(max(poll_after_seconds, POLL_MIN), remaining_budget)` (§5.1) so a large hint can never overshoot the BO wall-clock budget.

### 4.10 Config (`app/core/config.py` + env / docker-compose)
```python
ASYNC_JOBS_ENABLED: bool = True
MAX_ACTIVE_JOBS: int = 8
ASYNC_ADMISSION_MAX_SLOTS: int = 4         # dedicated sub-pool — see §4.11
JOB_TTL_ACTIVE_S: int = 7200
JOB_RESULT_TTL_S: int = 3600
STALE_THRESHOLD_S: int = 120
HEARTBEAT_INTERVAL_S: int = 5
ASYNC_SUBMIT_RETRY_AFTER_S: int = 15
ASYNC_POLL_HINT_MAX_S: int = 30
```
All overridable via env (Pydantic `BaseSettings`). docker-compose may pin `MAX_ACTIVE_JOBS` / `ASYNC_ADMISSION_MAX_SLOTS` per resource budget.

### 4.11 Admission isolation & tradeoffs (flagged)
1. **Dedicated async admission sub-pool (design change vs approved Section 2).** The async worker's per-item fetches acquire from a **separate** `AdmissionController(ASYNC_ADMISSION_MAX_SLOTS, default 4)`, **not** the prod `AdmissionController` (8 in compose). Why: the prod pool is non-blocking and fast-fails on saturation, turning items into `admission_rejected`. crawler-service (an active production pipeline) calls single `/detect`, whose fetch acquires a prod slot → a sustained async run filling the shared 8 would fast-fail crawler into 503s. A dedicated sub-pool caps async's claim and **guarantees crawler/sync keep their 8 slots**. Both pools still serialize on the single browser semaphore (6 in compose) — the real memory/OOM bound — so total concurrent browsers is unchanged; async simply queues fairly behind the semaphore instead of stealing prod admission slots. Async items that miss the sub-pool become `admission_rejected` and ride the existing Pass-2 retry (within the async run). `_fetch_with_admission` gains a `controller` argument (prod vs async); the sync path passes the prod controller unchanged.
   - **Worst-case bound:** `MAX_ACTIVE_JOBS(8) × max_concurrency(10) = 80` coroutines may be past their per-job semaphore, but only `ASYNC_ADMISSION_MAX_SLOTS(4)` proceed to fetch concurrently; the rest are `admission_rejected`→retry. Memory ≈ a few MB of parked coroutines.
2. **Redis becomes required for async** (cache stays optional). `REDIS_URL` unset / unreachable → submit returns 503 (`retryable:false`); **sync endpoints unaffected** (no full-service crash). `ASYNC_JOBS_ENABLED=false` is the explicit kill-switch.
3. **Work runs in the API process** — same as today's sync detection; `MAX_ACTIVE_JOBS` + the sub-pool bound the footprint.

---

## 5. Consumer-Side Design (BO)

### 5.1 New helper `detectBatchUrlsAsync()`
Location: beside `detectBatchUrls()` in `fonctions_scrapping.php`.
```php
function detectBatchUrlsAsync(
    array $items, int $maxConcurrency = 10, string $mode = 'complete',
    bool $force_redetect = false, ?string $client_job_id = null
): ?array
```
**Return contract:**
```php
[
  'results'         => [ /* every PROCESSED item, same DetectionResponse shape as sync */ ],
  'incomplete_urls' => [ /* submitted URLs ENTIRELY ABSENT from results; [] on full success */ ],
  'job_id'          => '...',
  'final_status'    => 'completed' | 'stale' | 'failed' | 'timeout',
]
```

**Correlation contract (the helper computes `incomplete_urls` itself — callers do NOT build indexes):**
- The server may return a result whose `url` differs from the submitted URL (FR found via an **alternative/redirect** link — `DetectionResponse.url` is then the *alternative* URL; homepage-fallback keeps the submitted url but validates `analyzed_url`). A naive "submitted minus results-by-url" diff therefore wrongly flags a successfully-detected FR site as incomplete and re-enqueues it forever.
- So the helper builds the **same dual index the cron retry script already uses**: `$results_by_url` (key = `trim(trim($r['url']),'/')`) **and** `$results_by_domain` (key = base domain via `recupere_domaine()`), then:
  > `incomplete_urls` = each **distinct submitted URL** that matches **neither** `$results_by_url` **nor** `$results_by_domain`.
- **"Present in results at all ⇒ NOT incomplete"**, regardless of ok/non-ok. A completed non-ok (e.g. `fetch_failed`) is consumed by the caller's normal loop (→ `est_valide_df=0`, unchanged §2) and is **not** re-enqueued.
- `incomplete_urls` contains submitted URL strings **VERBATIM** (the exact `items[].url` sent, no helper-side normalization), so callers can map them back with their own keys.
- **Duplicate/same-domain handling:** the helper de-dupes submitted URLs before submit (the server precondition); correlation is by exact URL first, base-domain only as fallback, and the by-domain index **must not overwrite ambiguously** (keep-first; if two submitted URLs share a domain and only one ok result returns, the domain match resolves both as present — acceptable because BO upserts per returned result; flagged so an implementer keeps the keep-first rule rather than last-wins).

**Internals:**
1. `client_job_id` ← caller-supplied (§5.4).
2. **Submit:** `call_api_hellopro('POST','detection_site_fr-service','/api/v1/detect-batch-async', $payload, false, DETECTION_ASYNC_SUBMIT_TIMEOUT_S, $headers, DETECTION_CONNECT_TIMEOUT_S)`. Reuse the existing 503/`Retry-After`/transient-code retry loop from `detectBatchUrls` — **but** if a 503 body has `retryable:false`, short-circuit immediately to the `catch` path (do not burn the retry budget on a kill-switch / Redis-down condition). Obtain `job_id` (handles both 202 and the 200 existing-job case identically).
3. **Poll loop:** `GET /api/v1/detect-batch-async/{job_id}` with `DETECTION_ASYNC_POLL_TIMEOUT_S`. Sleep `min(max(poll_after_seconds, DETECTION_ASYNC_POLL_MIN_S), remaining_budget)` between polls. Continue until terminal status or total elapsed > `DETECTION_ASYNC_MAX_WAIT_S`. `404` → treat as `stale`. `503` → honor `Retry-After`, backoff, continue.
4. Map terminal → return shape. `completed` → `results` from body, `incomplete_urls=[]`. `failed`/`stale`/`timeout` → `results` = partial completed items from body (may be empty), `incomplete_urls` = distinct submitted URLs absent from `results` per the correlation contract.

`detectBatchUrlsAsync` **throws** (`DetectionApiException`, like sync) only when submit cannot succeed (after retries, or on a `retryable:false` 503) — so callers' existing `catch` still guards the transport-failure path (enqueues whole batch as today).

### 5.2 New BO constants (near `DETECTION_REQUEST_TIMEOUT_S`)
```php
const DETECTION_ASYNC_SUBMIT_TIMEOUT_S = 30;
const DETECTION_ASYNC_POLL_TIMEOUT_S   = 15;
const DETECTION_ASYNC_MAX_WAIT_S       = 1800;   // per-job wall-clock budget (30 min)
const DETECTION_ASYNC_POLL_MIN_S       = 5;
const DETECTION_ASYNC_BATCH_SIZE       = 100;
```
**Load-bearing invariant (state, do not rely on coincidence):** `DETECTION_ASYNC_MAX_WAIT_S (1800) < JOB_RESULT_TTL_S (3600) ≤ JOB_TTL_ACTIVE_S (7200)`. This guarantees a poll *within budget* can never `404` on a job that actually completed (which would lose results and re-enqueue a fully-successful batch). If any of these constants change, this ordering must be preserved.

### 5.3 Migrations

**Migration 1 — `script_identifier_site_fr_v2.php`:**
- `array_chunk($tab_siteweb, 5)` → `array_chunk($tab_siteweb, DETECTION_ASYNC_BATCH_SIZE)`.
- Loop signature change (index does not exist today): `foreach($tab_siteweb as $chunk_idx => $payload_siteweb)`.
- `$res = detectBatchUrls($payload_siteweb);` → `$res = detectBatchUrlsAsync($payload_siteweb, 10, 'complete', false, sha1($id_upload.':'.$chunk_idx));`.
- The per-result upsert loop body is **unchanged** (it keys on the returned `$res_check['url']`; `admission_rejected` → `enfiler_url_retry_fr(..., 0)` stays). The helper already computed `incomplete_urls` correctly (correlation §5.1) — the script does not build any index.
- **Add, inside the per-chunk `foreach`, immediately after the inner per-result loop** (so it runs once per chunk against that chunk's `$res`, not once after all chunks):
  ```php
  foreach (($res['incomplete_urls'] ?? []) as $u) {
      enfiler_url_retry_fr($u, (int)$id_upload, $res['final_status'] ?? 'incomplete', 1);
      $nb_incomplete++;                       // initialize $nb_incomplete = 0 with the other counters
  }
  ```
- Surface `$nb_incomplete` in the function's return stats / operator email (parity with `nb_retry`), so re-enqueues are observable.
- Existing `catch (Exception $e)` unchanged (now fires only on submit-exhaustion / `retryable:false` / transport failure → whole-batch enqueue as today).

**Migration 2 — `script_retry_identifier_site_fr.php`:**
- `const RETRY_BATCH_SIZE = 5;` → `100`. Keep `RETRY_LIMIT_PER_RUN=200`, `RETRY_SLEEP_MS`.
- `$res = detectBatchUrls($payload_siteweb);` → `$res = detectBatchUrlsAsync($payload_siteweb, 10, 'complete', false, sha1('retry:'.$id_upload.':'.$batch_idx));` (`$batch_idx` already exists).
- Results loop unchanged: success → `marquer_succes_retry`, real non-ok / `admission_rejected` → existing handling (`admission_rejected` touch-only per the prior BO retry spec).
- **`incomplete_urls` (stale/failed/timeout) → touch-only** (update `date_derniere_tentative_dfr_retry = NOW()`, **no `nb_tentatives` increment, no status change** — same as `admission_rejected`). Rationale: a service restart is not the URL's fault and must not consume one of its 3 attempts.
  - Mapping: **build a new** `url → id_dfr_retry` index from `$batch`, keyed by `trim(trim($lig['url_dfr_retry']),'/')` (the *same* normalization the existing `$results_by_url` path uses); look up each (verbatim) incomplete URL against it; touch-only the matched `id_dfr_retry`. (The script does not hold a url→id map today — it holds `$batch` rows + result-keyed indexes — so this index is new.)
- Add `$nb_incomplete = 0;` **and** initialize the existing `$nb_admission_rejected = 0;` (currently uninitialized) in the same counters block; surface `$nb_incomplete` in the parity email line.

### 5.4 `client_job_id` semantics (BO side)
- Deterministic per batch intent, **stable across transport-level resubmits** (lost submit response / 503 retry → dedups onto the same server job).
- v2: `sha1($id_upload.':'.$chunk_idx)`. cron-retry: `sha1('retry:'.$id_upload.':'.$batch_idx)`. Disjoint namespaces → no cross-flow collision.
- **Operator re-trigger window (documented behavior):** if the v2 upload is re-triggered within `JOB_RESULT_TTL_S` (3600s), the same `client_job_id` dedups onto the **prior terminal job** and returns its cached results rather than re-detecting. This is intentional (detection is idempotent; saves recompute). To force a fresh run within the window, pass `force_redetect=true` *and* fold a coarse run-token into the key (e.g. `sha1($id_upload.':'.$chunk_idx.':'.$run_token)`) — out of scope unless operators need it.
- A genuinely later run (index expired) → fresh job.

### 5.5 Base URL
Unchanged — `call_api_hellopro('POST','detection_site_fr-service', ...)` already routes through `https://api.hellopro.eu/{service}`. New paths auto-route.

---

## 6. Failure & Restart Contract (consolidated)

| Poll `status` (or HTTP) | BO action |
|---|---|
| `pending` / `running` | sleep `min(max(poll_after_seconds, POLL_MIN), remaining_budget)`, poll again; bounded by `DETECTION_ASYNC_MAX_WAIT_S`. |
| `completed` | consume `results` (FR→`est_valide_df=1`, non-FR/real-non-ok→`0`; `admission_rejected`→`enfiler_url_retry_fr(...,0)`). |
| `failed` / `stale` | consume present partials (same loop), then re-enqueue **absent** URLs (v2 → `enfiler_url_retry_fr(...,1)`; cron → touch-only). |
| `404` on poll | treat as `stale`. |
| `503 retryable:true` on submit | honor `Retry-After`, backoff, resubmit with same `client_job_id` (idempotent). |
| `503 retryable:false` on submit | short-circuit to `catch` (kill-switch / Redis-down): whole-batch enqueue, no retry-budget burn. |
| budget exceeded | `final_status='timeout'`; re-enqueue absent URLs. Server job may still finish; idempotent re-detect later is harmless. |

**Restart walkthrough:** OOM/redeploy mid-job → asyncio task + heartbeat ticker die → `last_activity` freezes → next poll computes `stale` → BO re-enqueues absent URLs. Graceful shutdown short-circuits: `JobManager.shutdown()` cancels tasks, awaits them, then writes `failed(service_shutdown)` for non-terminal records → BO acts on the next poll without waiting `STALE_THRESHOLD_S`; jobs not marked within `GRACE` fall back to the stale path.

---

## 7. Testing Strategy

### Service (`pytest`)
- **Test seam:** prefer unit-testing `JobManager` directly, constructed with a fake/mock Redis (no lifespan needed). For endpoint tests, the client **must drive lifespan** (the existing `tests/` fixtures build `AsyncClient(app=app)` which does NOT run startup/shutdown → `app.state.job_manager` unset). Use `httpx` `ASGITransport` with lifespan or `asgi-lifespan`'s `LifespanManager`; the shutdown test runs inside a managed lifespan context. (Note: existing fixtures need updating, not just new tests.)
- **`_run_batch_core` characterization:** sync `/detect-batch` output identical before/after the refactor (same items → same `results`, counts, ordering) — guards the DRY extraction and the `progress_cb=None` no-op.
- Submit → `202` + `job_id`; `pending` record created.
- **Idempotent re-submit under concurrency:** two *concurrent* submits with the same `client_job_id` → one `job_id`, exactly one task spawned (assert via the atomic-claim path, not sequential).
- Capacity: `MAX_ACTIVE_JOBS` reached → `503` + `Retry-After` + `retryable:true`; `ASYNC_JOB_CAPACITY_REJECTED` incremented. Cap holds under concurrent submits (no overshoot).
- Kill-switch / Redis-down: `503` + `retryable:false`, no `Retry-After`; sync `/detect` + `/detect-batch` still `200`.
- Lifecycle: poll `pending`→`running`→`completed`; `results` only when terminal; terminal counts come from the core return (authoritative), not the throttled snapshot.
- **Stale not false-positive:** a job with a single slow item (heartbeat ticker firing) stays `running`, never `stale`, across > `STALE_THRESHOLD_S` of a slow item. A frozen `last_activity` (no ticker) → `stale` for both `pending` and `running`, record unmutated.
- Shutdown: cancels tasks, awaits, marks non-terminal `failed(service_shutdown)`; never overwrites an already-`completed` record.
- Index/record TTL alignment: after terminal write, idempotency index TTL == result TTL; existence guard yields a fresh job if the record is gone.
- 404 on unknown `job_id`.

### Consumer (BO)
- `detectBatchUrlsAsync` with mocked `call_api_hellopro`: submit→job_id; poll running×k then completed → `results` + `incomplete_urls=[]`.
- **Alternative-URL correlation:** a submitted URL whose ok result returns a different `url` (alt link) is matched via the by-domain index → NOT in `incomplete_urls`.
- Partial terminal (`failed`/`stale`): present partials consumed; `incomplete_urls` = absent submitted URLs only (a present non-ok URL is excluded).
- 404 on poll → `stale`. Budget exceeded → `final_status='timeout'`, `incomplete_urls` = absent.
- Submit `503 retryable:true` then `202` → single logical job (same `client_job_id`). Submit `503 retryable:false` → immediate `catch`, no retry.
- Migration 1: `incomplete_urls` enqueue runs per-chunk; `$nb_incomplete` surfaced. Migration 2: incomplete → touch-only via the new `url→id_dfr_retry` index, `nb_tentatives` unchanged; counters initialized.
- Migration smoke (mirrors `pct_smoke_detection_contract_rindra_BO.php`): one URL through each migrated path against a mocked service.

---

## 8. Rollout / Deploy Gate
1. **RAG-HP-PUB first** (service async endpoints) — additive, sync path untouched; safe before BO. BO cannot call the new path until it exists; until then nothing references it.
2. Verify on the live service: submit a small async job via the gateway, poll to `completed`, confirm `/metrics` shows `detect_async_jobs_*` + `detect_async_admission_rejected_total`.
3. **Hellopro second** (BO migrations) — only after the service endpoints are live.
4. **Admission-isolation gate:** before/just-after BO cutover, confirm `detect_admission_rejected_total` (prod pool, fed by crawler/sync) does **not** climb when async jobs run — i.e. the sub-pool isolation works. If it does climb, lower `ASYNC_ADMISSION_MAX_SLOTS` / `MAX_ACTIVE_JOBS`.
5. Observe one full cron cycle of `script_retry_identifier_site_fr.php` + one manual `script_identifier_site_fr_v2.php` upload. Watch `detect_async_jobs_terminal{status}`, `ASYNC_JOBS_ACTIVE`, both admission counters, browser semaphore waiters, and BO `[detection-langue-fr]` logs.
6. Kill-switch: `ASYNC_JOBS_ENABLED=false` → submit 503 `retryable:false`; BO callers fall to `catch` → `domaine_fr_retry` (degraded-but-safe), no retry-budget burn.

---

## 9. Deferred Follow-Ups
- Migrate the remaining 5 consumers once the pattern is proven.
- Tune `ASYNC_ADMISSION_MAX_SLOTS` / `MAX_ACTIVE_JOBS` from observed pressure.
- Job cancellation `DELETE /{job_id}`.
- Approach-B backend swap (dedicated worker + broker) if volume outgrows single-replica — **no BO change required**.
- Operator-forced fresh re-run via run-token in `client_job_id` (§5.4) if needed.
- Optional: persist input URL list + startup resume (only if fail-fast re-enqueue proves too lossy — unlikely given idempotency).

---

## 10. Risks
- **Coroutine accumulation** under many concurrent large jobs — bounded by `MAX_ACTIVE_JOBS`; the async sub-pool + browser semaphore are the throughput bound. Observe `ASYNC_JOBS_ACTIVE`.
- **Async vs crawler/sync contention** — mitigated by the dedicated sub-pool (§4.11) which guarantees the prod 8 slots stay available; the deploy gate (§8.4) verifies isolation empirically.
- **Redis dependency for async** — explicit 503 (`retryable:false`) + kill-switch; sync unaffected.
- **`_run_batch_core` refactor regressing sync** — characterization test + isolated refactor commit (progress_cb plumbing included in that commit).
- **Cron-retry `incomplete` touch-only forever under chronic restarts** — acceptable; the daily cron keeps retrying and operators watch restart metrics. Not a silent data loss (rows stay `statut=0`, visible).
- **Correlation by base-domain fallback** could, for two same-domain submitted URLs, mark both present off one ok result — accepted (BO upserts per returned result; keep-first index rule documented).
