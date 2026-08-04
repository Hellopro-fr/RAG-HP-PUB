import asyncio
import gc
import pytest
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
