import logging

from fastapi import FastAPI

from app.core.config import get_settings
from app.router import agents as agents_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

settings = get_settings()
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Exécution des agents IA HelloPro (Dust maison) avec LangGraph.",
)
app.include_router(agents_router.router)


@app.get("/health", tags=["Monitoring"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION}
