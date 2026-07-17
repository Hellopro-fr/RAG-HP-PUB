"""Graceful-drain helper: interrupt an idle queue wait on shutdown without
dropping an already-dequeued item."""

import asyncio
import importlib
import sys

from common_utils.autres.graceful import get_message_or_stop


def test_imports_without_heavy_optional_deps(monkeypatch):
    """Regression guard: the drain helper must import with only the stdlib.

    It is used by services (document-echange-processor) that do NOT install
    prometheus_client / pika / redis. It previously lived in
    common_utils.concurrency, whose __init__ eagerly imports the Milvus guard
    (prometheus_client) -> the service crashed on startup with ModuleNotFoundError.
    """
    for mod in ("prometheus_client", "pika", "redis"):
        monkeypatch.setitem(sys.modules, mod, None)  # make `import mod` raise
    monkeypatch.delitem(sys.modules, "common_utils.autres.graceful", raising=False)
    reloaded = importlib.import_module("common_utils.autres.graceful")
    assert hasattr(reloaded, "get_message_or_stop")


def test_returns_item_when_available():
    async def go():
        q, ev = asyncio.Queue(), asyncio.Event()
        await q.put("m1")
        return await get_message_or_stop(q, ev)

    assert asyncio.run(go()) == "m1"


def test_returns_none_when_already_stopped_without_consuming():
    async def go():
        q, ev = asyncio.Queue(), asyncio.Event()
        await q.put("m1")
        ev.set()  # stop already requested
        result = await get_message_or_stop(q, ev)
        return result, q.qsize()

    result, qsize = asyncio.run(go())
    assert result is None
    assert qsize == 1  # item left in buffer -> unacked -> redelivered, not lost


def test_returns_none_when_stopped_while_waiting():
    async def go():
        q, ev = asyncio.Queue(), asyncio.Event()
        task = asyncio.ensure_future(get_message_or_stop(q, ev))
        await asyncio.sleep(0.01)  # block on the empty queue
        ev.set()
        return await task

    assert asyncio.run(go()) is None


def test_returns_item_if_it_arrives_while_waiting():
    async def go():
        q, ev = asyncio.Queue(), asyncio.Event()
        task = asyncio.ensure_future(get_message_or_stop(q, ev))
        await asyncio.sleep(0.01)
        await q.put("m2")
        return await task

    assert asyncio.run(go()) == "m2"
