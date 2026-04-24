from __future__ import annotations

import logging
import socket
import threading

logger = logging.getLogger("port_pool")


class PortPoolExhausted(Exception):
    pass


def _port_is_busy(port: int, host: str = "127.0.0.1", timeout: float = 0.2) -> bool:
    """Returns True if something is currently accepting connections on
    (host, port). Uses connect() rather than bind() because a freshly-dead
    child leaves the port in TIME_WAIT, during which bind() would (falsely
    for our purpose) report the port as taken — connect() correctly
    reports no-one-listening there.

    We probe 127.0.0.1 since mcp-proxy binds 0.0.0.0 inside the container
    and any 0.0.0.0 listener accepts loopback connects.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


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

    def allocate(self, probe: bool = True, preferred: int | None = None) -> int:
        """Return the lowest port in the range that is:
          1. not already handed out by this pool, AND
          2. not currently accepting connections on 127.0.0.1 (unless
             probe=False).

        If ``preferred`` is supplied AND inside the range AND passes both
        checks, it wins over the sequential scan. This is how startup sync
        restores stable per-instance ports across runner restarts (the
        gateway sends the last-known port; the runner tries to reuse it so
        the mcp_servers.url stored in the DB stays valid).

        Skipping externally-busy ports guards against stale pool state after
        an unclean runner restart, and against a foreign process that happens
        to bind a port inside our range.
        """
        with self._lock:
            # Preferred-port fast path.
            if preferred is not None and self._start <= preferred <= self._end:
                if preferred not in self._used:
                    if not probe or not _port_is_busy(preferred):
                        self._used.add(preferred)
                        return preferred
                    logger.warning(
                        "port_pool: preferred %d is busy, falling back to sequential",
                        preferred,
                    )
            # Sequential scan (original behaviour).
            for p in range(self._start, self._end + 1):
                if p in self._used:
                    continue
                if probe and _port_is_busy(p):
                    logger.warning(
                        "port_pool: skipping %d — something is listening outside the pool",
                        p,
                    )
                    continue
                self._used.add(p)
                return p
            raise PortPoolExhausted(f"no free port in [{self._start}, {self._end}]")

    def release(self, port: int) -> None:
        with self._lock:
            self._used.discard(port)

    def used(self) -> list[int]:
        with self._lock:
            return sorted(self._used)
