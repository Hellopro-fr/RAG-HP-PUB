from __future__ import annotations
import threading


class PortPoolExhausted(Exception):
    pass


class PortPool:
    def __init__(self, start: int, end: int):
        if end < start:
            raise ValueError("end must be >= start")
        self._start = start
        self._end = end
        self._used: set[int] = set()
        # threading.Lock (not asyncio.Lock): allocate/release may be called from
        # both the event-loop thread and executor threads (supervisor callbacks).
        self._lock = threading.Lock()

    def allocate(self) -> int:
        with self._lock:
            for p in range(self._start, self._end + 1):
                if p not in self._used:
                    self._used.add(p)
                    return p
            raise PortPoolExhausted(f"no free port in [{self._start}, {self._end}]")

    def release(self, port: int) -> None:
        with self._lock:
            self._used.discard(port)

    def used(self) -> list[int]:
        with self._lock:
            return sorted(self._used)
