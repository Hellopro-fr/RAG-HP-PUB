# image-comparison-service robustness + download-perf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound every comparison job to a terminal state within a deadline and stop one slow/dead image URL from gating/hanging a job — fixing the 62-66s slowness and the rare `HTTP 0 / poll-deadline`.

**Architecture:** Layered bounding (no watchdog): per-image download `wait_for` cap + granular `httpx.Timeout` + skip-retry-4xx (B); per-job `asyncio.wait_for` → `failed` (A2); strong ref on the fire-and-forget task (A3); async-submit 503 backpressure (D). Config knobs are env-tunable. Status/result JSON, keys, TTL, and the contract stay unchanged except `/start sync:false` may now 503.

**Tech Stack:** Python 3.11, FastAPI, httpx, redis (via `common_utils`). RAG-HP-PUB, branch `features/poc` (tip has the cache_service migration `7517ee8a` + spec `ec6108f7`). Remote-only.

Ref spec: `docs/superpowers/specs/2026-06-18-image-comparison-robustness-download-perf-design.md`.

**Repo root:** `D:\DevHellopro\Workspaces\RAG-HP-PUB` (paths below relative to it; all under `apps-microservices/image-comparison-service/`). Commits **both EN+FR**; do NOT push (user controls push/deploy).

**Remote-only verify:** `python -m py_compile <files>` (local) + `docker build` + deploy smoke on the VM (user). No local Redis/build. No image-comparison unit-test harness assumed (the httpx/Redis async paths lack a clean injection seam) — if one exists, extend it; otherwise py_compile + smoke.

**Dependencies:** T2, T3, T4 each ← T1 (they reference the new `settings.*`). T2/T3/T4 are mutually independent (different files).

---

### Task 1: Config — add bounding knobs

**Goal:** 5 env-tunable settings with conservative defaults; no behavior change (unused until T2-T4).

**Files:** Modify `app/core/config.py`

**Acceptance Criteria:**
- [ ] `IMG_DOWNLOAD_CONNECT_TIMEOUT_S` (3.0), `IMG_DOWNLOAD_READ_TIMEOUT_S` (15.0), `IMG_DOWNLOAD_CAP_S` (20.0), `PROCESSING_DEADLINE_S` (120.0), `ASYNC_BACKLOG_FACTOR` (4) added to `Settings`, each `os.getenv` with default.
- [ ] `python -m py_compile app/core/config.py` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/config.py` → success; `python -c "from app.core.config import settings; print(settings.PROCESSING_DEADLINE_S, settings.IMG_DOWNLOAD_CAP_S, settings.ASYNC_BACKLOG_FACTOR)"` (from the service dir, if runnable) → `120.0 20.0 4`.

**Steps:**

- [ ] **Step 1: Add the settings**

In `app/core/config.py`, the current `Settings` class ends with `JOB_RESULT_TTL` then `settings = Settings()`:
```python
    # Data Retention
    # Time in seconds to keep job status and results in Redis (Default: 24 hours)
    JOB_RESULT_TTL: int = int(os.getenv("JOB_RESULT_TTL", "86400"))

settings = Settings()
```
Insert the new block between `JOB_RESULT_TTL` and `settings = Settings()`:
```python
    # Data Retention
    # Time in seconds to keep job status and results in Redis (Default: 24 hours)
    JOB_RESULT_TTL: int = int(os.getenv("JOB_RESULT_TTL", "86400"))

    # --- Bounding knobs (Design 1: bounded downloads + per-job timeout + backpressure) ---
    # Per-image download timeouts (granular). READ is the inter-byte cap — flagged for
    # later p95-based tuning (a too-low value drops genuinely-slow images -> failed_images).
    IMG_DOWNLOAD_CONNECT_TIMEOUT_S: float = float(os.getenv("IMG_DOWNLOAD_CONNECT_TIMEOUT_S", "3"))
    IMG_DOWNLOAD_READ_TIMEOUT_S: float = float(os.getenv("IMG_DOWNLOAD_READ_TIMEOUT_S", "15"))
    # Per-image total wall cap (>= read timeout): one slow/dead URL fails here, never gates the job.
    IMG_DOWNLOAD_CAP_S: float = float(os.getenv("IMG_DOWNLOAD_CAP_S", "20"))
    # Per-job deadline (s): above a real ~40s job, below the BO client's 300s.
    PROCESSING_DEADLINE_S: float = float(os.getenv("PROCESSING_DEADLINE_S", "120"))
    # Async-submit backlog cap = MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR (per replica).
    ASYNC_BACKLOG_FACTOR: int = int(os.getenv("ASYNC_BACKLOG_FACTOR", "4"))

