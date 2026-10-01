# Design — api-detection-langue-fr async-job hang hardening

**Date:** 2026-07-22
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10, FastAPI). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO change, no migration.

## Problem

An async detection job (`e5be122…`) sat `running` for **27 hours**; four more jobs sat `pending` behind it; the BO retry launcher polled each for its full 30-min budget making zero progress. Metrics: `detect_async_jobs_active=5` (1 running + 4 queued), `queued=4`, `submitted=17`, `completed=12`, `failed=0`.

## Evidence

- Record `e5be122`: `status=running`, `done=18` (frozen; `total=10` — see sub-fix), `last_activity` advancing (heartbeat alive), `started_at→last_activity ≈ 27.2h`.
- `docker exec … ps`: **only `docker-init` + `uvicorn`** — no browser subprocess. The Camoufox/Chromium process died long ago; a coroutine awaits a driver reply that never arrives.
- CPU ~8%, not spinning → a **suspended await**, not a compute loop. Event loop healthy (heartbeat + queued-keeper still writing every 5s).
- Code audit (4 files) pinpointed the wedge (below).

## Root cause

1. **The wedge (source), `app/services/scraper.py`:** `scrape_html`'s `finally` runs `await context.close()` (L482) and `await browser.close()` (L486) with **no timeout**, and `scrape_html_with_redirects` mirrors it (L607/L611). On a dead browser these await a driver reply that never comes. They run **inside `finally` while the caller's `asyncio.wait_for(300)` CancelledError is already unwinding** — a coroutine already handling cancellation cannot be re-cancelled, so `wait_for` is left awaiting a task that never finishes → **hangs indefinitely**. This is precisely why "the 300s could not bound it." The `async with async_playwright()` `__aexit__` (`p.stop()`) is a second such teardown await. Additional unbounded browser awaits: `new_context`/`new_page`/`content()`/`add_cookies`/`route` (no `timeout=`), and the Chromium-fallback `launch` (L213) relies only on Playwright's internal 30s timer (Camoufox launch is already wrapped in `wait_for(45)`).
2. **The amplifier (queue liveness), `app/core/async_jobs.py`:** `JOB_WORKER_CONCURRENCY=1`; `_worker_loop` blocks on `await asyncio.wait([task])` until the current job finishes. A wedged job → the worker never calls `queue.get()` again → every queued job stays `pending`.
3. **The mask, `_queued_keeper_loop` + `_heartbeat`:** both refresh `last_activity` every 5s while the process lives, so `poll_status` never returns `stale` → the BO polls each stuck job for the full `DETECTION_ASYNC_MAX_WAIT_S=1800s` blind, and the idempotency index (2h TTL) re-binds re-submits to the same wedged jobs.

Secondary unbounded awaits (same dead-pipe class): `domain_fr.py:420` alt-validation `scrape_html` (no `wait_for` on the main path), the inflight-dedup follower `await fut` (`inflight_dedup.py:78`), and `first_match` Pass-1 `process_group` (`routes.py:606`, no `wait_for`).

## Design

### L1 — Source: self-aborting browser teardown + per-op timeouts (`scraper.py`) — the real cure

A `wait_for` around `browser.close()` does NOT help (the close ignores cancellation too, so `wait_for` re-hangs). The teardown must **abandon, not cancel-and-await**:

- New helper `_close_or_abandon(coro, timeout)`: `t = asyncio.ensure_future(coro); await asyncio.wait({t}, timeout=timeout)` — if `t` is still pending after `timeout`, **leave it detached** (do NOT `cancel()`+`await` it: a dead-pipe close ignores cancellation; `asyncio.wait` — unlike `wait_for` — does not cancel on timeout, so we simply stop waiting). **Correction 2026-08-17:** this line originally read "the detached task harms nothing (its OS process is already gone)" — that was a belief, never verified, and it is false. The service tracks no PID and kills nothing; `p.stop()` merely closes the driver pipe and waits for the driver to exit on its own, and the driver launches Firefox DETACHED, so an abandoned `browser.close` can leave a live browser and an undeleted profile directory behind. How many, and how often, has never been measured — the `detect_teardown_abandoned_total` counter and `detect_browsers_unclosed` gauge exist to answer that. Abandoning is still the right trade against the stall it prevents; raising `TEARDOWN_TIMEOUT_S` is not — FOUR sequential awaits on one scrape path (`unroute_all`, `context.close`, `browser.close`, `playwright.stop`) mean 10s→30s turns a 40s worst case into 120s. Neither the number of call sites nor the pool size enters that multiplication. This lets the coroutine escape `finally` → `async with semaphore` `__aexit__` runs → the browser slot is released → the caller's `wait_for(300)` finally lands → the item fails cleanly and the batch proceeds.
- Apply to every teardown await in both `scrape_html` and `scrape_html_with_redirects`: `page.unroute_all` (L477/L602), `context.close` (L482/L607), `browser.close` (L486/L611), and the `async_playwright().__aexit__`/`p.stop()`.
- Add explicit timeouts to the body browser ops that take none: `browser.new_context`, `context.new_page`, `context.add_cookies`, `page.route`, and `page.content()` — via `context.set_default_timeout(BROWSER_OP_TIMEOUT_S*1000)` where applicable plus explicit `timeout=` on `content()` calls (L377/L409/L415/L433).
- Wrap the Chromium-fallback `launch` (L213) in `asyncio.wait_for(BROWSER_LAUNCH_TIMEOUT_S)` mirroring the Camoufox path.

