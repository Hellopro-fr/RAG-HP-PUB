"""FastAPI admission-control middleware.

Per-path routing to two AdmissionController instances:
- Production endpoints (/detect, /detect-batch, /check-url) share one pool
- /detect-debug has its own smaller pool so dev traffic can't starve prod
- Infrastructure endpoints (/health, /metrics, /, /docs, /openapi.json)
  bypass admission entirely

On rejection: 503 + Retry-After. On accept: counter++ until response
is built, then counter-- in finally.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.admission import AdmissionController
from app.core.metrics import ADMISSION_REJECTED, INFLIGHT_REQUESTS

logger = logging.getLogger(__name__)

# Paths that use the production slot pool.
_PROD_PATHS = frozenset({
    "/api/v1/detect",
    "/api/v1/detect-batch",
    "/api/v1/check-url",
})

# Path using the isolated debug slot pool.
_DEBUG_PATH = "/api/v1/detect-debug"


class AdmissionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        prod_controller: AdmissionController,
        debug_controller: AdmissionController,
        retry_after_seconds: int = 30,
        enabled: bool = True,
    ):
        super().__init__(app)
        self._prod = prod_controller
        self._debug = debug_controller
        self._retry_after = str(int(retry_after_seconds))
        self._enabled = enabled

    def _pick_controller(self, path: str):
        if path == _DEBUG_PATH:
            return self._debug, _DEBUG_PATH
        if path in _PROD_PATHS:
            return self._prod, path
        return None, None

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            return await call_next(request)

        controller, endpoint_label = self._pick_controller(request.url.path)
        if controller is None:
            # Not an admission-controlled path (health, metrics, docs, etc.)
            return await call_next(request)

        admitted = await controller.acquire()
        if not admitted:
            ADMISSION_REJECTED.labels(endpoint=endpoint_label).inc()
            logger.warning(
                f"Admission rejected for {endpoint_label}: "
                f"{controller.inflight}/{controller.max_slots} in flight"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily saturated",
                    "retry_after_seconds": int(self._retry_after),
                },
                headers={"Retry-After": self._retry_after},
            )

        INFLIGHT_REQUESTS.inc()
        try:
            return await call_next(request)
        finally:
            await controller.release()
            INFLIGHT_REQUESTS.dec()
