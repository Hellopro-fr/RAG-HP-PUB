"""Graceful-drain behavior of the batch consumer.

Skipped locally (the app package is renamed to ``document_echange_processor_service``
in the image and Presidio must be importable); runs in CI/container.
"""

import asyncio
from unittest.mock import Mock

import pytest

consumer_mod = pytest.importorskip(
    "document_echange_processor_service.messaging.consumer"
)
Consumer = consumer_mod.Consumer


def test_batch_processor_exits_when_stopped_while_idle():
    async def go():
        c = Consumer(connection=Mock(), publisher=Mock())
        c._stop_event = asyncio.Event()
        task = asyncio.ensure_future(c.batch_processor())
        await asyncio.sleep(0.05)  # let it block on the empty buffer
        assert not task.done()
        c._stop_event.set()  # request graceful stop
        await asyncio.wait_for(task, timeout=2)
        assert task.done() and task.exception() is None

    asyncio.run(go())


def test_buffered_message_not_dropped_on_stop():
    """A delivered-but-unpulled message must stay in the buffer (unacked upstream
    -> redelivered on restart), never silently dropped, when stop fires first."""

    async def go():
        c = Consumer(connection=Mock(), publisher=Mock())
        c._stop_event = asyncio.Event()
        c._stop_event.set()  # already stopping
        await c.message_buffer.put("m")  # a delivered-but-unpulled message
        task = asyncio.ensure_future(c.batch_processor())
        await asyncio.wait_for(task, timeout=2)
        assert c.message_buffer.qsize() == 1  # not consumed -> will be redelivered

    asyncio.run(go())
