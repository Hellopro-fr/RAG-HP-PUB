import logging
from fastapi import FastAPI
from app.api.routes import router

# Configuration du logging — INFO pour voir les logs de stratégie proxy, retry, etc.
# Sans cette configuration, Python utilise WARNING par défaut et masque les logs INFO.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="API Détection Langue Française",
    description="Détecte si un site web est en français ou dispose d'une version française",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "API Détection Langue Française",
        "documentation": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
