import logging
import logging.config
import asyncio
import json
from typing import Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.router.crawler import router as CrawlerRouter
from app.router.migration import router as MigrationRouter  # TODO: Remove after migration complete
from app.router.admin import router as AdminRouter
from app.core.crawler_manager import crawler_manager, CRAWL_RUNNING_COUNT_KEY, CRAWL_JOB_PREFIX
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool
from app.core.config import settings
from common_utils.redis import cache_service

# Configure logging — uses dictConfig to override uvicorn's default loggers
# (basicConfig is a no-op when uvicorn has already configured the root logger)
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": LOG_FORMAT,
            "datefmt": LOG_DATE_FORMAT,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
})
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
            
        except Exception as e:
            logger.error(f"Error during archive cleanup task: {e}", exc_info=True)
        
        # Wait for the next interval
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


app = FastAPI(
    title="Crawler Service",
    description="An API to manage scalable web crawling jobs.",
    version="1.0.0"
    # Reverted to default docs paths (served at root)
    # Nginx rewrites /crawler/openapi.json -> /openapi.json
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Global exception handler for Pydantic validation errors.
    This intercepts any 422 Unprocessable Entity error, logs the invalid payload
    and the specific validation error, and then returns the standard 422 response.
    """
    try:
        # exc.body is bytes
        raw_body = exc.body.decode('utf-8')
    except (AttributeError, UnicodeDecodeError):
        raw_body = "(Could not decode request body)"

    # Log the essential information for debugging
    logger.error(
        f"Validation error for {request.method} {request.url}. "
        f"Invalid payload: {raw_body}. "
        f"Error details: {exc.errors()}"
    )
    
    # Return the default 422 response structure that clients would expect
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

@app.on_event("startup")
async def startup_event():
    global reconciliation_task, archive_cleanup_task
    logger.info("Crawler Service starting up.")
    await init_redis_pool()

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

@app.on_event("shutdown")
async def shutdown_event():
    global reconciliation_task, archive_cleanup_task
    logger.info("Crawler Service shutting down. Stopping all active crawls and disconnecting from Redis.")
    
    # Cancel the reconciliation task
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
    await close_redis_pool()
    logger.info("All crawl processes terminated and Redis connection closed.")

# Include routers WITHOUT prefix. Nginx handles the path stripping.
app.include_router(CrawlerRouter, tags=["Crawler"])
app.include_router(MigrationRouter, prefix="/migration", tags=["Migration (Temporary)"])
app.include_router(AdminRouter)

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Crawler API"}