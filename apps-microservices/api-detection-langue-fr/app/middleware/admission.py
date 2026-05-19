"""FastAPI admission-control middleware.

Scope after the crawler carve-out refactor:
- /detect, /detect-batch, /check-url → gated at the route level (or
  not at all), NOT by this middleware.
- /detect-debug → gated by the debug-only controller here so dev
  traffic cannot starve the production browser semaphore.
- Infrastructure endpoints (/health, /metrics, /, /docs, /openapi.json)
  bypass admission entirely.

On rejection: 503 + Retry-After. On accept: counter++ until response
is built, then counter-- in finally.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.admission import AdmissionController
from app.core.metrics import ADMISSION_REJECTED

logger = logging.getLogger(__name__)

# Path using the isolated debug slot pool.
_DEBUG_PATH = "/api/v1/detect-debug"


class AdmissionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        debug_controller: AdmissionController,
        retry_after_seconds: int = 30,
        enabled: bool = True,
    ):
        super().__init__(app)
        self._debug = debug_controller
        self._retry_after = str(int(retry_after_seconds))
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled or request.url.path != _DEBUG_PATH:
            return await call_next(request)

        admitted = await self._debug.acquire()
        if not admitted:
            ADMISSION_REJECTED.labels(endpoint=_DEBUG_PATH).inc()
            logger.warning(
                f"Admission rejected for {_DEBUG_PATH}: "
                f"{self._debug.inflight}/{self._debug.max_slots} in flight"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily saturated",
                    "retry_after_seconds": int(self._retry_after),
                },
                headers={"Retry-After": self._retry_after},
            )

        try:
            return await call_next(request)
        finally:
            await self._debug.release()
