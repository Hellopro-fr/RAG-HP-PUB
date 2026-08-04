# Teardown flood + retry-cascade cost — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the asyncio "exception was never retrieved" flood, and stop a hopeless domain costing up to ~275 s (close to the 300 s per-item ceiling — the observed cancellation implies the real per-launch cost runs above the ~45 s estimate behind that figure — and the cancellation is what causes the flood).

**Architecture:** Three independent changes in `app/services/`. `_close_or_abandon` gains exception draining. The duplicated teardown block in both scrape functions is extracted into one liveness-aware helper. `redirect_tracker.fetch_html` gains a denylist gate so URL variants are skipped for failure classes they cannot fix.

**Tech Stack:** Python 3.10, asyncio, Playwright (Camoufox/Firefox in prod), pytest + pytest-asyncio.

**User decisions (already made):**
- Do the three cheap changes; the structural Playwright refactor is **off the table** (the process-leak hypothesis was falsified: only 5 processes older than 10 min inside the container, none a browser or driver).
- `pids_limit` in compose is **withdrawn** — 876 PIDs is legitimate load, so a cap would cause an outage rather than prevent one.
- The variant gate is a **denylist** (`Timeout`, `Contenu vide ou trop court`), chosen after we proved an allowlist keyed on `_VARIANT_ELIGIBLE_ERRORS` cannot match on Camoufox and would have deleted variant rescue entirely.

**Spec:** `docs/superpowers/specs/2026-08-03-detection-teardown-flood-and-retry-cascade-cost-design.md` (`a0d2f03`, amended `3131cd3`)

---

## Environment notes (read before running anything)

- Run pytest from `apps-microservices/api-detection-langue-fr` with `$env:PYTHONIOENCODING="utf-8"` set first — French log output crashes this machine's cp1252 stdout with `UnicodeEncodeError` / `OSError: [Errno 22]`. If output is unreadable, redirect to a file and read the file.
- `common_utils` is **already** installed editable from the MAIN checkout (`D:\DevHellopro\Workspaces\RAG-HP-PUB\libs\common-utils`). Do **not** reinstall, and never `pip install -e` from inside a worktree — that breaks every future session once the worktree is removed. On `ModuleNotFoundError: No module named 'common_utils'`, stop and report NEEDS_CONTEXT.
- Baseline suite: `python -m pytest tests/ --ignore=tests/test_api.py -q` → **`287 passed, 7 failed`**. The 7 failures are all in `tests/test_domain_fr.py`, are **pre-existing** (no local fastText `.bin`, a `ScrapeResult` tuple-unpack drift, a genuine missing `await` in `test_detect_hreflang`/`test_detect_data_lang`) and are **not yours**. Do not edit that file. The full run takes ~5 minutes because of real Playwright timeout tests — run it in the FOREGROUND and wait.
- Playwright **is** importable locally (the existing `tests/test_close_or_abandon.py` imports `app.services.scraper` and passes), so these tests run without Docker.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `app/services/scraper.py` | `_close_or_abandon` drains exceptions; new `_teardown_targets` helper owns liveness-aware teardown for both scrape functions | 1, 2 |
| `app/services/redirect_tracker.py` | `_VARIANT_POINTLESS_ERRORS` + the Phase-2 gate | 3 |
| `tests/test_close_or_abandon.py` | **exists** (2 tests) — extended, not replaced | 1 |
| `tests/test_teardown_targets.py` | create — liveness-guard behaviour | 2 |
| `tests/test_variant_gate.py` | create — Phase-2 gate behaviour | 3 |

Tasks 1 → 2 are sequential (same file, and 2 relies on 1's helper). Task 3 touches a disjoint file pair and may run in parallel with either.

---

### Task 1: `_close_or_abandon` drains the task's exception

**Goal:** No asyncio "Task exception was never retrieved" is emitted for a teardown coroutine, whether it fails fast or is abandoned.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py:286-297`
- Test: `apps-microservices/api-detection-langue-fr/tests/test_close_or_abandon.py` (exists — append)

**Acceptance Criteria:**
- [ ] A teardown coroutine that raises **immediately** produces no unretrieved-exception report from the loop's exception handler
- [ ] A teardown coroutine that exceeds the timeout and raises **later** also produces none (drained by a done-callback)
- [ ] The abandoned case still logs `scraper teardown abandoned after {timeout}s: {what}` at WARNING
- [ ] A coroutine that succeeds logs no warning
- [ ] A **cancelled** task does not cause `_close_or_abandon` (or the callback) to raise `CancelledError`
- [ ] The two pre-existing tests in the file still pass unchanged

**Verify:** `python -m pytest tests/test_close_or_abandon.py -v` → 6 passed

**Steps:**

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_close_or_abandon.py`:

```python


# --- Exception draining (2026-08-03) -----------------------------------------
# asyncio.wait() does NOT retrieve results. Without draining, a teardown that
# fails (TargetClosedError on an already-dead browser) makes asyncio log
# "Task exception was never retrieved" — the flood reported in prod.

import gc


class _HandlerSpy:
    """Captures anything asyncio reports to the loop exception handler."""

    def __init__(self):
        self.contexts = []

    def __call__(self, loop, context):
        self.contexts.append(context)


async def _settle():
    """Give asyncio a chance to GC finished tasks and report unretrieved ones."""
    for _ in range(3):
        gc.collect()
        await asyncio.sleep(0)
    gc.collect()


@pytest.mark.asyncio
async def test_fast_failure_exception_is_drained():
    spy = _HandlerSpy()
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    loop.set_exception_handler(spy)
    try:
        async def boom():
            raise RuntimeError("Target page, context or browser has been closed")

        await _close_or_abandon(boom(), timeout=5, what="fast-failure")
        await _settle()
    finally:
        loop.set_exception_handler(previous)

    assert spy.contexts == [], (
        f"asyncio reported an unretrieved exception: {spy.contexts}"
    )


@pytest.mark.asyncio
async def test_abandoned_task_exception_is_drained():
    spy = _HandlerSpy()
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    loop.set_exception_handler(spy)
    try:
        async def slow_boom():
            await asyncio.sleep(0.05)
            raise RuntimeError("late TargetClosedError")

        await _close_or_abandon(slow_boom(), timeout=0.01, what="abandoned")
        # Let the orphan finish AFTER we stopped waiting for it.
        await asyncio.sleep(0.2)
        await _settle()
    finally:
        loop.set_exception_handler(previous)

    assert spy.contexts == [], (
        f"abandoned teardown leaked an unretrieved exception: {spy.contexts}"
    )


@pytest.mark.asyncio
async def test_abandoned_task_still_warns(caplog):
    async def hangs():
        await asyncio.Event().wait()

    with caplog.at_level("WARNING", logger="app.services.scraper"):
        await _close_or_abandon(hangs(), timeout=0.01, what="warn-me")

    assert any("teardown abandoned" in r.message and "warn-me" in r.message
               for r in caplog.records)


@pytest.mark.asyncio
async def test_cancelled_task_does_not_raise(caplog):
    """A cancelled teardown must not turn into a CancelledError from the
    drain path — t.exception() raises on a cancelled task."""
    async def slow():
        await asyncio.sleep(10)

    t = asyncio.ensure_future(slow())
    t.cancel()
    # Feed the already-cancelled task through the same drain callback the
    # abandoned path installs.
    from app.services.scraper import _drain_orphan_exception
    _drain_orphan_exception(t)  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_close_or_abandon.py -v`
Expected RED: `test_fast_failure_exception_is_drained` and `test_abandoned_task_exception_is_drained` fail on their assertion (the spy captured a context whose message mentions "never retrieved"), and `test_cancelled_task_does_not_raise` fails with `ImportError` / `cannot import name '_drain_orphan_exception'`. `test_abandoned_task_still_warns` should already pass. Report exactly which failed and how.

- [ ] **Step 3: Implement the drain**

In `app/services/scraper.py`, replace the whole `_close_or_abandon` function (currently `:286-297`) with:

```python
def _drain_orphan_exception(fut: "asyncio.Future") -> None:
    """Read an abandoned teardown's exception once it finally completes.

    Without this, asyncio logs "Task exception was never retrieved" when the
    orphan is garbage-collected — the log flood observed in prod on 2026-08-03.
    A cancelled task must be skipped: `.exception()` re-raises CancelledError.
    """
    if fut.cancelled():
        return
    exc = fut.exception()
    if exc is not None:
        logger.debug(f"abandoned teardown finished with: {exc!r}")


async def _close_or_abandon(coro, timeout: float, what: str = "") -> None:
    """Await a browser teardown coroutine, but ABANDON it if it exceeds `timeout`.

    A close() on a dead browser pipe ignores asyncio cancellation, so wait_for
    (cancel-then-await) would itself hang. asyncio.wait() returns on timeout
    WITHOUT cancelling; we simply stop waiting and leave the task detached (its
    OS process is already gone, so it leaks nothing meaningful). This lets the
    caller escape `finally` and release its semaphore slot.

    Either way the exception is DRAINED — asyncio.wait() does not retrieve
    results, so a teardown that fails fast (TargetClosedError on an already
    dead browser) would otherwise be reported as never retrieved."""
    t = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({t}, timeout=timeout)
    if done:
        if not t.cancelled():
            exc = t.exception()
            if exc is not None:
                logger.debug(f"teardown failed ({what}): {exc!r}")
        return
    logger.warning(f"scraper teardown abandoned after {timeout}s: {what}")
    t.add_done_callback(_drain_orphan_exception)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_close_or_abandon.py -v`
Expected: 6 passed.

- [ ] **Step 5: Prove the drain is what fixes it**

Temporarily delete the `if not t.cancelled(): …` block from the `if done:` branch (leaving a bare `return`) and re-run `test_fast_failure_exception_is_drained` → it MUST fail. Restore the block exactly and re-run → 6 passed. Then do the same for the `t.add_done_callback(_drain_orphan_exception)` line against `test_abandoned_task_exception_is_drained`. Report both outcomes and confirm both restorations are byte-identical to the code above.

- [ ] **Step 6: Syntax check + commit**

Run: `python -c "import ast; ast.parse(open('app/services/scraper.py',encoding='utf-8').read()); print('AST OK')"`

Stage exactly these two paths (explicit paths only — **never** `git add -A`):
```
apps-microservices/api-detection-langue-fr/app/services/scraper.py
apps-microservices/api-detection-langue-fr/tests/test_close_or_abandon.py
```
Bilingual EN-then-FR Conventional Commit, message written to a temp file with the Write tool and passed via `git commit --file=<path>` (**no bash heredoc** — it trips a force-push blocker hook here). EN subject: `fix(detection): drain teardown task exceptions instead of orphaning them`

---

### Task 2: liveness-aware teardown, extracted once

**Goal:** Teardown skips page/context/browser operations whose target is already dead — removing up to 30 s of pointless waiting per attempt and stopping Playwright from scheduling the internal interceptor task behind the largest traceback.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py` (add helper near `_close_or_abandon`; replace the teardown blocks at `:496-513` and `:627-642`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_teardown_targets.py` (create)

**Acceptance Criteria:**
- [ ] All targets live → `unroute_all`, `context.close`, `browser.close` each awaited once
- [ ] `page.is_closed()` is `True` → `unroute_all` **not** awaited; context and browser still closed
- [ ] `browser.is_connected()` is `False` → neither `context.close` nor `browser.close` awaited
- [ ] `page` is `None` and/or `context` is `None` → no crash, browser still handled
- [ ] An exception raised inside the helper never propagates (it runs inside a `finally`; propagating would mask the original error)
- [ ] The teardown block appears **once** in the file — the duplicated copy in `scrape_html_with_redirects` is gone
- [ ] The six now-redundant `except Exception as …: logger.debug(...)` wrappers are removed
- [ ] `p.stop()` remains unconditional in both outer `finally` blocks (it reaps the driver; the leak hypothesis was falsified)

**Verify:** `python -m pytest tests/test_teardown_targets.py -v` → 6 passed

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_teardown_targets.py`:

```python
"""Liveness guards on browser teardown (2026-08-03).

On a failed scrape the page/context/browser are usually already gone, so every
teardown op raises TargetClosedError. Each one burned up to TEARDOWN_TIMEOUT_S,
and `unroute_all` on a dead page is what made Playwright schedule its internal
_update_interceptor_patterns task — the giant repeated traceback in prod logs.
"""
import pytest

from app.services.scraper import _teardown_targets


class _StubPage:
    def __init__(self, closed=False):
        self._closed = closed
        self.unroute_calls = 0

    def is_closed(self):
        return self._closed

    async def unroute_all(self, behavior=None):
        self.unroute_calls += 1


class _StubContext:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class _StubBrowser:
    def __init__(self, connected=True):
        self._connected = connected
        self.close_calls = 0

    def is_connected(self):
        return self._connected

    async def close(self):
        self.close_calls += 1


@pytest.mark.asyncio
async def test_all_live_closes_everything():
    page, context, browser = _StubPage(), _StubContext(), _StubBrowser()
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert page.unroute_calls == 1
    assert context.close_calls == 1
    assert browser.close_calls == 1


@pytest.mark.asyncio
async def test_closed_page_skips_unroute():
    page, context, browser = _StubPage(closed=True), _StubContext(), _StubBrowser()
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert page.unroute_calls == 0, "unroute_all on a closed page is the flood trigger"
    assert context.close_calls == 1
    assert browser.close_calls == 1


@pytest.mark.asyncio
async def test_disconnected_browser_skips_both_closes():
    page, context, browser = _StubPage(), _StubContext(), _StubBrowser(connected=False)
    await _teardown_targets(page, context, browser, "https://example.fr")
    assert context.close_calls == 0
    assert browser.close_calls == 0


@pytest.mark.asyncio
async def test_none_page_and_context_are_tolerated():
    browser = _StubBrowser()
    await _teardown_targets(None, None, browser, "https://example.fr")
    assert browser.close_calls == 1


@pytest.mark.asyncio
async def test_exception_inside_teardown_never_propagates():
    class _Exploding(_StubContext):
        async def close(self):
            raise RuntimeError("boom during teardown")

    browser = _StubBrowser()
    # Must not raise: this helper runs inside a `finally`, so propagating
    # would mask whatever error the scrape was already unwinding.
    await _teardown_targets(_StubPage(), _Exploding(), browser, "https://example.fr")


@pytest.mark.asyncio
async def test_single_definition_in_source():
    """The teardown block must exist once, not duplicated per scrape function."""
    import inspect
    import app.services.scraper as scraper
    src = inspect.getsource(scraper)
    assert src.count("unroute_all(behavior='ignoreErrors')") == 1, (
        "teardown is still duplicated across the two scrape functions"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_teardown_targets.py -v`
Expected RED: every test fails at import with `cannot import name '_teardown_targets'`.

- [ ] **Step 3: Add the helper**

In `app/services/scraper.py`, immediately after `_close_or_abandon`, add:

```python
async def _teardown_targets(page, context, browser, url: str) -> None:
    """Tear down page/context/browser, skipping targets that are already dead.

    On a failed scrape the targets are usually gone, so every op would raise
    TargetClosedError — each burning up to TEARDOWN_TIMEOUT_S, and `unroute_all`
    on a dead page additionally makes Playwright schedule its internal
    _update_interceptor_patterns task (the large repeated traceback in the
    2026-08-03 logs). `is_closed()` / `is_connected()` are synchronous in the
    Python API, so the guards cannot hang.

    Runs inside a `finally`: never let anything propagate, or the original
    scrape error would be masked.
    """
    try:
        # Drain in-flight route callbacks before tearing down the page.
        # Suppresses TargetClosedError flood from _route_handler firing
        # on closed pages under concurrent load.
        if page is not None and not page.is_closed():
            await _close_or_abandon(
                page.unroute_all(behavior='ignoreErrors'),
                settings.TEARDOWN_TIMEOUT_S,
                f"unroute_all {url}",
            )
        # BrowserContext exposes no is_closed() in the Python API; if the
        # browser is gone the context is gone with it.
        if context is not None and browser.is_connected():
            await _close_or_abandon(
                context.close(), settings.TEARDOWN_TIMEOUT_S, f"context.close {url}"
            )
        if browser.is_connected():
            await _close_or_abandon(
                browser.close(), settings.TEARDOWN_TIMEOUT_S, f"browser.close {url}"
            )
    except Exception as teardown_err:
        logger.debug(f"teardown error for {url}: {teardown_err!r}")
```

- [ ] **Step 4: Replace both call sites**

In `scrape_html`, replace the entire `finally:` body currently at `:496-513` (the comment plus the three guarded `_close_or_abandon` calls) with:

```python
            finally:
                await _teardown_targets(page, context, browser, url)
```

In `scrape_html_with_redirects`, replace the equivalent block at `:627-642` with the same single line at that block's indentation:

```python
                finally:
                    await _teardown_targets(page, context, browser, url)
```

Leave both outer `finally: await _close_or_abandon(p.stop(), …)` lines (`:515` and `:644`) exactly as they are.

- [ ] **Step 5: Run the tests + syntax check**

Run: `python -c "import ast; ast.parse(open('app/services/scraper.py',encoding='utf-8').read()); print('AST OK')"`
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_teardown_targets.py tests/test_close_or_abandon.py tests/test_scraper.py tests/test_scraper_result.py -v`
Expected: all pass. `tests/test_scraper.py` and `tests/test_scraper_result.py` are the existing scraper suites — they are the regression guard for the call-site edit. If either fails, STOP and report rather than editing them.

- [ ] **Step 6: Commit**

Stage exactly:
```
apps-microservices/api-detection-langue-fr/app/services/scraper.py
apps-microservices/api-detection-langue-fr/tests/test_teardown_targets.py
```
Bilingual EN-then-FR message via the Write tool + `git commit --file=<path>`. EN subject: `fix(detection): skip teardown on already-dead browser targets`

---

### Task 3: skip URL variants for failures they cannot fix

**Goal:** A domain that fails Phase 1 with a navigation timeout or empty content no longer buys up to 3 more browser launches, bringing the worst case from ~275 s to ~140 s against the 300 s per-item ceiling (275 s already sat under it on the ~45 s/launch estimate, so the cancellation actually observed implies the real per-launch cost runs higher). This halves the worst case — it does not guarantee the ceiling is never reached: `_launch_browser` can still burn ~45 s on the Camoufox `wait_for` and another ~45 s on the Chromium fallback per attempt, so under a launch-timeout storm the item can still be cancelled at 300 s instead of returning a real verdict (see "Parked, deliberately not in this plan").

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py` (new tuple near `:13-27`; gate before `:262`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_variant_gate.py` (create)

**Acceptance Criteria:**
- [ ] Phase 1 failing with `Timeout 30000ms exceeded` → `scrape_html` called exactly **3** times (`HTTP_MAX_RETRIES = 3`), never 7
- [ ] The skip logs `[VARIANTES] ignorées` at WARNING, naming the URL and the error
- [ ] Phase 1 failing with a **Gecko** DNS error (`NS_ERROR_UNKNOWN_HOST`) → variants **still** attempted (call count > 3). This is the regression guard for the engine mismatch — it fails if anyone reintroduces an allowlist keyed on Chromium codes
- [ ] Phase 1 returning `None` every attempt (empty/short content) → variants skipped
- [ ] A successful first attempt → exactly 1 call, result returned, no gate log
- [ ] `_VARIANT_ELIGIBLE_ERRORS`, `_FATAL_ERRORS` and `_NON_RETRYABLE_ERRORS` are left untouched

**Verify:** `python -m pytest tests/test_variant_gate.py -v` → 5 passed

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `tests/test_variant_gate.py`:

```python
"""Phase-2 URL variants are skipped for failures they cannot fix (2026-08-03).

A hopeless domain cost 3 retries (~140s) PLUS up to 3 variants (~135s) =
~275s, close to the 300s per-item ceiling in _run_batch_core. The item could
be cancelled in flight, and that cancellation orphaned the futures behind the
asyncio flood.

The gate is a DENYLIST on purpose: _VARIANT_ELIGIBLE_ERRORS holds only
Chromium codes while prod runs Camoufox (Firefox), so an allowlist would be
false for every real failure and would skip Phase 2 unconditionally.
"""
import asyncio

import pytest

import app.services.redirect_tracker as rt


async def _no_sleep(_seconds):
    return None


@pytest.fixture(autouse=True)
def _fast_and_offline(monkeypatch):
    monkeypatch.setattr(rt, "build_proxy_url", lambda *a, **k: "http://proxy:8000")
    monkeypatch.setattr(rt.asyncio, "sleep", _no_sleep)


def _counting_raiser(message, calls):
    async def fake_scrape(target, proxy=None):
        calls.append(target)
        raise RuntimeError(message)
    return fake_scrape


@pytest.mark.asyncio
async def test_timeout_skips_variants(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(
        rt, "scrape_html", _counting_raiser("Timeout 30000ms exceeded.", calls)
    )

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 3, f"variants were still tried: {calls}"
    assert any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_gecko_dns_error_still_tries_variants(monkeypatch):
    """Over-gating guard: Camoufox/Firefox emits NS_ERROR_*, not ERR_*."""
    calls = []
    monkeypatch.setattr(
        rt, "scrape_html", _counting_raiser("NS_ERROR_UNKNOWN_HOST", calls)
    )

    result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) > 3, (
        "a DNS failure must still reach Phase 2 — the gate must not be an "
        "allowlist keyed on Chromium error codes"
    )


@pytest.mark.asyncio
async def test_empty_content_skips_variants(monkeypatch, caplog):
    calls = []

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        return None  # drives the "Contenu vide ou trop court" branch

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    with caplog.at_level("WARNING", logger="app.services.redirect_tracker"):
        result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is None
    assert len(calls) == 3, f"variants were still tried: {calls}"
    assert any("[VARIANTES] ignorées" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_success_on_first_attempt_makes_one_call(monkeypatch):
    calls = []
    sentinel = object()

    async def fake_scrape(target, proxy=None):
        calls.append(target)
        return sentinel

    monkeypatch.setattr(rt, "scrape_html", fake_scrape)

    result = await rt.fetch_html("https://www.example.fr", proxy="p")

    assert result is sentinel
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_existing_tuples_untouched():
    assert rt._VARIANT_ELIGIBLE_ERRORS == (
        'ERR_NAME_NOT_RESOLVED',
        'ERR_CERT_DATE_INVALID',
        'ERR_SSL_PROTOCOL_ERROR',
    )
    assert rt._NON_RETRYABLE_ERRORS == rt._VARIANT_ELIGIBLE_ERRORS + rt._FATAL_ERRORS
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_variant_gate.py -v`
Expected RED: `test_timeout_skips_variants` and `test_empty_content_skips_variants` fail (call count is 7, not 3, and no `[VARIANTES] ignorées` log). The other three should already pass. Report which failed and the actual call counts.

**Known trap in this fixture.** `monkeypatch.setattr(rt.asyncio, "sleep", _no_sleep)` patches the real `asyncio.sleep` for the duration of the test, because `rt.asyncio` *is* the stdlib module. It is only there to skip `fetch_html`'s 2 s + 4 s inter-attempt waits. If it destabilises pytest-asyncio (hangs, or errors from inside the event loop rather than from the code under test), **drop that line and accept ~6 s per test** — correctness of the assertions matters, speed does not. Do not try to work around it by lowering `HTTP_MAX_RETRIES`: the call-count assertions are pinned to 3.

- [ ] **Step 3: Add the denylist tuple**

In `app/services/redirect_tracker.py`, after `_NON_RETRYABLE_ERRORS` (`:27`) and before `logger = logging.getLogger(__name__)`:

```python
# Échecs qu'un changement de variante d'URL ne peut PAS réparer.
# Basculer http/https ou www/sans-www ne rend pas un site lent plus rapide,
# et ne remplit pas une page vide. Formulations stables sur les DEUX moteurs
# (Camoufox/Firefox comme Chromium) — contrairement à _VARIANT_ELIGIBLE_ERRORS
# ci-dessus qui ne contient que des codes Chromium et ne matche donc jamais
# en production (CAMOUFOX_ENABLED=True par défaut).
_VARIANT_POINTLESS_ERRORS = (
    'Timeout',                     # « Timeout 30000ms exceeded » — Playwright, les 2 moteurs
    'Contenu vide ou trop court',  # posé plus bas, branche contenu insuffisant
)
```

- [ ] **Step 4: Add the gate**

In `fetch_html`, immediately before `variants = _generate_url_variants(url)` (`:262`):

```python
    # Un domaine injoignable coûtait 3 tentatives (~140s) PUIS jusqu'à 3
    # variantes (~135s) = ~275s, proche du plafond de 300s par item : l'item
    # pouvait être annulé en vol, et cette annulation orphelinait les futures
    # à l'origine du flood asyncio du 2026-08-03. Les variantes n'y changeaient rien.
    variant_pointless = last_error and any(
        tok in last_error for tok in _VARIANT_POINTLESS_ERRORS
    )
    if variant_pointless:
        logger.warning(
            f"[VARIANTES] ignorées pour {url} — "
            f"échec non réparable par une variante: {last_error}"
        )
        return None
```

- [ ] **Step 5: Run the tests + syntax check**

Run: `python -c "import ast; ast.parse(open('app/services/redirect_tracker.py',encoding='utf-8').read()); print('AST OK')"`
Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_variant_gate.py tests/test_redirect_tracker_result.py -v`
Expected: 5 passed in the new file, and `tests/test_redirect_tracker_result.py` (existing) still passes.

- [ ] **Step 6: Prove the gate bites**

Temporarily change `_VARIANT_POINTLESS_ERRORS` to an empty tuple `()` and re-run `test_timeout_skips_variants` → it MUST fail with a call count of 7. Restore the tuple exactly and re-run → 5 passed. Report both outcomes and confirm the restoration is byte-identical.

- [ ] **Step 7: Regression run + commit**

Run: `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/ --ignore=tests/test_api.py -q`
Expected: `7 failed` and nothing else new; the passed count rises by however many tests were added across all three tasks. Takes ~5 minutes — foreground, wait for it.

Stage exactly:
```
apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py
apps-microservices/api-detection-langue-fr/tests/test_variant_gate.py
```
Bilingual EN-then-FR message via the Write tool + `git commit --file=<path>`. EN subject: `fix(detection): skip URL variants for failures they cannot repair`

---

## Deploy (after all tasks, user-controlled)

`git push origin features/poc` + **Docker rebuild of `api-detection-langue-fr` on the VM**. No BO, no migration, no env var, no compose change.

## Post-deploy verification

On the next `domaine_fr_retry` batch, in the container log:

- `Pass 1 termine` wall clock roughly halved versus the 659325 ms baseline
- items reported as `fetch_failed` rather than `error` / `Timeout global item (300s)`
- `[VARIANTES] ignorées` lines present
- **no** `Task exception was never retrieved` / `Future exception was never retrieved`
- `docker stats` PIDs lower than 876 — a secondary confirmation that the count tracks in-flight launches rather than leakage
- `Timeout global item (300s)` should go to zero — if it doesn't, the residual path noted below (`_launch_browser` still burning ~90 s/attempt on launch timeouts) is live
- `Timeout lancement Camoufox (45s), fallback vers Chromium` — its frequency tells the operator whether to schedule the wall-clock-deadline work below

## Parked, deliberately not in this plan

- **`_VARIANT_ELIGIBLE_ERRORS` is Chromium-only**, so the `break` at `redirect_tracker.py:245-247` is dead on Camoufox: a DNS failure burns all 3 retries instead of short-circuiting to Phase 2. Fixing it means asserting exact Gecko token strings, unverifiable without a browser on this machine — and a wrong token silently re-disables the path, the exact failure already caught once. Verify against a real Camoufox DNS failure first.
- **A wall-clock deadline inside `fetch_html`** — not insurance against a hypothetical future cascade: it is the residual path by which this incident can recur. `_launch_browser` can burn ~45 s on the Camoufox `wait_for` then another ~45 s on the Chromium fallback (~90 s/attempt before navigation starts), so three attempts plus the 2 s/4 s sleeps ≈ 280 s, and the browser-semaphore wait is charged to the same 300 s item budget (`ADMISSION_MAX_SLOTS=8` exceeds `BROWSER_SEMAPHORE_SIZE=6`, so two admitted items always queue). Under a launch-timeout storm — the incident's own condition — items can still be cancelled at 300 s. Task 3 brings the worst case to ~140 s against a 300 s budget; kept out of scope for this plan, but that is the plain reason.
- **The duplicated `WARNING`/`ERROR` log lines** (`INFO` lines are not duplicated → likely a second handler at WARNING+ level alongside `main.py:22`'s `basicConfig`). Cosmetic, doubles flood volume, separate investigation.
- **`ADMISSION_MAX_SLOTS=8` exceeding `BROWSER_SEMAPHORE_SIZE=6`** — two admitted requests always queue on the browser semaphore. Harmless; not touched.
