import time
from fastapi import FastAPI
from app.router import chat as llm_chat_router
from app.core.credentials import settings

import logging
import asyncio
from contextlib import asynccontextmanager

# TODO:
# centraliser la configuration du logging dans un module dédié
# from app.core.searchws import get_milvus_connection, get_embedding_model, get_openai_client, prepare_onnx_model, get_reranker_onnx_model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API pour interroger Qdrant ou Milvus et générer des réponses avec des LLMs.",
    # lifespan=lifespan
)

@app.on_event("startup")
def startup():
    """
    Événement exécuté au démarrage de l'application.
    - Étape 1: Vérifie si le modèle ONNX existe. Si non, le convertit.
    - Étape 2: Pré-charge tous les modèles en mémoire pour une latence minimale.
    """
    logger.info("--- DÉMARRAGE DU SERVEUR : PRÉPARATION DES MODÈLES ---")
    
    # Étape 1: S'assure que le modèle ONNX existe sur le disque.
    # Cette opération est longue UNIQUEMENT au tout premier lancement.
    # prepare_onnx_model()
    
    logger.info("Pré-chargement du modèle de reranking ONNX...")
    # get_reranker_onnx_model()
    
    logger.info("--- MODÈLES PRÊTS : LE SERVEUR EST OPÉRATIONNEL ---")

app.include_router(llm_chat_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
