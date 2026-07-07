"""Unit tests for the in-memory log ring buffer."""
import logging
import threading
import pytest

from app.core import log_buffer


@pytest.fixture(autouse=True)
def clean_buffer():
    log_buffer.clear()
    yield
    log_buffer.clear()


def _emit(handler, level, msg):
    record = logging.LogRecord("t", level, __file__, 1, msg, None, None)
    handler.emit(record)


def test_emit_and_get_recent():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    _emit(h, logging.INFO, "AUTO_STASH crawl_id=42 reason=grace")
    _emit(h, logging.WARNING, "STASH_UPLOAD_ORPHAN crawl_id=43")
    lines = log_buffer.get_recent()
    assert len(lines) == 2
    assert "AUTO_STASH" in lines[0]  # chronological order


def test_grep_and_level_filter():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    _emit(h, logging.INFO, "noise")
    _emit(h, logging.WARNING, "AUTO_STASH crawl_id=42")
    assert log_buffer.get_recent(grep="AUTO_STASH") == ["WARNING | AUTO_STASH crawl_id=42"]
    assert log_buffer.get_recent(min_levelno=logging.WARNING) == ["WARNING | AUTO_STASH crawl_id=42"]


def test_limit_keeps_newest():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    for i in range(10):
        _emit(h, logging.INFO, f"line-{i}")
    lines = log_buffer.get_recent(limit=3)
    assert lines == ["line-7", "line-8", "line-9"]


def test_get_recent_snapshots_while_appending():
    """get_recent iterates a snapshot — concurrent emits must not raise
    'deque mutated during iteration'."""
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    _emit(h, logging.INFO, "seed")
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            _emit(h, logging.INFO, f"w-{i}")
            i += 1

    t = threading.Thread(target=writer)
    t.start()
    try:
        for _ in range(200):
            lines = log_buffer.get_recent()
            assert all(isinstance(l, str) for l in lines)
    finally:
        stop.set()
        t.join()


def test_emit_never_raises():
    h = log_buffer.RingBufferHandler()  # no formatter set -> format() still works
    _emit(h, logging.INFO, "ok")
    h.format = lambda r: (_ for _ in ()).throw(RuntimeError("boom"))
    _emit(h, logging.INFO, "must not raise")