settings = Settings()
```

- [ ] **Step 2: Lint + commit (both EN+FR)**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/config.py` → success.
```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/app/core/config.py
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "feat(image-comparison): add download/timeout/backpressure config knobs" -m "EN: Add env-tunable IMG_DOWNLOAD_CONNECT/READ_TIMEOUT_S, IMG_DOWNLOAD_CAP_S, PROCESSING_DEADLINE_S, ASYNC_BACKLOG_FACTOR with conservative defaults (used by the bounded-downloads + per-job-timeout + backpressure work). No behavior change yet." -m "FR: Ajoute des reglages env IMG_DOWNLOAD_CONNECT/READ_TIMEOUT_S, IMG_DOWNLOAD_CAP_S, PROCESSING_DEADLINE_S, ASYNC_BACKLOG_FACTOR avec defauts conservateurs (utilises par le bornage downloads + timeout par job + backpressure). Aucun changement de comportement pour l'instant."
```

---

### Task 2: B — bounded downloads (`image_processor.py`)

**Goal:** Granular `httpx.Timeout` + skip-retry-on-4xx + per-image `wait_for` cap so one slow/dead URL fails fast (→ `failed_images`) without gating the gather.

**Files:** Modify `app/core/image_processor.py` (`load_images`)

**blockedBy:** Task 1.

**Acceptance Criteria:**
- [ ] `httpx.AsyncClient` uses `httpx.Timeout(connect=…, read=…, write=…, pool=…)` from settings (not `timeout=30.0`).
- [ ] `download_with_retry` returns immediately on a 4xx response (no retry).
- [ ] Each download wrapped in `asyncio.wait_for(download_with_retry(inp), settings.IMG_DOWNLOAD_CAP_S)`; a per-image timeout → `failed_images` (via existing `return_exceptions=True` handling), not gating others.
- [ ] `python -m py_compile` clean. `import httpx`, `import asyncio`, `from app.core.config import settings` all already present.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/image_processor.py` → success. Smoke (VM): a job with a dead image URL finishes in ≤ ~`IMG_DOWNLOAD_CAP_S`, the dead image in `failed_images`.

**Steps:**

- [ ] **Step 1: Granular timeout (B4)**

In `load_images`, replace:
```python
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers=ImageProcessor.DOWNLOAD_HEADERS,
                verify=False,
                proxy=proxy_url
            ) as client:
```
with:
```python
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.IMG_DOWNLOAD_CONNECT_TIMEOUT_S,
                    read=settings.IMG_DOWNLOAD_READ_TIMEOUT_S,
                    write=settings.IMG_DOWNLOAD_READ_TIMEOUT_S,
                    pool=settings.IMG_DOWNLOAD_CONNECT_TIMEOUT_S,
                ),
                follow_redirects=True,
                headers=ImageProcessor.DOWNLOAD_HEADERS,
                verify=False,
                proxy=proxy_url
            ) as client:
```

- [ ] **Step 2: Skip retry on 4xx (B4)**

In `download_with_retry`, replace:
```python
                        try:
                            resp = await client.get(str(inp.url))
                            if resp.status_code == 200:
                                return resp
                            if attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            logger.warning(f"HTTP {resp.status_code} for {inp.id} ({inp.url}) after retry")
                            return resp
