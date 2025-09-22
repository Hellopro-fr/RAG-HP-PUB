import time
from fastapi import FastAPI
from app.router import search as search_router
from app.router import searchws as search_ws_router
from fastapi.middleware.cors import CORSMiddleware
from app.core.credentials import settings

import logging
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API pour interroger Qdrant ou Milvus et générer des réponses avec des LLMs.",
    # lifespan=lifespan
)


origins = [
    "https://rag.hellopro.eu",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    """
    Événement exécuté au démarrage de l'application.
    - Étape 1: Vérifie si le modèle ONNX existe. Si non, le convertit.
    - Étape 2: Pré-charge tous les modèles en mémoire pour une latence minimale.
    """
    logger.info("--- DÉMARRAGE DU SERVEUR : PRÉPARATION DES MODÈLES ---")
    logger.info("Pré-chargement du modèle de reranking ONNX...")
    logger.info("--- MODÈLES PRÊTS : LE SERVEUR EST OPÉRATIONNEL ---")

app.include_router(search_router.router)
app.include_router(search_ws_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
