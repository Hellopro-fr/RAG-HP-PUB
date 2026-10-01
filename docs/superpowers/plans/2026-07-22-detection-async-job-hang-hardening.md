# Detection async-job hang hardening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop one wedged browser fetch from hanging a detection job forever and freezing the single-worker FIFO queue.

**Architecture:** L1 — make browser teardown self-abort instead of awaiting a dead-pipe `browser.close()` (the root wedge), plus enforce per-op/launch timeouts (`scraper.py`). L2 — a worker watchdog that abandons an over-budget job so the queue never freezes (`async_jobs.py`). Sub-fixes — bound the last unwrapped `first_match` Pass-1 await and clamp the `done>total` overcount (`routes.py`).

**Tech Stack:** Python 3.10, asyncio, Playwright/Camoufox. Service `apps-microservices/api-detection-langue-fr`. Tests: `pytest`.

**Spec:** `docs/superpowers/specs/2026-07-22-detection-async-job-hang-hardening-design.md`

**Prereq for local tests:** `pip install -e libs/common-utils` (from repo root), then `cd apps-microservices/api-detection-langue-fr && pytest tests/`.

**Paths:** `SCRAPER` = `apps-microservices/api-detection-langue-fr/app/services/scraper.py` · `JOBS` = `apps-microservices/api-detection-langue-fr/app/core/async_jobs.py` · `ROUTES` = `apps-microservices/api-detection-langue-fr/app/api/routes.py` · `CONFIG` = `apps-microservices/api-detection-langue-fr/app/core/config.py`

---

### Task 1: L1 — self-aborting browser teardown + op/launch timeouts (scraper.py)

**Goal:** A dead-browser `browser.close()` (and the other teardown/launch/body awaits) can no longer hang the coroutine; the item self-aborts within seconds so the caller's `wait_for(300)` lands.

