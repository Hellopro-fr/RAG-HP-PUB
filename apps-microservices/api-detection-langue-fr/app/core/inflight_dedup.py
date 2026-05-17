"""In-process URL coalescing primitive.

NOT a cache — the entry only lives while the fetch is actually in
flight. After the factory resolves or raises, the entry is removed so
subsequent calls run a fresh factory.

Purpose: when N concurrent callers ask for the same URL at the same
time, run the expensive browser launch once and give them all the same
result. The existing Redis cache handles the "completed within last
30d/7d/6h" case; this handles the "completed 20ms ago but cache not
written yet" case.

Note: emits ``DEDUP_HITS`` Prometheus counter on the follower path via a
direct ``app.core.metrics`` import. This couples the primitive to the
service's observability stack. If this module is ever extracted to a
shared library (``libs/common-utils``), convert the metric increment to a
constructor-injected callback hook (``on_follower_hit: Callable[[], None]``)
so the primitive stays pure.
"""
import asyncio
from typing import Awaitable, Callable, TypeVar

from app.core.metrics import DEDUP_HITS

T = TypeVar("T")


class InflightDedup:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._hits = 0

    def reset(self) -> None:
        """Clear all in-flight state. Test-isolation helper only — do NOT
        call from production code. Drops the in-flight registry without
        cancelling any awaiting futures (acceptable in test teardown
        where the loop is being torn down anyway)."""
        self._inflight.clear()
        self._hits = 0

    @property
    def hits(self) -> int:
        """Number of coalesced calls served from a shared future."""
        return self._hits

    async def coalesce(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        """Run factory() at most once for concurrent callers with the same key.

        First caller for the key: registers a future, runs factory(), resolves
        the future, cleans up the entry.
        Concurrent callers: await the existing future and get the same result
        (or exception).

        The factory runs OUTSIDE the lock so unrelated coalesce() calls for
        different keys are not serialized.

        DEDUP_HITS Prometheus counter is incremented by exactly 1 per
        follower call (i.e., per caller that gets coalesced onto an
        existing future). This is the correct semantic count and avoids
        the multi-count race that arises when callers compute a delta
        against a shared counter snapshot.
        """
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                self._hits += 1
                DEDUP_HITS.inc()
                fut = existing
                is_owner = False
            else:
                fut = asyncio.get_event_loop().create_future()
                self._inflight[key] = fut
                is_owner = True

        if not is_owner:
            # Wait on someone else's future
            return await fut

        # We own the future: run factory, resolve future, clean up
        try:
            result = await factory()
        except BaseException as e:
            fut.set_exception(e)
            raise
        else:
            fut.set_result(result)
            return result
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
