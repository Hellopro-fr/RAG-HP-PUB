import time
from fastapi import FastAPI, Request
from app.router import search as search_router
from app.router import searchws as search_ws_router
from fastapi.middleware.cors import CORSMiddleware
from app.core.credentials import settings

import logging
import asyncio
from contextlib import asynccontextmanager
import os

log_format = "%(asctime)s - %(levelname)s - [WORKER_PID:%(process)d] - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Requête reçue: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Réponse envoyée avec le statut: {response.status_code}")
    return response

@app.on_event("startup")
def startup():
    """
    Événement exécuté au démarrage de l'application.
    - Étape 1: Vérifie si le modèle ONNX existe. Si non, le convertit.
    - Étape 2: Pré-charge tous les modèles en mémoire pour une latence minimale.
    """
    logger.info("--- DÉMARRAGE DU SERVEUR : PRÉPARATION DES MODÈLES ---")
    from app.core.recherche import batching_manager
    batching_manager.startup()
    logger.info("Pré-chargement du modèle de reranking ONNX...")
    logger.info("--- MODÈLES PRÊTS : LE SERVEUR EST OPÉRATIONNEL ---")

@app.on_event("shutdown")
def shutdown_event():
    logger.info("--- SHUTTING DOWN : STOPPING BATCH PROCESSORS ---")
    from app.core.recherche import batching_manager
    batching_manager.embedding_batch_processor.shutdown()
    batching_manager.reranking_batch_processor.shutdown()
    logger.info("--- BATCH PROCESSORS STOPPED ---")

app.include_router(search_router.router)
app.include_router(search_ws_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