**Files:**
- Modify: `CONFIG` (add 3 env settings)
- Modify: `SCRAPER` (helper + teardown + launch + default op timeout, in both `scrape_html` and `scrape_html_with_redirects`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_close_or_abandon.py`

**Acceptance Criteria:**
- [ ] `_close_or_abandon(coro, timeout)` returns within `timeout` when the coro hangs, leaving it detached (no exception, no cancel-await); returns promptly when the coro completes.
- [ ] `scrape_html` + `scrape_html_with_redirects` teardown (`unroute_all`, `context.close`, `browser.close`) go through `_close_or_abandon(TEARDOWN_TIMEOUT_S)`.
- [ ] Playwright driver is started via explicit `start()` and stopped via `_close_or_abandon(p.stop(), TEARDOWN_TIMEOUT_S)` in a `finally` (replaces `async with async_playwright()`), in both functions.
- [ ] `context.set_default_timeout(BROWSER_OP_TIMEOUT_S*1000)` set right after context creation (bounds `new_page`/`content`/`add_cookies`/`route`).
- [ ] Chromium fallback `launch` wrapped in `asyncio.wait_for(BROWSER_LAUNCH_TIMEOUT_S)`; Camoufox launch uses `settings.BROWSER_LAUNCH_TIMEOUT_S` (was hardcoded 45).

**Verify:** `pytest tests/test_close_or_abandon.py -v` → PASS; `python -c "import ast; ast.parse(open('app/services/scraper.py').read())"` → no error.

**Steps:**

- [ ] **Step 1: Add config settings** — in `CONFIG`, inside `Settings` after the async-job block (after `SHUTDOWN_GRACE_S`):

```python
    # Browser-op hardening (scraper teardown/launch/op timeouts)
    TEARDOWN_TIMEOUT_S: int = 10       # bound + abandon on browser/context/page close & playwright.stop
    BROWSER_OP_TIMEOUT_S: int = 30     # context default timeout (new_page/content/route/add_cookies)
    BROWSER_LAUNCH_TIMEOUT_S: int = 45 # wrap Camoufox + Chromium launch
```

- [ ] **Step 2: Write the failing test** — create `tests/test_close_or_abandon.py`:

```python
import asyncio
import pytest
from app.services.scraper import _close_or_abandon


@pytest.mark.asyncio
async def test_abandons_hanging_coro_within_timeout():
    started = asyncio.Event()

    async def hangs():
        started.set()
        await asyncio.Event().wait()  # never resolves

    t0 = asyncio.get_event_loop().time()
    await _close_or_abandon(hangs(), timeout=0.2, what="test")
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 1.0                 # returned ~promptly, did not hang
    assert started.is_set()              # the coro did start (and is now detached)


@pytest.mark.asyncio
async def test_returns_when_coro_completes():
    ran = {"v": False}

    async def quick():
        ran["v"] = True

    await _close_or_abandon(quick(), timeout=5, what="test")
    assert ran["v"] is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_close_or_abandon.py -v`
Expected: FAIL — `ImportError: cannot import name '_close_or_abandon'`.

- [ ] **Step 4: Add the helper** — in `SCRAPER`, near the top-level helpers (before `scrape_html`), add:

```python
async def _close_or_abandon(coro, timeout: float, what: str = "") -> None:
    """Await a browser teardown coroutine, but ABANDON it if it exceeds `timeout`.

    A close() on a dead browser pipe ignores asyncio cancellation, so wait_for
    (cancel-then-await) would itself hang. asyncio.wait() returns on timeout
    WITHOUT cancelling; we simply stop waiting and leave the task detached
    (what that costs: see the 2026-08-17 correction below). This lets the
    caller escape `finally` and release its semaphore slot."""
    t = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({t}, timeout=timeout)
    if not done:
        logger.warning(f"scraper teardown abandoned after {timeout}s: {what}")
```

> **Correction 2026-08-17.** The docstring above shipped claiming the detached
> task's "OS process is already gone, so it leaks nothing meaningful". That was a
> belief, not a measurement, and it is false: this service contains no process
> management at all (no kill, no wait, no PID tracked), `p.stop()` only closes
> the driver pipe and waits for the driver to exit by itself, and the driver
> launches Firefox DETACHED. An abandoned `browser.close` therefore confirms
> neither the browser's death nor the removal of its profile directory. The
> abandon itself is still the right trade — raising `TEARDOWN_TIMEOUT_S` is not
> (FOUR sequential awaits on one scrape path — `unroute_all`, `context.close`,
> `browser.close`, `playwright.stop` — so 10s→30s turns a 40s worst case into
> 120s) — but its frequency was unknowable until `detect_teardown_abandoned_total`
> and `detect_browsers_unclosed` were added. Nobody has measured how many
> browsers survive an abandon; do not write a number here.

- [ ] **Step 5: Bound Camoufox + Chromium launch** — in `_launch_browser`, change the Camoufox `timeout=45` to `timeout=settings.BROWSER_LAUNCH_TIMEOUT_S`, and wrap the Chromium fallback launch (currently `browser = await playwright_instance.chromium.launch(...)`) in `asyncio.wait_for`:

```python
    # Fallback: Playwright Chromium
    t0 = time.monotonic()
    browser = await asyncio.wait_for(
        playwright_instance.chromium.launch(
            headless=True,
            proxy=playwright_proxy,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-blink-features=AutomationControlled',
            ],
        ),
        timeout=settings.BROWSER_LAUNCH_TIMEOUT_S,
    )
```

- [ ] **Step 6: `scrape_html` — explicit playwright start/stop + bounded teardown + default op timeout.** Replace the body from `async with _BROWSER_SEMAPHORE:` down through the `finally` block. Current outer structure is `async with _BROWSER_SEMAPHORE: / async with async_playwright() as p: / browser,is_camoufox = await _launch_browser(...) / try: ... finally: <3 closes>`. Change to:

```python
    async with _BROWSER_SEMAPHORE:
        p = await async_playwright().start()
        try:
            browser, is_camoufox = await _launch_browser(p, playwright_proxy)
            context = None
            page = None
            try:
                # ... UNCHANGED body: context_options, new_context, cookie inject,
                #     new_page, resource blocking, goto, networkidle, content loop,
                #     challenge poll, final_url, return ScrapeResult / None ...
                context = await browser.new_context(**context_options)
                context.set_default_timeout(settings.BROWSER_OP_TIMEOUT_S * 1000)
                # ... rest of the existing try body unchanged ...
            finally:
                if page is not None:
                    try:
                        await _close_or_abandon(
                            page.unroute_all(behavior='ignoreErrors'),
                            settings.TEARDOWN_TIMEOUT_S, f"unroute_all {url}")
                    except Exception as unroute_err:
                        logger.debug(f"unroute_all failed for {url}: {unroute_err}")
                if context is not None:
                    try:
                        await _close_or_abandon(
                            context.close(), settings.TEARDOWN_TIMEOUT_S, f"context.close {url}")
                    except Exception as ctx_err:
                        logger.debug(f"context.close failed for {url}: {ctx_err}")
                try:
                    await _close_or_abandon(
                        browser.close(), settings.TEARDOWN_TIMEOUT_S, f"browser.close {url}")
                except Exception as br_err:
                    logger.debug(f"browser.close failed for {url}: {br_err}")
        finally:
            await _close_or_abandon(p.stop(), settings.TEARDOWN_TIMEOUT_S, f"playwright.stop {url}")
