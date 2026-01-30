from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging
import asyncio
from typing import Optional

from app.router import crawler
from app.core.redis import cache_service
from app.core.crawler_manager import crawler_manager
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Reconciliation Task ---
reconciliation_task: Optional[asyncio.Task] = None
archive_cleanup_task: Optional[asyncio.Task] = None

async def reconcile_running_jobs_count():
    """
    Periodically checks the actual number of 'running' jobs in Redis and corrects
    the dedicated counter if it has drifted. This provides self-healing.
    Also cleans up stale jobs that have stopped sending heartbeats.
    """
    while True:
        try:
            if not cache_service.redis_client:
                logger.warning("Reconciliation skipped: Redis client not available.")
                await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)
                continue

            await crawler_manager.reconcile_jobs()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during running jobs reconciliation: {e}", exc_info=True)
        
        # Wait for the next interval
        await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)

async def scheduled_archive_cleanup():
    """
    Periodically cleans up old archive files to manage disk usage.
    Runs every hour and deletes files older than 24 hours.
    """
    CLEANUP_INTERVAL_SECONDS = 3600  # Run every hour
    MAX_AGE_HOURS = 24  # Trigger deletion for files > 24h old

    while True:
        try:
            # Initial delay to stagger from startup
            await asyncio.sleep(60)
            
            await crawler_manager.cleanup_archives(max_age_hours=MAX_AGE_HOURS)
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error during archive cleanup task: {e}", exc_info=True)
        
        # Wait for the next interval
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global reconciliation_task, archive_cleanup_task
    
    # Startup
    logger.info("Starting up Crawler Service...")
    await cache_service.connect()
    
    # Run an immediate reconciliation to clean up any stale jobs from previous runs
    try:
        logger.info("Running initial job reconciliation...")
        await crawler_manager.reconcile_jobs()
    except Exception as e:
        logger.error(f"Initial reconciliation failed: {e}", exc_info=True)

    # Start the background reconciliation task
    reconciliation_task = asyncio.create_task(reconcile_running_jobs_count())
    logger.info(f"Started background task for reconciling running jobs every {settings.RECONCILIATION_INTERVAL_SECONDS} seconds.")

    # Start the background archive cleanup task
    archive_cleanup_task = asyncio.create_task(scheduled_archive_cleanup())
    logger.info("Started background task for archive cleanup (every 1 hour).")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Crawler Service...")
    
    # Cancel tasks
    if reconciliation_task:
        reconciliation_task.cancel()
        try:
            await reconciliation_task
        except asyncio.CancelledError:
            logger.info("Reconciliation task successfully cancelled.")
            
    if archive_cleanup_task:
        archive_cleanup_task.cancel()
        try:
            await archive_cleanup_task
        except asyncio.CancelledError:
            logger.info("Archive cleanup task successfully cancelled.")

    await crawler_manager.shutdown()
    await cache_service.close()

app = FastAPI(title="Crawler Service Python", version="1.0.0", lifespan=lifespan)

app.include_router(crawler.router, prefix="/crawler", tags=["crawler"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
