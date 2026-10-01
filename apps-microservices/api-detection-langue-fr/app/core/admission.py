"""Admission control primitive.

Non-blocking counter: acquire() either succeeds immediately (slot
available) or returns False (saturated). Never queues. Callers see
fast-fail rather than latency, which is the point.
"""
import asyncio


class AdmissionController:
    """Atomic in-flight counter with a hard max.

    Not a semaphore: acquire() does NOT block when the counter is at
    max — it returns False so the caller can emit 503+Retry-After.
    """

    def __init__(self, max_slots: int) -> None:
        if max_slots < 1:
            raise ValueError("max_slots must be >= 1")
        self._max = max_slots
        self._counter = 0
        self._lock = asyncio.Lock()

    @property
    def inflight(self) -> int:
        """Current admitted in-flight count (unsynchronized read for observability)."""
        return self._counter

    @property
    def max_slots(self) -> int:
        return self._max

    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns True on success, False if saturated."""
        async with self._lock:
            if self._counter >= self._max:
                return False
            self._counter += 1
            return True

    async def release(self) -> None:
        """Release a slot. Defensive: does not go below zero."""
        async with self._lock:
            if self._counter > 0:
                self._counter -= 1