```

Preserve the entire existing inner try-body (context_options through the `return`) verbatim — only (a) add the `context.set_default_timeout(...)` line right after `new_context`, (b) wrap the three closes in `_close_or_abandon`, (c) replace `async with async_playwright() as p:` with the explicit `start()`/`finally: stop()`.

- [ ] **Step 7: `scrape_html_with_redirects` — same three changes.** Apply the identical pattern (explicit `start()`/`finally _close_or_abandon(p.stop())`, `context.set_default_timeout` after its `new_context`, and `_close_or_abandon` on `unroute_all`/`context.close`/`browser.close`) to the twin teardown (`unroute_all` L602, `context.close` L607, `browser.close` L611) and its `async with async_playwright()` (L530).

- [ ] **Step 8: Run test + syntax check**

Run: `pytest tests/test_close_or_abandon.py -v` → PASS (2 tests).
Run: `python -c "import ast; ast.parse(open('app/services/scraper.py').read())"` → no output (valid).

- [ ] **Step 9: Commit**

```bash
git add app/core/config.py app/services/scraper.py tests/test_close_or_abandon.py
git commit -m "fix(detection): self-aborting browser teardown + op/launch timeouts (L1)"
```

---

### Task 2: L2 — worker watchdog abandons over-budget jobs (async_jobs.py)

**Goal:** The single FIFO worker can never be frozen by one job — an over-`JOB_MAX_S` job is marked `failed(job_timeout)`, abandoned, and the worker proceeds.

**Files:**
- Modify: `CONFIG` (add `JOB_MAX_S`)
- Modify: `JOBS` (`__init__` set, `_worker_loop` bounded wait, new `_abandon_job`, guard `_on_done`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_worker_watchdog.py`

**Acceptance Criteria:**
- [ ] `_worker_loop` waits on the job task with `timeout=JOB_MAX_S`; on breach it calls `_abandon_job` and continues to the next queued job.
- [ ] `_abandon_job` writes `status=failed, error='job_timeout'` (only if not already terminal), increments `ASYNC_JOBS_TERMINAL{status="failed"}`, best-effort `task.cancel()`, decrements `_inflight` exactly once, and records the id so a late zombie completion does NOT double-decrement.
- [ ] `_on_done` skips its decrement for an already-abandoned job.

**Verify:** `pytest tests/test_worker_watchdog.py -v` → PASS.

**Steps:**

- [ ] **Step 1: Add config** — in `CONFIG` after `BROWSER_LAUNCH_TIMEOUT_S` (Task 1) add:

```python
    JOB_MAX_S: int = 1500  # worker abandons a job exceeding this (< DETECTION_ASYNC_MAX_WAIT_S=1800 caller budget)
```

- [ ] **Step 2: Write the failing test** — create `tests/test_worker_watchdog.py`:

