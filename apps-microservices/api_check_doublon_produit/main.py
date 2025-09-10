from fastapi import FastAPI
from app.router import check_doublon as check_doublon_router

from app.core.check_doublon import get_milvus_connection


import logging
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

description = """
API pour vérifier le doublon produit pour le projet RAG Hellopro !
"""
PROJECT_NAME__    = "API-HP-RAG"
PROJECT_VERSION__ = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    logger.info("--- Application Startup ---")
    
    # Create a list of async tasks for pre-loading resources.
    # We run the synchronous, blocking model-loading code in a separate thread
    # to avoid blocking the asyncio event loop.
    init_tasks = [
        asyncio.to_thread(get_milvus_connection),
    ]
    
    logger.info("Pre-loading models and establishing database connection...")
    # asyncio.gather runs all our initialization tasks concurrently
    await asyncio.gather(*init_tasks)
    
    logger.info("--- Startup Complete. Application is ready. ---")
    
    yield
    
    # --- Shutdown Logic ---
    # You can add cleanup code here if needed, like closing connections.
    logger.info("--- Application Shutdown ---")


app = FastAPI(
    title       = PROJECT_NAME__,
    version     = PROJECT_VERSION__,
    description = description,
    lifespan=lifespan
)

app.include_router(check_doublon_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():    
    return {"message": f"Bienvenue sur l'API {PROJECT_NAME__} v{PROJECT_VERSION__}"}

