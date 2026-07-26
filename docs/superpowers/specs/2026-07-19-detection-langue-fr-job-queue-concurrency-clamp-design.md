# Detection-Langue-FR — Async Job Queue (P0) + Server-Side Concurrency Clamp (P1) — Design

**Date:** 2026-07-19
**Status:** Approved (implemented same day)
**Scope:** `apps-microservices/api-detection-langue-fr` only. No caller change, no API-contract change.
**Related:** `2026-06-01-detection-langue-fr-async-job-api-design.md` (adds scheduling to it), `2026-07-18-detection-langue-fr-transient-error-retry-design.md` (Pass-2 retry — this spec removes most of what Pass 2 had to mop up), `2026-04-20-detection-langue-fr-concurrency-defense-design.md` § B.1 (deployed limits).

---

## Problem

Deployed capacity ladder (docker-compose): `BROWSER_SEMAPHORE_SIZE=6` < `ADMISSION_MAX_SLOTS=8` < BO `max_concurrency=10` < `MAX_ACTIVE_JOBS=8` concurrent jobs.

1. **No job scheduling.** `JobManager.submit` spawns `asyncio.create_task(_run_job(...))` immediately (`async_jobs.py:183`): up to 8 jobs run their batches SIMULTANEOUSLY, each with its own `Semaphore(10)` — worst case ~80 item-tasks against 8 admission slots and 6 browsers. Items sit in the browser queue while their 300s `wait_for` budget burns → the `Timeout global item (300s)` storms observed on 2026-07-12 (33/55 "non-FR"), plus `admission_rejected` bursts.
2. **Guaranteed per-batch bounce.** Even a single job at `max_concurrency=10` on 8 admission slots instantly rejects ~2 items per chunk (fast-fail, recovered by Pass 2 — but pure churn, on every chunk).

Total throughput is browser-bound (6) regardless; running jobs 8-wide adds only failure modes, zero throughput.

## Goals

- **P0:** jobs execute from a FIFO queue with a small worker pool (default 1). `MAX_ACTIVE_JOBS` keeps its exact backpressure contract (503 + Retry-After when pending+running hits the cap — `_inflight` already counts submitted-not-finished, unchanged).
- **P0:** a queued job polls as `pending`, never falsely `stale` (a keeper refreshes `last_activity` for queued records); a genuinely dead service (restart with queued jobs) still surfaces `stale` within `STALE_THRESHOLD_S`.
- **P0:** shutdown marks queued jobs `failed(service_shutdown)` like running ones (fail-fast contract preserved).
- **P1:** server-side clamp of per-batch concurrency to `ADMISSION_MAX_SLOTS` — only for batches that actually fetch. `html_content`-provided batches (crawler-service) are NOT clamped (they bypass admission entirely).

## Non-Goals

- Changing the submit/poll HTTP contract, `Retry-After` semantics, or the PHP client. A queued job is indistinguishable from a slow-starting one.
- Multi-worker fairness/priorities (`JOB_WORKER_CONCURRENCY` env exists; default 1 = serial; raising it is an ops decision after measuring).
- Job resume after restart (2026-06-01 fail-fast decision stands).
- Raising `BROWSER_SEMAPHORE_SIZE`/`mem_limit` (operator experiment, documented separately).
- Fixing the pre-existing idempotency quirk where a deterministic `client_job_id` re-submitted within `JOB_RESULT_TTL_S` of a failure returns the old failed job.

## Design

### P0 — Queue + worker pool (`async_jobs.py`)

`JobManager` gains:

```python
self._queue: asyncio.Queue = asyncio.Queue()   # (job_id, cjid, items, mode, opts)
self._queued_ids: set[str] = set()             # ids awaiting pickup (keeper scope)
self._workers: list[asyncio.Task] = []         # JOB_WORKER_CONCURRENCY consumers
self._keeper: asyncio.Task | None = None       # queued-record heartbeat
```

