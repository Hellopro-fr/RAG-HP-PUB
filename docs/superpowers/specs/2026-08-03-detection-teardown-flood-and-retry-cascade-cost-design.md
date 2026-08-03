# Design — teardown exception flood + retry-cascade cost

**Date:** 2026-08-03
**Status:** Approved (design), pending implementation plan
**Service:** `apps-microservices/api-detection-langue-fr` (Python 3.10). RAG-HP-PUB `features/poc`.
**Deploy:** `git push` + **Docker rebuild on VM**. No BO, no migration, no new env var, no compose change.

## Problem

Two symptoms, one causal chain.

**Reported symptom.** The container floods its log with asyncio errors, hundreds of lines per event:

```
asyncio - ERROR - Future exception was never retrieved
future: <Future finished exception=TargetClosedError('Target page, context or browser has been closed')>
  ... _update_interceptor_patterns_ignore_exceptions ... (same 4 frames repeated ~20×)
asyncio - ERROR - Task exception was never retrieved
future: <Task ... coro=<Page.unroute_all() ...> exception=TargetClosedError(...)>
asyncio - ERROR - Task exception was never retrieved
future: <Task ... coro=<BrowserContext.close() ...> exception=TargetClosedError(...)>
```

**Operational symptom, same log.** A batch of 10 produced nothing in 11 minutes:

```
[BATCH] [10/10] TIMEOUT https://www.forgesclerencoise.fr après 300s
[BATCH] Pass 1 termine: 0 OK, 0 fetch_failed, 0 challenge_page, 10 autres (659325ms)
```

### Hypotheses tested and FALSIFIED — recorded so nobody re-runs this

| Hypothesis | Evidence against it |
|---|---|
| The browser is OOM-killed | `docker inspect`: `OOMKilled=false`, `RestartCount=1`, limit 4718592000. `docker stats`: **2.879 GiB / 4.395 GiB (65%)**. Every `dmesg` OOM victim is `cadvisor` or `mysqld` — different cgroups, never this service, never a browser. |
| Playwright drivers / browsers leak (876 PIDs) | `ps -eo etimes,comm` filtered to `>600s` inside the container returns **only** `3 MainThread`, `1 uvicorn`, `1 docker-init`. No stranded `node`, no stranded Firefox. `p.stop()` reaps correctly; 876 PIDs is legitimate thread count for 6 concurrent Camoufox instances. |
| CPU saturation | compose grants **`cpus: 4`**; observed **119.51%** of 400% available. ~30% utilisation. |

**Consequences of those three falsifications, which shaped this design:** no structural Playwright refactor (a long-lived instance, or killing the driver through `p._connection._transport`) is warranted — there is nothing leaking to fix. And a `pids_limit` backstop in compose is **actively withdrawn as a recommendation**: 876 PIDs is normal load here, so a cap would cause an outage rather than prevent one.

### Actual root cause — arithmetic, not resource exhaustion

**1. Phase 2 (URL variants) runs unconditionally, whatever the failure was.**

`redirect_tracker.py` uses `_VARIANT_ELIGIBLE_ERRORS` (`:245-247`) only to `break` out of the retry loop early. After the loop, `:262` calls `_generate_url_variants(url)` with no reference to *why* Phase 1 failed. So a plain navigation timeout — which http/https and www toggling cannot possibly fix — still triggers up to 4 more full browser launches.

Cost of one hopeless domain:

| phase | launches | cost each | subtotal |
|---|---|---|---|
| Phase 1 retries (`:218`) | 3 | launch + 30 s nav timeout + teardown, + 2 s/4 s sleeps | ~140 s |
| Phase 2 variants (`:268`) | up to 4 | launch + 30 s nav timeout + teardown | ~180 s |
| **total** | **up to 7** | | **~320 s** |

Against the 300 s per-item ceiling in `_run_batch_core`, that **deterministically overruns**. The item is cancelled mid-flight — and the cancellation is what orphans the in-flight futures that produce the flood. The reported log symptom is therefore *downstream* of this cost defect.

The batch in the log is a **retry batch of already-failing domains** (it ends in `Pass 2: retry sequentiel` on `cantirac.fr`, and the caller is the `domaine_fr_retry` path), so `0 OK / 10 autres` is the expected input population — not a service defect. The defect is spending 320 s per domain to learn what was already known at 140 s.

**2. Teardown runs against targets that are already dead.**

`scraper.py:498-513` and `:627-642` call `unroute_all` → `context.close` → `browser.close` unconditionally in `finally`. When the target is already gone — the common case on a failed scrape — each raises `TargetClosedError`. Two costs: up to `TEARDOWN_TIMEOUT_S` (10 s, `config.py:89`) burned per op inside the item's budget, and `unroute_all` on a dead page is what makes Playwright schedule its internal `_update_interceptor_patterns_ignore_exceptions` task — the giant repeated traceback. (Note the irony: that `unroute_all` was itself added to suppress a *different* `TargetClosedError` flood, per the comment at `:498-499`.)

