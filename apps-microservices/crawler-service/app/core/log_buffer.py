"""In-memory ring buffer of recent orchestrator log lines.

Docker logs rotate (~30MB json-file) and are ssh-only; this keeps the last
RECENT_LOGS_MAXLEN formatted records of THIS replica queryable over HTTP via
GET /admin/recent-logs. Memory-only by design — no disk, no rotation logic.
"""
import logging
import re
from collections import deque
from typing import List, Optional, Tuple

RECENT_LOGS_MAXLEN = 5000

_buffer: "deque[Tuple[int, str]]" = deque(maxlen=RECENT_LOGS_MAXLEN)


class RingBufferHandler(logging.Handler):
    """Appends (levelno, formatted line) to the module-level ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append((record.levelno, self.format(record)))
        except Exception:
            pass  # logging must never break the app


def get_recent(grep: Optional[str] = None, min_levelno: int = logging.INFO,
               limit: int = 500) -> List[str]:
    """Newest `limit` matching lines, returned in chronological order.
    Raises re.error on an invalid grep pattern (caller maps to 400)."""
    rx = re.compile(grep) if grep else None
    out: List[str] = []
    # Snapshot: executor threads append concurrently; iterating the live
    # deque would raise "deque mutated during iteration".
    for levelno, line in reversed(list(_buffer)):
        if levelno < min_levelno:
            continue
        if rx is not None and not rx.search(line):
            continue
        out.append(line)
        if len(out) >= limit:
            break
    out.reverse()
    return out


def clear() -> None:
    """Test helper."""
    _buffer.clear()