```
with:
```python
                        try:
                            resp = await client.get(str(inp.url))
                            if resp.status_code == 200:
                                return resp
                            # 4xx is terminal (404/403 won't change) — don't waste a retry.
                            if 400 <= resp.status_code < 500:
                                logger.warning(f"HTTP {resp.status_code} for {inp.id} ({inp.url}) — no retry (4xx)")
                                return resp
                            if attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            logger.warning(f"HTTP {resp.status_code} for {inp.id} ({inp.url}) after retry")
                            return resp
```

- [ ] **Step 3: Per-image cap (B5)**

Replace the gather:
```python
                # Execute concurrently with retry
                responses = await asyncio.gather(
                    *[download_with_retry(inp) for inp in download_tasks],
                    return_exceptions=True
                )
```
with:
```python
                # Execute concurrently with retry, each download hard-capped so one
                # slow/dead URL fails fast (-> failed_images) without gating the others.
                responses = await asyncio.gather(
                    *[asyncio.wait_for(download_with_retry(inp), settings.IMG_DOWNLOAD_CAP_S)
                      for inp in download_tasks],
                    return_exceptions=True
                )
```
(The existing loop below already does `if isinstance(response, Exception): failed.append(...)`, so a per-image `asyncio.TimeoutError` lands in `failed_images`. No other change.)

- [ ] **Step 4: Lint + commit (both EN+FR)**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/image_processor.py` → success.
```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/app/core/image_processor.py
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "perf(image-comparison): bound downloads (granular timeout + skip-4xx + per-image cap)" -m "EN: load_images uses a granular httpx.Timeout, skips retry on 4xx, and caps each download via asyncio.wait_for(IMG_DOWNLOAD_CAP_S) so one slow/dead URL fails fast into failed_images instead of gating the whole gather (was ~62s). Behavior safe: capped images -> failed_images -> keep-all downstream." -m "FR: load_images utilise un httpx.Timeout granulaire, ne retente pas sur 4xx, et borne chaque download via asyncio.wait_for(IMG_DOWNLOAD_CAP_S) pour qu'une URL lente/morte echoue vite vers failed_images au lieu de bloquer tout le gather (~62s avant). Comportement sur : images bornees -> failed_images -> keep-all en aval."
```

---

### Task 3: A2+A3 — per-job timeout + non-GC'd task (`job_manager.py`)

**Goal:** Every job reaches `finished`/`failed` within `PROCESSING_DEADLINE_S`; the fire-and-forget task can't be GC'd.

**Files:** Modify `app/core/job_manager.py`

**blockedBy:** Task 1.

**Acceptance Criteria:**
- [ ] `__init__` adds `self._background_tasks: set = set()`.
- [ ] New `_mark_failed_timeout(job_id)` helper writes `status=failed` (error `timeout: exceeded {PROCESSING_DEADLINE_S}s`) via `cache_service.redis_client.set` (guarded).
- [ ] `submit_job_async`'s `_run_and_release` wraps `process_job_logic` in `asyncio.wait_for(..., settings.PROCESSING_DEADLINE_S)`; on `asyncio.TimeoutError` → `_mark_failed_timeout`; the create_task handle is stored in `_background_tasks` + discarded on done.
- [ ] `submit_job_sync` wraps in `asyncio.wait_for(...)`; on `asyncio.TimeoutError` → `_mark_failed_timeout` + re-raise.
- [ ] `process_job_logic` UNCHANGED (its `except Exception` must not catch `CancelledError`; its `async with semaphore` + `finally: safe_decrement_key` heal slot+counter on cancel).
- [ ] `python -m py_compile` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/core/job_manager.py` → success. Smoke (VM): a job that would hang → `status=failed` at ~`PROCESSING_DEADLINE_S`; `comparator:running_count` stays ≥ 0.

**Steps:**

- [ ] **Step 1: `__init__` — task set**

Replace:
```python
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        # Track local active jobs manually since semaphore._value is internal/implementation specific
        self.local_active_jobs = 0
