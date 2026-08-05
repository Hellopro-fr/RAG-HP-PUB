"""The loop exception handler drains orphaned Playwright protocol callbacks.

A cancelled scrape leaves `page.goto`'s protocol callback pending-and-uncancelled;
`Connection.cleanup()` then sets TargetClosedError on it. Nobody can retrieve it —
the awaiting frame is gone by construction. Playwright suppresses the two sibling
cases (no_reply, already-cancelled) and misses this one (upstream
playwright-python#2163, unchanged through v1.62.0), so we complete the suppression.

The handler must stay NARROW: a TargetClosedError on a live awaited path has an
owning task and must still be reported.
"""
import asyncio

import pytest
from playwright.async_api import Error as PlaywrightError

import main as main_module
from main import _handle_loop_exception
from app.core.metrics import ORPHANED_PROTOCOL_FUTURES


class _TargetClosedError(PlaywrightError):
    """Stand-in with the real class NAME — the handler matches on the name
    because playwright.async_api does not export TargetClosedError."""
    pass


_TargetClosedError.__name__ = "TargetClosedError"


class _FakeLoop:
    def __init__(self):
        self.delegated = []

    def default_exception_handler(self, context):
        self.delegated.append(context)


def _count():
    return ORPHANED_PROTOCOL_FUTURES._value.get()


def test_orphaned_future_is_drained_and_counted():
    loop = _FakeLoop()
    before = _count()

    _handle_loop_exception(loop, {
        "message": "Future exception was never retrieved",
        "exception": _TargetClosedError("Target page, context or browser has been closed"),
        "future": asyncio.Future(),
    })

    assert loop.delegated == [], "an orphaned protocol future must not be reported"
    assert _count() == before + 1, "the silenced orphan must be counted"


def test_target_closed_with_owning_task_is_delegated():
    """The guard against becoming a blanket suppressor."""
    loop = _FakeLoop()

    _handle_loop_exception(loop, {
        "message": "Task exception was never retrieved",
        "exception": _TargetClosedError("Target page, context or browser has been closed"),
        "future": asyncio.Future(),
        "task": object(),
    })

    assert len(loop.delegated) == 1, "a TargetClosedError with an owner must be reported"


def test_other_playwright_error_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {
        "exception": PlaywrightError("some other playwright failure"),
        "future": asyncio.Future(),
    })
    assert len(loop.delegated) == 1


def test_non_playwright_exception_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {
        "exception": ValueError("unrelated"),
        "future": asyncio.Future(),
    })
    assert len(loop.delegated) == 1


def test_context_without_exception_is_delegated():
    loop = _FakeLoop()
    _handle_loop_exception(loop, {"message": "something odd happened"})
    assert len(loop.delegated) == 1


@pytest.mark.asyncio
async def test_lifespan_installs_the_loop_exception_handler(monkeypatch):
    """Nothing previously asserted the handler is actually wired onto the
    running loop — every other test here calls _handle_loop_exception
    directly. Mirrors tests/test_main.py:78-100
    (test_lifespan_inits_shared_pool_and_bridges_redis_url)'s setup: fake
    init/close so no real Redis is touched, then enter the real
    lifespan(app) context and inspect the loop it ran on."""
    async def fake_init():
        pass

    async def fake_close():
        pass

    monkeypatch.setattr(main_module, "init_redis_pool", fake_init)
    monkeypatch.setattr(main_module, "close_redis_pool", fake_close)

    async with main_module.lifespan(main_module.app):
        assert asyncio.get_running_loop().get_exception_handler() is main_module._handle_loop_exception
