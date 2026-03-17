import time
from fastapi import FastAPI
from app.router import prix as prix_router
from app.core.credentials import settings

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API pour le traitement des prix - Extraction des caractéristiques influençant le prix.",
)

@app.on_event("startup")
def startup():
    """
    Événement exécuté au démarrage de l'application.
    """
    logger.info("--- DÉMARRAGE DU SERVEUR prix-traitement ---")
    logger.info(f"Version: {settings.PROJECT_VERSION}")
    logger.info("--- SERVEUR PRÊT ---")

app.include_router(prix_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