```
with:
```python
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        # Track local active jobs manually since semaphore._value is internal/implementation specific
        self.local_active_jobs = 0
        # Strong refs to fire-and-forget tasks — without this the event loop only keeps
        # a weak ref and a job can be garbage-collected mid-flight.
        self._background_tasks: set = set()
```

- [ ] **Step 2: Add the timeout-failed helper** (place it right before `submit_job_async`)

```python
    async def _mark_failed_timeout(self, job_id: str) -> None:
        """Write a terminal 'failed' status for a job that exceeded PROCESSING_DEADLINE_S."""
        logger.error(f"Job {job_id}: exceeded PROCESSING_DEADLINE_S={settings.PROCESSING_DEADLINE_S}s — marking failed")
        if cache_service.redis_client:
            st = JobStatus(
                job_id=job_id,
                status="failed",
                error=f"timeout: exceeded {settings.PROCESSING_DEADLINE_S}s",
                progress=0.0,
            )
            await cache_service.redis_client.set(f"job:{job_id}:status", st.json(), ex=settings.JOB_RESULT_TTL)
```

- [ ] **Step 3: `submit_job_async` — wait_for + timeout-fail + strong task ref**

Replace:
```python
        async def _run_and_release():
            try:
                await self.process_job_logic(job_id, images, threshold)
            finally:
                self.release_local_slot()

        asyncio.create_task(_run_and_release())
```
with:
```python
        async def _run_and_release():
            try:
                await asyncio.wait_for(
                    self.process_job_logic(job_id, images, threshold),
                    timeout=settings.PROCESSING_DEADLINE_S,
                )
            except asyncio.TimeoutError:
                # process_job_logic got CancelledError -> its semaphore + finally
                # (safe_decrement_key) already ran; here we record the terminal failure.
                await self._mark_failed_timeout(job_id)
            finally:
                self.release_local_slot()

        task = asyncio.create_task(_run_and_release())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
```

- [ ] **Step 4: `submit_job_sync` — wait_for + timeout-fail + re-raise**

Replace:
```python
        return await self.process_job_logic(job_id, images, threshold)
```
with:
```python
        try:
            return await asyncio.wait_for(
                self.process_job_logic(job_id, images, threshold),
                timeout=settings.PROCESSING_DEADLINE_S,
            )
        except asyncio.TimeoutError:
            await self._mark_failed_timeout(job_id)
            raise
```
(The router's `except Exception` turns the re-raised `asyncio.TimeoutError` into a 500 for the blocking caller. `process_job_logic` itself is untouched.)

- [ ] **Step 5: Lint + commit (both EN+FR)**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/core/job_manager.py` → success.
```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/app/core/job_manager.py
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "fix(image-comparison): per-job timeout + strong task ref (no stuck/GC'd jobs)" -m "EN: Wrap process_job_logic in asyncio.wait_for(PROCESSING_DEADLINE_S) in both submit paths; on timeout write a terminal failed status (the inner coroutine's semaphore + finally safe_decrement heal slot+counter on cancel). Keep a strong ref to the fire-and-forget create_task so it can't be GC'd mid-flight. Fixes the rare HTTP 0/poll-deadline server-side." -m "FR: Encadre process_job_logic dans asyncio.wait_for(PROCESSING_DEADLINE_S) dans les deux chemins de submit ; au timeout, ecrit un statut failed terminal (le semaphore + finally safe_decrement de la coroutine interne reparent slot+compteur a l'annulation). Garde une reference forte sur la task create_task pour qu'elle ne soit pas GC mid-flight. Corrige le rare poll-deadline HTTP 0 cote serveur."
```

---

### Task 4: D — async-submit backpressure (`comparator.py`)

**Goal:** The async `/start` path returns 503 when the replica's backlog is full (it never rejects today).

**Files:** Modify `app/router/comparator.py` (the `else` / `sync:false` branch of `start_comparison`)

**blockedBy:** Task 1.

**Acceptance Criteria:**
- [ ] Before `submit_job_async`, if `job_manager.local_active_jobs >= settings.MAX_CONCURRENT_JOBS * settings.ASYNC_BACKLOG_FACTOR` → `raise HTTPException(503, …)`.
- [ ] Otherwise unchanged (202 + JobResponse). `settings` and `status` already imported.
- [ ] `python -m py_compile` clean.