```python
import asyncio
import pytest
from types import SimpleNamespace
from app.core.async_jobs import JobManager, JobStore


class _FakeRedis:
    def __init__(self): self.kv = {}
    async def ping(self): return True
    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv: return False
        self.kv[k] = v; return True
    async def get(self, k): return self.kv.get(k)
    async def delete(self, k): self.kv.pop(k, None)
    async def expire(self, k, ttl): return True
    async def setex(self, k, ttl, v): self.kv[k] = v; return True


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=8, JOB_WORKER_CONCURRENCY=1,
                JOB_TTL_ACTIVE_S=7200, JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120,
                HEARTBEAT_INTERVAL_S=1, ASYNC_SUBMIT_RETRY_AFTER_S=15, ASYNC_POLL_HINT_MAX_S=30,
                SHUTDOWN_GRACE_S=5, JOB_MAX_S=0.3)
    base.update(over); return SimpleNamespace(**base)


def _req(items, cjid):
    return SimpleNamespace(client_job_id=cjid, items=items, proxy_url=None,
                           use_nlp_detection=True, force_refresh=False, max_concurrency=10,
                           homepage_fallback=True, validate_alternatives=True,
                           mode="complete")


@pytest.mark.asyncio
async def test_watchdog_abandons_wedged_job_and_frees_queue(monkeypatch):
    store = JobStore(client=_FakeRedis())
    hang = asyncio.Event()          # job 1's runner never returns
    ran2 = asyncio.Event()          # job 2's runner DID run

    async def batch_runner(items, mode, opts, progress_cb):
        # First call hangs forever; second completes.
        if not ran2_started["v"]:
            ran2_started["v"] = True
            await hang.wait()       # wedge
        ran2.set()
        return [], SimpleNamespace(success_count=0, failed_count=0, error_count=0)
    ran2_started = {"v": False}

    jm = JobManager(store, batch_runner, _settings())
    from app.models.schemas import BatchItem
    id1, _ = await jm.submit(_req([BatchItem(url="http://a.fr")], "c1"))
    id2, _ = await jm.submit(_req([BatchItem(url="http://b.fr")], "c2"))

    # Wait for the watchdog to fire on job1 and the worker to run job2.
    await asyncio.wait_for(ran2.wait(), timeout=5)

    rec1 = await store.get(id1)
    assert rec1["status"] == "failed" and rec1["error"] == "job_timeout"
    assert jm._inflight >= 0
    hang.set()                      # release the zombie; must not crash / double-decrement
    await asyncio.sleep(0.2)
    await jm.shutdown()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_worker_watchdog.py -v`
Expected: FAIL — job2 never runs (worker frozen on job1) → `asyncio.wait_for(ran2.wait())` times out.

- [ ] **Step 4: Implement.** In `JOBS` `__init__`, add after `self._keeper = None`:

```python
        self._abandoned_ids: set[str] = set()   # jobs decremented by the watchdog (guard _on_done)
```

Replace `_on_done`:

```python
    def _on_done(self, job_id: str) -> None:
        self._job_tasks.pop(job_id, None)
        if job_id in self._abandoned_ids:
            # already accounted for in _abandon_job — do NOT decrement twice
            self._abandoned_ids.discard(job_id)
            return
        self._inflight = max(0, self._inflight - 1)
        from app.core.metrics import ASYNC_JOBS_ACTIVE
        ASYNC_JOBS_ACTIVE.set(self._inflight)
```

In `_worker_loop`, replace the final `await asyncio.wait([task])` with:

```python
            done, _pending = await asyncio.wait({task}, timeout=self._s.JOB_MAX_S)
            if not done:
                await self._abandon_job(job_id, task)
```

Add the new method (next to `_on_done`):

```python
    async def _abandon_job(self, job_id: str, task: asyncio.Task) -> None:
        """Job exceeded JOB_MAX_S. Mark failed, abandon the (possibly uncancellable)
        task, free the slot, and let the worker proceed. A dead-pipe task may never
        finish cancelling — we do NOT await it."""
        from app.core.metrics import ASYNC_JOBS_TERMINAL, ASYNC_JOBS_ACTIVE
        logger.error(f"[async-jobs] job {job_id} exceeded JOB_MAX_S={self._s.JOB_MAX_S}s — failing + abandoning")
        rec = await self._store.get(job_id) or {"job_id": job_id}
        if rec.get("status") not in ("completed", "failed"):
            rec.update({"status": "failed", "error": "job_timeout",
                        "finished_at": time.time(), "last_activity": time.time()})
            try:
                await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
            except Exception:
                pass
            ASYNC_JOBS_TERMINAL.labels(status="failed").inc()
        task.cancel()                          # best-effort; may be ignored by a dead-pipe await
        self._job_tasks.pop(job_id, None)
        self._abandoned_ids.add(job_id)        # so a late _on_done won't double-decrement
        self._inflight = max(0, self._inflight - 1)
        ASYNC_JOBS_ACTIVE.set(self._inflight)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_worker_watchdog.py -v` → PASS.
Run the full async-job suite for no regression: `pytest tests/test_async_jobmanager.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py app/core/async_jobs.py tests/test_worker_watchdog.py
git commit -m "fix(detection): worker watchdog abandons over-budget jobs, queue never freezes (L2)"
```

---

### Task 3: sub-fixes — bound first_match Pass-1 + clamp done overcount (routes.py)

**Goal:** Close the last unwrapped await (`first_match` Pass-1) and stop `done` exceeding `total`.

