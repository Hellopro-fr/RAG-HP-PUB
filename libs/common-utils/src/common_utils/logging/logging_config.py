import logging
import sys


LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def setup_logging(service_name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure root logger and return a named logger for the service.

    Safe to call multiple times — skips handler setup if already configured.
    """
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        root_logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)

    return logging.getLogger(service_name)