**3. `_close_or_abandon` never retrieves the task's exception.**

```python
t = asyncio.ensure_future(coro)
done, _pending = await asyncio.wait({t}, timeout=timeout)
if not done:
    logger.warning(f"scraper teardown abandoned after {timeout}s: {what}")
```

`asyncio.wait()` does not retrieve results. Two paths, **both present in the log**:

- **Completed with an exception** (browser already dead → raises immediately): lands in `done`, we skip the warning, nobody reads the exception → `Task exception was never retrieved`. These are the entries at `09:58:48,729` that arrive with *no* accompanying "abandoned" warning.
- **Exceeded the timeout**: left pending, completes later unread → same error. These pair with the `09:59:09` / `09:59:39` warnings.

Same defect class as the one fixed in `inflight_dedup.py` this session (`b4917662`, adding `fut.exception()`); it was written into `_close_or_abandon` two commits earlier and the connection was missed.

**Side effect:** because `_close_or_abandon` swallows and never re-raises, the six `except Exception as …: logger.debug(...)` handlers wrapping its call sites (`:503`, `:508`, `:512`, `:632`, `:637`, `:641`) are **provably dead** — they have never fired.

## Design

Three changes, all in `app/services/`. Ordered by value: the first removes the flood's *trigger*, the third removes the flood's *logging*.

### 1. Gate Phase 2 on the failure class — `redirect_tracker.py`

Before `variants = _generate_url_variants(url)` (`:262`):

```python
    # Les variantes n'existent que pour les mauvaises configurations DNS/SSL
    # (ERR_NAME_NOT_RESOLVED sur www, certificat invalide sur https…). Sur un
    # timeout de navigation ou un contenu vide, basculer http/https et www ne
    # change rien : c'était jusqu'ici 4 lancements de navigateur pour rien, ce
    # qui poussait le coût d'un domaine injoignable à ~320s, au-delà du
    # plafond de 300s par item — l'item était alors annulé en vol, ce qui
    # orphelinait les futures et produisait le flood asyncio.
    variant_eligible = last_error and any(
        err in last_error for err in _VARIANT_ELIGIBLE_ERRORS
    )
    if not variant_eligible:
        logger.warning(
            f"[VARIANTES] ignorées pour {url} — "
            f"échec non éligible aux variantes: {last_error}"
        )
        return None
```

The strictest of the three gates considered, chosen deliberately. The `break` path at `:245-247` is unaffected: it breaks *because* `last_error` is variant-eligible, so the new gate passes for exactly those cases.

**Accepted loss:** a site reachable only on the www-toggled host that *times out* rather than failing DNS resolution is no longer rescued. Judged acceptable — a timeout on the apex is far more often a slow or dead site than a www misconfiguration, and the 4 wasted launches are paid on every hopeless domain to buy that rare rescue.

### 2. Liveness-guard the teardown — `scraper.py` (both scrape functions)

```python
                if page is not None and not page.is_closed():
                    await _close_or_abandon(page.unroute_all(behavior='ignoreErrors'), ...)
                if context is not None and browser.is_connected():
                    await _close_or_abandon(context.close(), ...)
                if browser.is_connected():
                    await _close_or_abandon(browser.close(), ...)
```

`page.is_closed()` and `browser.is_connected()` are synchronous in the Python API — no await, no network round-trip, so the guard cannot itself hang. `BrowserContext` exposes no `is_closed()`, so its close is gated on the browser instead: if the browser is gone, the context is gone with it.

`p.stop()` stays unconditional — it reaps the driver process, and the falsified leak hypothesis confirms it is doing so correctly.

Effect: on a failed scrape, up to 30 s of pointless waiting disappears from the item budget, and Playwright's internal interceptor-pattern task is never scheduled, so the largest traceback in the log stops being produced at all.

### 3. Retrieve the exception — `scraper.py:286-297`

```python
def _drain_orphan_exception(fut: asyncio.Future) -> None:
    """Read an abandoned teardown's exception so asyncio doesn't log
    'Task exception was never retrieved' when it is garbage-collected."""
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        logger.debug(f"abandoned teardown finished with: {exc!r}")


async def _close_or_abandon(coro, timeout: float, what: str = "") -> None:
    t = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({t}, timeout=timeout)
    if done:
        # asyncio.wait() ne consomme PAS le résultat : sans ceci, une fermeture
        # qui échoue vite (TargetClosedError sur un navigateur déjà mort) fait
        # journaliser "Task exception was never retrieved" par asyncio.
        if not t.cancelled() and t.exception() is not None:
            logger.debug(f"teardown failed ({what}): {t.exception()!r}")
        return
    logger.warning(f"scraper teardown abandoned after {timeout}s: {what}")
    t.add_done_callback(_drain_orphan_exception)
```