**Files:**
- Modify: `ROUTES` (`process_group` loop ~L604-606; `_increment_count` ~L528 region)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_batch_progress_clamp.py`

**Acceptance Criteria:**
- [ ] `first_match` Pass-1 wraps `_process_item_core(item)` in `asyncio.wait_for(..., 300)` with a TimeoutError → `error` result (matching Pass-1 `process_single`).
- [ ] The progress callback never reports a value greater than `total_items` (Pass-2 retries no longer push `done` past `total`).

**Verify:** `pytest tests/test_batch_progress_clamp.py -v` → PASS; `python -c "import ast; ast.parse(open('app/api/routes.py').read())"` → no error.

**Steps:**

- [ ] **Step 1: Bound first_match Pass-1.** In `ROUTES` `process_group`, replace:

```python
            for item in group_items:
                async with semaphore:
                    result = await _process_item_core(item)
                last_result = result
```

with:

```python
            for item in group_items:
                try:
                    async with semaphore:
                        result = await asyncio.wait_for(_process_item_core(item), timeout=300)
                except asyncio.TimeoutError:
                    result = DetectionResponse(
                        ok=False, url=item.url, method='error',
                        error='Timeout global item (300s)')
                last_result = result
```

- [ ] **Step 2: Clamp the progress callback.** In `ROUTES` `_increment_count`, change the `progress_cb(processed_count)` call to clamp to `total_items`:

```python
    async def _increment_count() -> int:
        nonlocal processed_count
        async with count_lock:
            processed_count += 1
            if progress_cb is not None:
                progress_cb(min(processed_count, total_items))   # done must never exceed total
            return processed_count
```

(Leave the `[{count}/{total_items}]` log lines as-is — the raw count in logs is informative for retries; only the record's `done` must be clamped.)

- [ ] **Step 3: Write + run the test** — create `tests/test_batch_progress_clamp.py`:

```python
import asyncio
import pytest
from app.api import routes
from app.models.schemas import BatchItem, BatchOpts, DetectionMode, DetectionResponse


@pytest.mark.asyncio
async def test_progress_never_exceeds_total(monkeypatch):
    # Force every item to a Pass-2-retryable method so Pass-2 re-increments the counter.
    calls = {"n": 0}

    async def fake_core(item, force_refresh_override=None):
        calls["n"] += 1
        # first pass: transient (retryable); retry pass: still transient
        return DetectionResponse(ok=False, url=item.url, method='http_error_transient')

    monkeypatch.setattr(routes, "_detect_single_url",
                        lambda *a, **k: fake_core(BatchItem(url=k.get("url", "x")), None))
    progress = []
    items = [BatchItem(url=f"http://x{i}.fr") for i in range(3)]
    opts = BatchOpts(proxy_url=None, use_nlp_detection=True, force_refresh=False,
                     max_concurrency=10, homepage_fallback=True, validate_alternatives=True)
    await routes._run_batch_core(items, DetectionMode.COMPLETE, opts,
                                 progress_cb=lambda d: progress.append(d))
    assert progress, "progress_cb never called"
    assert max(progress) <= len(items)     # never exceeds total despite Pass-2 retries
```

Run: `pytest tests/test_batch_progress_clamp.py -v`.
Expected: FAIL before Step 2 (max(progress) > 3), PASS after.
(If the monkeypatch seam doesn't line up with `_process_item_core`'s call of `_detect_single_url`, adapt to patch `routes._detect_single_url` as the implementer sees it in the file — the assertion `max(progress) <= len(items)` is the contract.)

- [ ] **Step 4: Commit**

```bash
git add app/api/routes.py tests/test_batch_progress_clamp.py
git commit -m "fix(detection): bound first_match Pass-1 + clamp done<=total (sub-fixes)"
```

---

## Deploy (after tasks, user-controlled)

- **RAG-HP-PUB** `features/poc`: `git push origin features/poc` + **rebuild the `api-detection-langue-fr` Docker image on the VM**. No BO, no migration.
- New env vars default in `config.py`; no `.env` edit needed. Tune `JOB_MAX_S`/`TEARDOWN_TIMEOUT_S` later if wanted.
- **Immediate recovery (now, independent):** restart the container to clear the current 5 stuck jobs.

## Post-deploy smoke

- Submit a batch with a known-hostile/challenge URL; confirm: no job exceeds `JOB_MAX_S`, the FIFO keeps draining (subsequent jobs run), and a wedged item surfaces as an item `error`/job `failed` rather than freezing the worker. `docker exec … ps` shows no accumulating browser processes.