- **submit:** identical through capacity reserve + record write; then `_ensure_workers()` (lazy spawn, once) and `queue.put_nowait(...)` instead of `create_task`. Still returns `(job_id, 202)`.
- **worker loop:** `get()` → remove from `_queued_ids` → `create_task(_run_job(...))`, registered in `_job_tasks` with the existing `_on_done` callback (so `_inflight` accounting and metrics are untouched) → `await asyncio.wait([task])` (does not propagate job exceptions or job-task cancellation into the worker; worker's own cancellation stops the wait).
- **keeper loop:** every `HEARTBEAT_INTERVAL_S`, bump `last_activity` on each queued record still `pending`. This keeps `poll_status` from deriving `stale` for healthy queued jobs, while a dead process (no keeper) naturally goes stale after `STALE_THRESHOLD_S` — restart semantics preserved.
- **shutdown:** cancel keeper + workers first, drain the queue marking each entry `failed(service_shutdown)` (result TTL), then the existing cancel-and-mark for running tasks.

Execution concurrency = `JOB_WORKER_CONCURRENCY` (config, default **1**). Capacity/backpressure = `MAX_ACTIVE_JOBS` (unchanged meaning: pending+running).

Latency envelope: a full queue of 8 jobs × 10 items at 6 browsers ≈ 2-4 min/job → worst-case last job ≈ 25-30 min, inside the PHP client's 1800s poll deadline. If this proves tight, lower `MAX_ACTIVE_JOBS` (earlier 503 backpressure; the PHP client already retries submits with Retry-After) rather than raising worker concurrency.

### P1 — Concurrency clamp (`routes.py::_run_batch_core`)

```python
def _effective_batch_concurrency(items, requested: int) -> int:
    # html_content-only batches (crawler) never fetch → never touch admission.
    if all(item.html_content is not None for item in items):
        return requested
    from main import _prod_admission   # lazy, same pattern as _fetch_with_admission
    return min(requested, _prod_admission.max_slots)
```

Used for the batch semaphore and the stagger cap. With compose's `ADMISSION_MAX_SLOTS=8`, a BO chunk at `max_concurrency=10` runs at 8 → zero structural `admission_rejected` in the single-job case. Callers stay untouched; if ops changes the deployed slots, the clamp follows automatically.

### Observability

- New gauge `detect_async_jobs_queued` (queue depth). `detect_async_jobs_active` keeps meaning "reserved (pending+running)".
- Worker pickup logged: `[async-jobs] worker picked job {id} (queued {n}s)`.

## Config

| Variable | Default | Purpose |
|---|---|---|
| `JOB_WORKER_CONCURRENCY` | `1` | Async jobs executing simultaneously. Queue absorbs the rest up to `MAX_ACTIVE_JOBS`. |

## Testing

- `test_async_jobmanager.py`: jobs run serially (concurrency counter in a fake runner never exceeds 1) and FIFO; all queued jobs complete; capacity counts pending+running (unchanged assertion); keeper refreshes `last_activity` of a queued job (record read after > heartbeat interval); `poll_status` of a queued-but-kept record stays `pending`; shutdown marks queued (not-yet-started) job `failed(service_shutdown)`; `JOB_WORKER_CONCURRENCY=2` runs two jobs concurrently. Existing tests migrate from `gather(jm._job_tasks)` to a poll-until-terminal helper (racy with a queue).
- `routes` tests: `_effective_batch_concurrency` pure cases (fetch batch clamped to admission slots; html_content batch not clamped; mixed batch clamped); end-to-end batch with a 2-slot admission controller and 4 fetch items yields zero `admission_rejected`.

## Rollout

Ship enabled (no flag: queueing at worker-concurrency 1 is strictly safer than the 8-wide stampede; `JOB_WORKER_CONCURRENCY` is the tuning knob and `MAX_ACTIVE_JOBS` the rollback-ish lever). Redeploy service; no compose change required. Measure: `detect_async_jobs_queued`, `Timeout global item` rate, `admission_rejected` rate on the next multi-run BO day.

## Addendum 2026-07-26 — terminal-write loss (job `9597267b`, post-mortem)

**Incident:** a 5-item batch finished 15.8s with 5/5 OK (`[BATCH] Termine`), yet the job record
stayed `running` / `done=5` / `success_count=0` / `results=null` — the BO polled until stale and
discarded the (successful) run. The record content was exactly the heartbeat's last copy: the
terminal write never landed, and the old failure path was `try: write … except: pass` — fully
silent, no log, no retry, and the worker's watchdog can't help (the task finished "normally").

**Mechanism (prime suspect):** `hb.cancel()` fired while the heartbeat was awaiting a Redis
command; a cancelled in-flight command can leave the pooled connection with a pending unread
response, and the terminal `get`+`write` immediately reused that connection (LIFO pool) — both
failed, both were swallowed. Poll reads used other connections and stayed healthy.

**Fix (same commit):**
1. Cooperative heartbeat stop — `asyncio.Event` + bounded await instead of `cancel()`: the
   in-flight Redis command completes cleanly before the terminal sequence starts. (`cancel()` is
   kept only on the `CancelledError`/shutdown path, where the process is dying anyway.)
2. `_write_terminal`: terminal record writes (completed AND failed) are retried 3× with backoff;
   each failure logs a warning, definitive loss logs `écriture terminale PERDUE` at ERROR level —
   the silent `except: pass` is gone.
3. Completion/failure log lines (`[async-jobs] job X completed: …`) — the success path previously
   logged nothing, which made this incident diagnosable only from the BO side.

Degraded behavior if all retries fail is unchanged by design (record freezes → poll derives
`stale` → BO fail-fast re-submits) but is now observable in the service logs.
