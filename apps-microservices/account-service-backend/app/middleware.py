import logging
import secrets
import time

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("request")

REDACT_HEADERS = {"authorization", "cookie", "x-admin-key"}


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        rid_bytes = headers.get(b"x-request-id")
        rid = (
            rid_bytes.decode() if rid_bytes else secrets.token_urlsafe(8)
        )
        scope["request_id"] = rid

        start = time.perf_counter()

        async def send_with_header(msg):
            if msg["type"] == "http.response.start":
                msg.setdefault("headers", []).append(
                    (b"x-request-id", rid.encode())
                )
            await send(msg)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s rid=%s elapsed_ms=%.1f",
                scope.get("method"),
                scope.get("path"),
                rid,
                elapsed_ms,
            )
