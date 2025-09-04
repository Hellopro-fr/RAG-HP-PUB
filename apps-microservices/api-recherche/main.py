from fastapi import FastAPI
from app.router import search as search_router
from app.router import searchws as search_ws_router
from app.core.credentials import settings

import logging
import asyncio
from contextlib import asynccontextmanager

# TODO:
# centraliser la configuration du logging dans un module dédié
from app.core.searchws import get_milvus_connection, get_embedding_model, get_reranker_model, get_openai_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        asyncio.to_thread(get_embedding_model),
        asyncio.to_thread(get_reranker_model),
        asyncio.to_thread(get_openai_client)
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
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API pour interroger Qdrant ou Milvus et générer des réponses avec des LLMs.",
    lifespan=lifespan
)

app.include_router(search_router.router)
app.include_router(search_ws_router.router)

@app.get("/", tags=["Monitoring"])
def read_root():
    return {"message": f"Bienvenue sur l'API {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"}
