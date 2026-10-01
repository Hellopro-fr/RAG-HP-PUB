import asyncio
import gc
import pytest
from prometheus_client import REGISTRY

from app.core.metrics import BROWSERS_UNCLOSED, TEARDOWN_ABANDONED
from app.services.scraper import _close_or_abandon, _drain_orphan_exception


@pytest.mark.asyncio
async def test_abandons_hanging_coro_within_timeout():
    started = asyncio.Event()

    async def hangs():
        started.set()
        await asyncio.Event().wait()  # never resolves

    t0 = asyncio.get_event_loop().time()
    await _close_or_abandon(hangs(), timeout=0.2, what="test")
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 1.0
    assert started.is_set()


@pytest.mark.asyncio
async def test_returns_when_coro_completes():
    ran = {"v": False}

    async def quick():
        ran["v"] = True

    await _close_or_abandon(quick(), timeout=5, what="test")
    assert ran["v"] is True


# --- Exception draining (2026-08-03) -----------------------------------------
# asyncio.wait() does NOT retrieve results. Without draining, a teardown that
# fails (TargetClosedError on an already-dead browser) makes asyncio log
# "Task exception was never retrieved" — the flood reported in prod.


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
async def test_cancelled_task_does_not_raise():
    """A cancelled teardown must not turn into a CancelledError from the
    drain path — t.exception() raises on a cancelled task."""
    async def slow():
        await asyncio.sleep(10)

    t = asyncio.ensure_future(slow())
    t.cancel()
    # Let the loop actually run the cancellation through so `t` is genuinely
    # CANCELLED (not just cancel-requested) before feeding it through the same
    # drain callback the abandoned/caller-cancelled paths install.
    await asyncio.sleep(0)
    _drain_orphan_exception(t)  # must not raise


# --- Abandonment is observable (2026-08-17) ----------------------------------
# Before this, an abandon left exactly one WARNING line and no counter, so its
# real frequency was unknowable. The gauge additionally makes the overlap
# readable: browsers whose close() never returned stay counted while the
# semaphore hands their slot to the next scrape.


def _abandoned(op):
    return TEARDOWN_ABANDONED.labels(op=op)._value.get()


@pytest.mark.asyncio
async def test_abandon_is_counted_by_op_family():
    before = _abandoned("browser.close")

    async def hangs():
        await asyncio.Event().wait()

    await _close_or_abandon(hangs(), timeout=0.01,
                            what="browser.close https://example.fr/a")
    # The URL must never become a label value: unbounded cardinality.
    assert REGISTRY.get_sample_value(
        "detect_teardown_abandoned_total",
        {"op": "browser.close https://example.fr/a"},
    ) is None
    assert _abandoned("browser.close") == before + 1


@pytest.mark.asyncio
async def test_teardown_that_completes_is_not_counted():
    """Opposite polarity of the test above: only abandons may be counted."""
    before = _abandoned("context.close")

    async def quick():
        return None

    await _close_or_abandon(quick(), timeout=5, what="context.close https://example.fr")
    assert _abandoned("context.close") == before


@pytest.mark.asyncio
async def test_settled_browser_close_decrements_gauge_even_late():
    """The gauge stays up while a browser.close is abandoned, and only comes
    down when that close finally settles — which may be long after we walked
    away from it."""
    release = asyncio.Event()

    async def hangs():
        await release.wait()

    BROWSERS_UNCLOSED.inc()  # stands in for the launch site
    before = BROWSERS_UNCLOSED._value.get()

    await _close_or_abandon(hangs(), timeout=0.01,
                            what="browser.close https://example.fr")
    assert BROWSERS_UNCLOSED._value.get() == before, (
        "an abandoned browser.close must NOT be treated as a confirmed exit"
    )

    release.set()
    await asyncio.sleep(0.05)  # let the orphan settle -> done-callback fires
    assert BROWSERS_UNCLOSED._value.get() == before - 1


@pytest.mark.asyncio
async def test_browser_close_that_raises_does_not_decrement_the_gauge():
    """A close that settles by RAISING is not a confirmed exit.

    `browser.close()` only returns after the driver confirms the browser is dead
    and its profile removed, so a `TargetClosedError` means the pipe died first
    and nothing was confirmed. `_teardown_targets` already keeps a browser
    counted when it SKIPS the close on `is_connected()` false, for that same
    reason — both paths say "the pipe is dead", so both must behave alike.
    Decrementing here would make the gauge under-report, i.e. err toward hiding
    the overlap it exists to reveal.
    """
    async def raises():
        raise RuntimeError("TargetClosedError: Target page, context or browser has been closed")

    BROWSERS_UNCLOSED.inc()  # stands in for the launch site
    before = BROWSERS_UNCLOSED._value.get()

    await _close_or_abandon(raises(), timeout=1.0,
                            what="browser.close https://example.fr")
    await asyncio.sleep(0)  # let the done-callback run

    assert BROWSERS_UNCLOSED._value.get() == before, (
        "a browser.close that raised must stay counted — the browser's death "
        "was never confirmed"
    )

    BROWSERS_UNCLOSED.dec()  # undo the stand-in so the suite stays balanced


@pytest.mark.asyncio
async def test_other_teardown_ops_never_touch_the_gauge():
    """Every teardown op shares this drain callback; only browser.close means a
    browser is done with."""
    before = BROWSERS_UNCLOSED._value.get()

    async def quick():
        return None

    for what in ("unroute_all https://example.fr",
                 "context.close https://example.fr",
                 "playwright.stop https://example.fr"):
        await _close_or_abandon(quick(), timeout=5, what=what)

    assert BROWSERS_UNCLOSED._value.get() == before
