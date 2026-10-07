"""Side HTTP server: /health (DB reachable) and /metrics (Prometheus)."""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def db_ping(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def _safe(check: Callable[[], bool]) -> bool:
    try:
        return bool(check())
    except Exception:
        logger.warning("health check failed", exc_info=True)
        return False


def start_http_server(port: int, health_check: Callable[[], bool], host: str = "0.0.0.0") -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            if self.path == "/health":
                healthy = _safe(health_check)
                body = b'{"status":"ok"}' if healthy else b'{"status":"unavailable"}'
                self._send(200 if healthy else 503, body, "application/json")
            elif self.path == "/metrics":
                self._send(200, generate_latest(), CONTENT_TYPE_LATEST)
            else:
                self._send(404, b"not found", "text/plain")

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 — silence per-request logs
            return

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="http").start()
    return server
