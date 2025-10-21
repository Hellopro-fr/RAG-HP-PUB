import logging
from fastapi import FastAPI
from app.router.crawler import router as CrawlerRouter
from app.core.crawler_manager import crawler_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Crawler Service",
    description="An API to manage scalable web crawling jobs.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    logger.info("Crawler Service starting up.")
    # You can initialize resources here if needed

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Crawler Service shutting down. Stopping all active crawls.")
    await crawler_manager.shutdown()
    logger.info("All crawl processes terminated.")

app.include_router(CrawlerRouter, prefix="/crawler", tags=["Crawler"])

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Crawler API"}