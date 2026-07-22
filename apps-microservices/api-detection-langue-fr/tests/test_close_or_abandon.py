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
    assert elapsed < 1.0
    assert started.is_set()


@pytest.mark.asyncio
async def test_returns_when_coro_completes():
    ran = {"v": False}

    async def quick():
        ran["v"] = True

    await _close_or_abandon(quick(), timeout=5, what="test")
    assert ran["v"] is True
