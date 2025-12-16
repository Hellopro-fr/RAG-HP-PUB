from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

from app.router import crawler
from app.core.redis import cache_service
from app.core.crawler_manager import crawler_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Crawler Service...")
    await cache_service.connect()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Crawler Service...")
    await crawler_manager.shutdown()
    await cache_service.close()

app = FastAPI(title="Crawler Service Python", version="1.0.0", lifespan=lifespan)

app.include_router(crawler.router, prefix="/crawler", tags=["crawler"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