`t.cancelled()` is checked because `t.exception()` raises `CancelledError` on a cancelled task.

The six dead `except Exception` handlers around the call sites become redundant as well as dead — `_close_or_abandon` now logs the failure itself. Removing them is recommended in the same edit (low risk, shrinks the code, and a reviewer would flag them regardless), but it is not load-bearing for the fix.

## Behaviour change

| Situation | Before | After |
|---|---|---|
| Domain fails Phase 1 with a nav timeout | 4 extra browser launches, ~320 s total, item cancelled at 300 s, flood | Phase 2 skipped, ~140 s, item returns a real verdict |
| Domain fails Phase 1 with DNS/SSL error | variants tried | unchanged — variants tried |
| Phase 1 returns empty/short content | variants tried | Phase 2 skipped (`last_error` not eligible) |
| Teardown on an already-dead target | 3 ops attempted, up to 30 s burned, `TargetClosedError` unretrieved ×3 + Playwright internal future | ops skipped, no wait, no flood |
| Teardown on a live target | unchanged | unchanged |
| Teardown genuinely hangs | abandoned after 10 s, exception later unretrieved | abandoned after 10 s, exception drained by callback |
| `p.stop()` | unconditional, abandoned after 10 s if wedged | unchanged |

Expected on the same retry batch: items fail with a verdict (`fetch_failed`) inside the ceiling instead of being cancelled as `error / Timeout global item (300s)`, pass-1 wall clock roughly halved, and the asyncio flood gone.

## Out of scope

- **A wall-clock deadline inside `fetch_html`.** It would make the 300 s ceiling unreachable by construction, but change 1 already brings the worst case to ~140 s against a 300 s budget. Insurance against a future cascade addition, not a fix for anything observed. Parked deliberately.
- **Any structural Playwright change** (long-lived instance, private-API driver kill) — the leak hypothesis is falsified; there is nothing to fix.
- **`pids_limit` in compose** — withdrawn, see the falsification table.
- **`BROWSER_SEMAPHORE_SIZE` / `ADMISSION_MAX_SLOTS` tuning** — 6 browsers on 4 CPUs at 30% utilisation is not the constraint. Note in passing that `ADMISSION_MAX_SLOTS=8` exceeds `BROWSER_SEMAPHORE_SIZE=6`, so two admitted requests always queue on the browser semaphore; harmless, not touched here.
- **The duplicated `WARNING`/`ERROR` log lines** (`INFO` lines are not duplicated, so a second handler at WARNING+ level is likely alongside `main.py:22`'s `basicConfig`). `[UNCLEAR]`, cosmetic, doubles flood volume; separate investigation.
- **The `404` on `GET /detect-batch-async/01e5…`** — explained by `RestartCount=1`: the restart wiped in-flight jobs, which is the documented fail-fast contract, not a bug.

## Verification

Unit tests (`tests/test_teardown_and_variants.py`), no network:

1. `_close_or_abandon` with a coroutine that raises immediately → returns normally, and a custom `loop.set_exception_handler` records **no** call after a GC cycle (this is the actual regression guard for the reported symptom).
2. `_close_or_abandon` with a coroutine that hangs past the timeout, then fails → the warning is logged, and the loop exception handler is still never called once the orphan completes.
3. `_close_or_abandon` with a coroutine that succeeds → no warning, no debug.
4. Phase-2 gate: `scrape_html` monkeypatched to raise a navigation timeout → asserted called exactly **3** times (not 7), and the `[VARIANTES] ignorées` warning emitted.
5. Phase-2 gate: `scrape_html` monkeypatched to raise `ERR_NAME_NOT_RESOLVED` → variants still attempted (guard against over-gating).
6. Liveness guard: a page stub whose `is_closed()` returns `True` → `unroute_all` never awaited; a browser stub whose `is_connected()` returns `False` → neither close awaited.

Baseline on this machine is `287 passed, 7 failed` (the 7 pre-existing `tests/test_domain_fr.py` failures — no local fastText model, a `ScrapeResult` tuple-unpack drift, a missing `await` in two alternative-language tests) plus a pre-existing `tests/test_api.py` collection error.

**Post-deploy**, on the same `domaine_fr_retry` batch: expect `Pass 1 termine` wall clock roughly halved, `0 OK` items reported as `fetch_failed` rather than `error`/timeout, `[VARIANTES] ignorées` lines appearing, and no `Task exception was never retrieved` in the log. `docker stats` PIDs should also fall, since fewer launches are in flight — a secondary confirmation that the count tracks load rather than leakage.
