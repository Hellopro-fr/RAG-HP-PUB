#!/usr/bin/env python3
"""
API de Classification de Produits
"""

import uvicorn
import sys
import os
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from app.router.classification import router as classification_router
import logging

# --- START METRICS IMPORTS ---
from starlette.middleware.wsgi import WSGIMiddleware
from common_utils.metrics.prometheus import get_metrics_app
# --- END METRICS IMPORTS ---

# --- START REDIS IMPORTS ---
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool
# --- END REDIS IMPORTS ---

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

# Lifespan context pour gérer l'initialisation et la fermeture de Redis
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application (startup/shutdown)"""
    # Startup
    logging.info("--- DÉMARRAGE API CLASSIFICATION V1 ---")
    await init_redis_pool()  # Initialiser la connexion Redis
    logging.info("✅ Redis pool initialisé")
    yield
    # Shutdown
    logging.info("--- ARRÊT API CLASSIFICATION V1 ---")
    await close_redis_pool()  # Fermer proprement la connexion Redis
    logging.info("✅ Redis pool fermé")

app = FastAPI(
    title="API Classification Produits",
    description="API pour la classification automatique de produits",
    version="1.0.0",
    lifespan=lifespan  # Associer le lifespan context
)

# --- Mount the metrics app using the WSGI adapter ---
# This adds the /metrics endpoint to your FastAPI application
metrics_app = get_metrics_app()
app.mount("/metrics", WSGIMiddleware(metrics_app))

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