**Verify:** `python -m py_compile apps-microservices/image-comparison-service/app/router/comparator.py` → success. Smoke (VM): a submit flood beyond the backlog cap → some 503s; the BO client backs off (treats 503 transient).

**Steps:**

- [ ] **Step 1: Add the backlog 503**

Replace:
```python
    else:
        await job_manager.submit_job_async(job_id, request.images, request.threshold)
        return JobResponse(
            message="Comparison job accepted and started.",
            job_id=job_id
        )
```
with:
```python
    else:
        # Backpressure: the async path otherwise queues unbounded detached tasks.
        # Shed load when the local backlog is deep so Nginx fails over / client backs off.
        backlog_cap = settings.MAX_CONCURRENT_JOBS * settings.ASYNC_BACKLOG_FACTOR
        if job_manager.local_active_jobs >= backlog_cap:
            logger.warning(
                f"Returning 503 (async backlog): local_active={job_manager.local_active_jobs}/{backlog_cap}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Instance backlog full. Please retry (triggers Nginx failover)."
            )
        await job_manager.submit_job_async(job_id, request.images, request.threshold)
        return JobResponse(
            message="Comparison job accepted and started.",
            job_id=job_id
        )
```

- [ ] **Step 2: Update the docstring** (optional but accurate) — change the `If sync is False` line from "Always accepts (queues) the job." to "Accepts (queues) the job, or 503 when the local backlog is full."

- [ ] **Step 3: Lint + commit (both EN+FR)**

Run: `python -m py_compile apps-microservices/image-comparison-service/app/router/comparator.py` → success.
```bash
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" add apps-microservices/image-comparison-service/app/router/comparator.py
git -C "D:/DevHellopro/Workspaces/RAG-HP-PUB" commit -m "feat(image-comparison): async-submit backpressure (503 when backlog full)" -m "EN: /start sync:false now returns 503 when local_active_jobs >= MAX_CONCURRENT_JOBS*ASYNC_BACKLOG_FACTOR, mirroring the sync path, instead of queuing unbounded detached tasks. The BO client already treats 503 as transient (backoff)." -m "FR: /start sync:false renvoie desormais 503 quand local_active_jobs >= MAX_CONCURRENT_JOBS*ASYNC_BACKLOG_FACTOR, comme le chemin sync, au lieu d'empiler des tasks detachees sans borne. Le client BO traite deja 503 comme transitoire (backoff)."
```

---

## Self-Review (done)

**1. Spec coverage:** §3.5 config → T1. §3.1 B (granular timeout + skip-4xx + per-image cap) → T2 Steps 1-3. §3.2 A2 (wait_for both paths + failed-write in wrapper + process_job_logic untouched) → T3 Steps 2-4. §3.3 A3 (task set + add/discard) → T3 Steps 1,3. §3.4 D (503 backlog) → T4. §4 contract: keys/TTL/JSON unchanged (no schema edits anywhere; only `_mark_failed_timeout` reuses the existing `JobStatus` shape); only `/start sync:false` gains a 503 → T4 + docstring. §5 verify → each task's Verify.

**2. Placeholders:** none — every step shows exact before/after.

**3. Type/consistency:** `settings.IMG_DOWNLOAD_CONNECT_TIMEOUT_S / READ_TIMEOUT_S / CAP_S / PROCESSING_DEADLINE_S / ASYNC_BACKLOG_FACTOR` defined in T1, consumed verbatim in T2/T3/T4. `_mark_failed_timeout` defined (T3 Step 2) before use (Steps 3-4). `JobStatus` fields (`job_id/status/error/progress`) match the existing model. `asyncio`/`httpx`/`settings`/`HTTPException`/`status`/`JobResponse` already imported in their files (verified). `process_job_logic` signature/behavior unchanged.

**Out of scope (per spec §6):** A1 watchdog (dropped), C feature cache (separate design).
