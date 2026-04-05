import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.wsgi import WSGIMiddleware
from common_utils.logging import setup_logging
from common_utils.metrics.prometheus import get_metrics_app

from app.core.config import settings
from app.routers import clean, extract

setup_logging("content-extractor-api-service")
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="HTML cleaning and header/footer extraction API",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Prometheus metrics
metrics_app = get_metrics_app()
app.mount("/metrics", WSGIMiddleware(metrics_app))

# CORS — internal service, not exposed publicly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal service only — not exposed publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_payload_size(request: Request, call_next):
    """Reject requests exceeding MAX_PAYLOAD_SIZE_MB."""
    content_length = request.headers.get("content-length")
    max_bytes = settings.MAX_PAYLOAD_SIZE_MB * 1024 * 1024
    if content_length and int(content_length) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Payload exceeds {settings.MAX_PAYLOAD_SIZE_MB}MB limit",
                "error_code": "PAYLOAD_TOO_LARGE",
            },
        )
    return await call_next(request)


app.include_router(clean.router)
app.include_router(extract.router)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
