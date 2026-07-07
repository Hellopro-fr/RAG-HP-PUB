from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import router
from app.core.config import settings
from app.core import metrics  # noqa: F401  — registers metric objects with the default registry

app = FastAPI(
    title=settings.APP_NAME,
    description="API de comparaison textuelle via difflib. "
                "Détermine si un contenu a suffisamment changé pour nécessiter une mise à jour (ratio < seuil).",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router, prefix="/api/v1")


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8998)