New env (config.py, with defaults): `TEARDOWN_TIMEOUT_S=10`, `BROWSER_OP_TIMEOUT_S=30`, `BROWSER_LAUNCH_TIMEOUT_S=45`.

### L2 — Safety net: worker watchdog that abandons an over-budget job (`async_jobs.py`)

`_worker_loop`: replace `await asyncio.wait([task])` with a bounded wait:
```
done, _ = await asyncio.wait({task}, timeout=self._s.JOB_MAX_S)
if task not in done:
    # over budget → mark failed, abandon (best-effort cancel, do NOT await), proceed
    write record status='failed', error='job_timeout', finished_at=now  (JOB_RESULT_TTL_S)
    ASYNC_JOBS_TERMINAL.labels(status='failed').inc()
    task.cancel()                      # best-effort; zombie may linger harmlessly
    self._job_tasks.pop(job_id, None)
    self._inflight = max(0, self._inflight - 1)   # manual decrement — the done-callback
                                                  # never fires for an abandoned zombie
    ASYNC_JOBS_ACTIVE.set(self._inflight)
    continue                            # pick the next queued job
```
- **`_inflight` accounting:** the abandoned task's `add_done_callback(_on_done)` won't fire (zombie never completes) → decrement `_inflight` manually here, and **remove the `_on_done` callback** (or guard it) so a late zombie completion can't double-decrement. Disjoint-path handling like `shutdown()`.
- Guarantees the queue can never be frozen by one job — for the known wedge **and** any future uncancellable await L1 didn't foresee.
- New env: `JOB_MAX_S=1500` (< the BO's `DETECTION_ASYNC_MAX_WAIT_S=1800` so the BO gets a terminal `failed` before its poll budget and re-submits cleanly — this is also what un-masks the stall, making L3 unnecessary).

### Sub-fixes (fold in)

- **`first_match` Pass-1** (`routes.py:606`): wrap `_process_item_core(item)` in `asyncio.wait_for(…, 300)` like the other loops (only unwrapped path remaining).
- **`done > total` overcount** (`routes.py`): Pass-2 retries re-call `_increment_count`, pushing `processed_count` past `total` (hence `done=18` for `total=10`). Report progress as distinct-items-done (clamp to `total`, or count first-pass completions only). Cosmetic but confusing.
- **Optional:** short `wait_for` on the dedup-follower `await fut` (`inflight_dedup.py:78`) so a follower can't outlive a dead leader.

## Out of scope

- **L3 progress-based stale** — dropped: L2 marks a wedged job `failed` within `JOB_MAX_S` (≤25 min, under the BO's 30-min budget), so the BO already gets a terminal status and re-submits. A separate `last_progress_at` field + `poll_status` change buys only marginally-faster detection. Revisit only if sub-1500s wedge detection is later required.
- **Pass-2 sequential-retry latency** — a large all-failing batch is inherently slow (sequential × up to 300s/item) and can legitimately exceed the BO budget. Parallelizing/capping Pass-2 is a separate perf chantier; `JOB_MAX_S` bounds it for now (fails → re-submit).
- **Semaphore-acquired-outside-`wait_for`** — not fixed structurally; L1 makes the wedged holder escape and release its slot, which removes the observed leak. Restructuring the acquire is unnecessary once L1 lands.

## Deploy

- **RAG-HP-PUB** `features/poc`: `git push origin features/poc` + **rebuild `api-detection-langue-fr` Docker image on the VM**. No BO, no migration.
- New env vars have safe defaults in `config.py`; no `.env` change required to deploy.
- **Immediate recovery (now, separate from this fix):** restart the container — fail-fast clears the 5 stuck jobs (→ stale → BO re-submits).

## Verification

- `pip install -e libs/common-utils` then `pytest tests/`.
- **L2 unit test:** inject a `batch_runner` that never returns; assert the worker marks the job `failed(job_timeout)` after `JOB_MAX_S` (patched small), decrements `_inflight`, and **picks the next queued job** (queue not frozen). No double-decrement if the zombie later resolves.
- **L1 unit test:** `_close_or_abandon` returns within `timeout` when the wrapped coro hangs, leaving it detached (no exception, no re-await). Scraper teardown path: a hanging `browser.close()` does not prevent `scrape_html` from returning/raising within `timeout`.
- **Sub-fix test:** progress `done` never exceeds `total`.
- **Post-deploy smoke:** submit a batch containing a known-hostile URL; confirm no job exceeds `JOB_MAX_S`, the queue keeps draining, and a wedged item surfaces as `failed`/item-error rather than freezing the worker.
