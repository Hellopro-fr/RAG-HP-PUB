"""Graceful-drain helper: interrupt an idle queue wait on shutdown without
dropping an already-dequeued item."""

import asyncio

from common_utils.concurrency.graceful import get_message_or_stop


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
