from fastapi import FastAPI
from app.router import search as search_router
from app.core.credentials import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API pour interroger Qdrant ou Milvus et générer des réponses avec des LLMs."
)

app.include_router(search_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
