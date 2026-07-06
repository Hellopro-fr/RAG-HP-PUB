"""main.py dictConfig must install the ring buffer handler on the root logger."""
import logging

from app.core import log_buffer


def test_root_logger_feeds_ring_buffer():
    import main  # noqa: F401  (applies dictConfig at import)
    log_buffer.clear()
    logging.getLogger("app.core.crawler_manager").info("RING_PROBE hello")
    assert any("RING_PROBE" in l for l in log_buffer.get_recent(grep="RING_PROBE"))
