# Design — image-comparison-service: bounded downloads + per-job timeout + backpressure (A2/A3 · B · D)

**Date:** 2026-06-18
**Status:** Validated (design)
**Author:** Rindra + Claude
**Scope:** "Design 1" = Groups **B** (bounded downloads), **A2+A3** (per-job timeout + non-GC'd task), **D** (async-submit backpressure). **A1 (watchdog) dropped** — superseded (see §6). **C (feature cache) is a separate design.**
**Service:** `apps-microservices/image-comparison-service` (RAG-HP-PUB), branch `features/poc`. Depends on the just-merged cache_service migration (`7517ee8a`).

---

## 1. Objective

Make every comparison job reach a **terminal state within a bounded time**, and stop a single slow/dead image URL from gating or hanging a job. This fixes both observed problems:
- **Slowness:** jobs take 37-66s, ~95-99% of it in `load_images`, gated by the slowest URL (a dead URL costs ~62s via the 30s timeout + retry).
- **Rare `HTTP 0 / poll-deadline`:** an in-process job that never reaches a terminal state → the BO client polls `/results` until its 300s deadline (freezing a Phase-2 worker 5 min).

Approach: **layered bounding, no external scanner** — per-image download cap (B) → per-job `wait_for` (A2) → non-GC'd task (A3) → submit backpressure (D).

## 2. Context (verified, this session)

- **Download-bound:** prod logs — `load_images` is 95-99% of job time (inputs 2→62s, 5→66s, 73→37s, 88→40s); `compare_batch` <1s even for 88. `image_processor.load_images` does `asyncio.gather` over `download_with_retry` with `httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False, proxy=APIFY_PROXY)`; retry = 1 attempt + 2s sleep on ANY non-200/exception → a dead URL ≈ 30s+2s+30s ≈ 62s, and `gather` waits for the slowest → it gates the whole job. NetIO 5-6 GB/replica, CPU idle, RAM ~⅓ of 2 GiB.
- **Stuck-job cause is in-process:** `docker inspect` — all 5 replicas up since 06-12, `OOMKilled:false`, no restart at the 06-17 21:41 error → **container death ruled out**. The stuck job was a GC-dropped `asyncio.create_task` (`submit_job_async` discards the task handle → weak ref → GC-able mid-flight) or a download evading httpx's inter-byte 30s read-timeout (slow-trickle host). Either → `status` stuck `processing` → poller waits the full 300s.
- **Capacity:** `MAX_CONCURRENT_JOBS=4`, 5 replicas (=20 global slots), `restart:unless-stopped`, no healthcheck. The async `/start` path (`submit_job_async`) never rejects (unbounded detached-task backlog).
- `cache_service` (post-migration) bounds every Redis op at `socket_timeout=10` and the `finally` decrement uses `safe_decrement_key`.

## 3. Design

### 3.1. B — bounded downloads (`app/core/image_processor.py: load_images`)
- Replace `timeout=30.0` with `httpx.Timeout(connect=IMG_DOWNLOAD_CONNECT_TIMEOUT_S, read=IMG_DOWNLOAD_READ_TIMEOUT_S, write=IMG_DOWNLOAD_READ_TIMEOUT_S, pool=IMG_DOWNLOAD_CONNECT_TIMEOUT_S)`.
- `download_with_retry`: on a response whose status is **4xx**, return it immediately (no retry — a 404/403 won't change). Retry only on transport exception / timeout / 5xx (keep the existing single retry + sleep for those).
- **Per-image cap (B5):** wrap each download in `asyncio.wait_for(download_with_retry(inp), IMG_DOWNLOAD_CAP_S)` within the gathered list. `gather(..., return_exceptions=True)` already maps a per-task exception → the image lands in `failed_images`; a per-image `TimeoutError` therefore drops just that image **without gating the others**. The load phase is bounded by the cap, not the worst URL.
- **Effect:** a dead/slow URL fails at ≤ cap (~20s) instead of ~62s; one bad image no longer gates the job.

### 3.2. A2 — per-job timeout (`app/core/job_manager.py`)
- Wrap the job execution in `asyncio.wait_for(self.process_job_logic(job_id, images, threshold), PROCESSING_DEADLINE_S)` in **both** `submit_job_sync` and the async wrapper `_run_and_release`.
- On `asyncio.TimeoutError` (raised to the wrapper): write `status=failed` (`error="timeout: exceeded {PROCESSING_DEADLINE_S}s"`, `ex=settings.JOB_RESULT_TTL`).
- The inner `process_job_logic` receives `CancelledError` at its current `await`; its `async with self.semaphore` releases and its `finally: await cache_service.safe_decrement_key(...)` runs → **slot + counter healed**. `process_job_logic`'s `except Exception` does NOT (and must not) catch `CancelledError` (it's `BaseException`) — the failed-status write on timeout lives in the **wrapper**, not inside `process_job_logic` (no double-write).
- Async path: a timed-out job ends `status=failed` → the Ch.D poller (`/results`→202→`/status`=`failed`) returns `[]` (keep-all) at ~`PROCESSING_DEADLINE_S`, not the client's 300s. **Server-side deadline fix.**
- Sync path (FP arsenal `sync:true`, gateway-killed at ~1s regardless): wrap for consistency; on timeout write failed + re-raise → router 500. Rarely reached.
- Edge: a job that waits > deadline for a semaphore slot is cancelled cleanly — its pre-semaphore INCR is balanced by the `finally` DECR.

### 3.3. A3 — non-GC'd task (`app/core/job_manager.py`)
- `__init__`: `self._background_tasks: set = set()`.
- `submit_job_async`: `t = asyncio.create_task(_run_and_release()); self._background_tasks.add(t); t.add_done_callback(self._background_tasks.discard)`.
- Holds a strong reference so the fire-and-forget task can't be garbage-collected mid-flight (so A2's `wait_for` reliably runs).

