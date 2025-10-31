#!/usr/bin/env python3
"""
API de Classification de Produits
"""

import uvicorn
import sys
import os
import socket
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from app.router.classification import router as classification_router
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Obtenir l'ID unique du replica (hostname du conteneur)
REPLICA_ID = socket.gethostname()

# Debug: Test d'import de common_utils
logging.info(f"Python path: {sys.path}")
try:
    import common_utils
    logging.info(f"✅ common_utils importé avec succès depuis: {common_utils.__file__}")
    from common_utils.grpc_clients import llm_client
    logging.info("✅ llm_client importé avec succès")
except ImportError as e:
    logging.error(f"❌ Erreur import common_utils: {e}")

app = FastAPI(
    title="API Classification Produits",
    description="API pour la classification automatique de produits",
    version="1.0.0"
)

# Middleware pour ajouter l'ID du replica dans les headers de réponse
@app.middleware("http")
async def add_replica_id_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Replica-ID"] = REPLICA_ID
    return response

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    logging.info(f"🚀 Démarrage du replica: {REPLICA_ID}")
    from api_recherche_lib.core.recherche import batching_manager
    batching_manager.startup()

@app.on_event("shutdown")
def shutdown_event():
    from api_recherche_lib.core.recherche import batching_manager
    batching_manager.embedding_batch_processor.shutdown()
    batching_manager.reranking_batch_processor.shutdown()

# Inclusion des routers
app.include_router(
    classification_router,
    prefix="/classification",
    tags=["Classification"]
)

@app.get("/")
async def root():
    return {"message": "API Classification Produits v1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )