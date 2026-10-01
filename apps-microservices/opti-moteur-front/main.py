"""Entrypoint FastAPI du microservice opti-moteur-front."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.credentials import settings
from app.core.milvus_connector import milvus
from app.core.typesense_client import typesense_client
from app.router.api_router import api_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


PROJECT_NAME__ = "OPTI-MOTEUR-FRONT"
PROJECT_VERSION__ = "1.0.0"
DESCRIPTION = """
Moteur de recherche produit HelloPro (remplacement de Milvus pour le front).

- **Backend**: Typesense (hybrid search BM25 + kNN)
- **Embeddings**: CamemBERT-large 1024 dims (identiques a Milvus prod)
- **Pertinence**: detection categorie + prefix-match + re-rank Python pondere
- **Cible**: P@5 >= 80%, latence < 200ms

Voir `apps-microservices/opti-moteur-front/README.md` pour les details.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("--- Startup %s v%s ---", PROJECT_NAME__, PROJECT_VERSION__)
    # Warm Typesense
    try:
        h = typesense_client.healthcheck()
        logger.info("Typesense healthy: %s", h)
    except Exception as e:
        logger.warning("Typesense non joignable au startup: %s", e)
    # Warm Milvus
    try:
        milvus.connect()
    except Exception as e:
        logger.warning("Milvus non joignable au startup: %s", e)
    logger.info("--- Startup complete ---")

    yield

    # Shutdown
    logger.info("--- Shutdown ---")
    try:
        milvus.disconnect()
    except Exception:
        pass


app = FastAPI(
    title=PROJECT_NAME__,
    version=PROJECT_VERSION__,
    description=DESCRIPTION,
    lifespan=lifespan,
)


@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {PROJECT_NAME__} v{PROJECT_VERSION__}"}


@app.get("/health", tags=["Monitoring"])
def health_check():
    typesense_ok = False
    milvus_ok = False
    try:
        h = typesense_client.healthcheck()
        typesense_ok = bool(h.get("ok", False))
    except Exception:
        pass
    try:
        milvus.connect()
        milvus_ok = milvus._connected
    except Exception:
        pass
    return {
        "status": "ok" if (typesense_ok and milvus_ok) else "degraded",
        "typesense": "ok" if typesense_ok else "ko",
        "milvus": "ok" if milvus_ok else "ko",
    }


app.include_router(api_router)