### 3.4. D — async-submit backpressure (`app/router/comparator.py` sync:false branch + `job_manager`)
- The async path currently does `self.local_active_jobs += 1` unconditionally and always returns 202. Add an admission cap: if `local_active_jobs >= settings.MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR`, return **503** (mirroring the sync path's existing capacity 503) instead of accepting.
- A flooded replica sheds load → Nginx failover / client backoff. The BO client (`image_comparator_submit`, post A+B-1) already treats 503 as transient (Retry-After/backoff). No client change.

### 3.5. Config (`app/core/config.py`, env-tunable, conservative defaults)
| Setting | Default | Notes |
|---|---|---|
| `IMG_DOWNLOAD_CONNECT_TIMEOUT_S` | 3 | TCP connect cap |
| `IMG_DOWNLOAD_READ_TIMEOUT_S` | 15 | inter-byte read cap — **flagged for later p95-based tuning** |
| `IMG_DOWNLOAD_CAP_S` | 20 | per-image total wall cap (≥ read timeout) |
| `PROCESSING_DEADLINE_S` | 120 | per-job cap; well above a real ~40s job, below the BO client's 300s |
| `ASYNC_BACKLOG_FACTOR` | 4 | async backlog cap = `MAX_CONCURRENT_JOBS * factor` (e.g. 16/replica) |

## 4. Behavior preservation / contract
- Keys (`job:{id}:status`/`:result`/`comparator:running_count`), TTL (`JOB_RESULT_TTL`), and the status/result JSON shape are **unchanged** (no `created_at` — A1 dropped). `/status` / `/results` / `/capacity` / `/jobs` unchanged.
- Only contract delta: `/start sync:false` may now return **503** when the replica's backlog is full — the BO client already handles 503. Documented.
- Downstream safety preserved: a timed-out/failed job and per-image `failed_images` → keep-all in the BO dedup (no wrongful deletion).
- **Accepted trade-off:** tighter download timeouts drop genuinely-slow images → lower recall (safe direction; missed dup → keep-all), tunable via env.

## 5. Verification (remote — RAG-HP-PUB)
- `python -m py_compile app/core/job_manager.py app/core/image_processor.py main.py app/core/config.py`.
- `docker build` on the VM (user).
- Smoke (deploy): a job with a dead image URL finishes in ≤ ~`IMG_DOWNLOAD_CAP_S` (not 62s); a simulated hung job → `status=failed` at ~`PROCESSING_DEADLINE_S` (not the 300s client wait); `/capacity` `comparator:running_count` stays ≥ 0; a submit flood → some 503s.
- Unit tests if a harness exists: the per-image cap, skip-retry-on-4xx, and per-job timeout are testable by injecting fake download/job callables (a small seam). Otherwise `py_compile` + smoke.

## 6. Blast radius / out of scope
- **image-comparison-service only.** Shared by Ch.D dedup + the FP arsenal (`isImagesSimilars*` / `batchCompareImagesMicroservice`) via the gateway; the only contract change (async 503) is client-handled; downloads bounded → lower recall (safe) on slow images; no data-loss path.
- **A1 (watchdog/reconcile) dropped:** A2 (in-coroutine `wait_for`) + A3 (task-ref) guarantee termination from inside the job; the `finally` + `safe_decrement_key` heal the counter; `cache_service` socket timeouts bound Redis ops; container death is ruled out. So an external scanner + a `created_at` schema field add complexity without covering a remaining known stuck-path. (If a future need arises, `cache_service` ships `delete_if_terminal`/`scan_keys_by_prefix` to add it cheaply.)
- **C (feature/pHash cache by URL)** — separate design (the NetIO win + its wrong-deletion correctness surface).

---

**End design — 2026-06-18.**
