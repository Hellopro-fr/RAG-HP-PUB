from fastapi import FastAPI
from app.router.api_router import api_router

import os
import logging
import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard
from common_utils.metrics.prometheus import start_metrics_server_in_thread

from app.core.api_rest_milvus import get_milvus_connection


logger = logging.getLogger(__name__)

description = """
API REST MILVUS !
"""
PROJECT_NAME__    = "API-HP-RAG REST MILVUS"
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

    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    # --- Initialize Milvus concurrency guard ---
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            await redis_client.ping()
            logger.info("Connected to Redis for concurrency guard.")
        except Exception as e:
            logger.warning("Could not connect to Redis: %s — guard will use local fallback", e)
            redis_client = None

    guard_config = GuardConfig(service_name="api-rest-milvus")
    app.state.concurrency_guard = MilvusConcurrencyGuard(redis_client, guard_config)
    await app.state.concurrency_guard.start_correction_loop()

    # Expose Redis client for routers that need direct access (e.g. stats cache)
    app.state.redis_client = redis_client

    # Pre-warm global-stats cache in background so first user after container restart
    # does not pay the full 180s scan cost
    if redis_client is not None:
        from app.router.stats import prewarm_cache
        asyncio.create_task(prewarm_cache(app.state.concurrency_guard, redis_client))

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

@app.get("/", tags=["Monitoring"])
def read_root():    
    return {"message": f"Bienvenue sur l'API {PROJECT_NAME__} v{PROJECT_VERSION__}"}

@app.get("/health", tags=["Monitoring"])
def health_check():
    return {"status": "ok"}

app.include_router(api_router)

