"""Graceful-drain helper for asyncio queue consumers."""

import asyncio
from typing import Any, Optional


async def get_message_or_stop(
    buffer: "asyncio.Queue", stop_event: "asyncio.Event"
) -> Optional[Any]:
    """Await the next item from ``buffer``, or return ``None`` as soon as
    ``stop_event`` is set while the buffer is empty.

    Makes a batch consumer's idle wait interruptible by a graceful shutdown: a
    batch already being processed is untouched (this only governs the wait for
    the NEXT batch), and items still sitting unconsumed are left in the buffer
    (unacked upstream -> redelivered on restart), so nothing is lost. An item
    that has actually been dequeued is always returned, never dropped.
    """
    if stop_event.is_set():
        return None
    get_task = asyncio.ensure_future(buffer.get())
    stop_task = asyncio.ensure_future(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {get_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        stop_task.cancel()
    if get_task in done:
        return get_task.result()
    get_task.cancel()
    return None
