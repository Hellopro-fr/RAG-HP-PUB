import logging
import os
import sys


LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"

_LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(service_name: str, level: int | None = None) -> None:
    """Configure root logger with a stdout handler.

    Safe to call multiple times — skips handler setup if already configured.
    Level is resolved from: explicit parameter > LOG_LEVEL env var > INFO default.
    """
    if level is None:
        env_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = _LOG_LEVEL_MAP.get(env_level, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)
