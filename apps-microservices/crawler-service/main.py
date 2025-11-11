import logging
import asyncio
import json
from typing import Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.router.crawler import router as CrawlerRouter
from app.core.crawler_manager import crawler_manager, CRAWL_RUNNING_COUNT_KEY, CRAWL_JOB_PREFIX
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool
from app.core.config import settings
from common_utils.redis import cache_service

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Reconciliation Task ---
reconciliation_task: Optional[asyncio.Task] = None

async def reconcile_running_jobs_count():
    """
    Periodically checks the actual number of 'running' jobs in Redis and corrects
    the dedicated counter if it has drifted. This provides self-healing.
    """
    while True:
        try:
            logger.info("Starting periodic reconciliation of running jobs counter...")
            if not cache_service.redis_client:
                logger.warning("Reconciliation skipped: Redis client not available.")
                await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)
                continue

            all_job_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
            
            true_running_count = 0
            if all_job_keys:
                # Use a pipeline to fetch all jobs at once for performance
                pipe = cache_service.redis_client.pipeline()
                for key in all_job_keys:
                    pipe.get(key)
                
                all_jobs_raw = await pipe.execute()
                
                for job_raw in all_jobs_raw:
                    if job_raw:
                        try:
                            job_data = json.loads(job_raw)
                            if job_data.get("status") == "running":
                                true_running_count += 1
                        except (json.JSONDecodeError, TypeError):
                            # Ignore malformed or non-string data
                            continue

            # Get the value from the dedicated counter
            counter_value_raw = await cache_service.get_key(CRAWL_RUNNING_COUNT_KEY)
            counter_value = int(counter_value_raw) if counter_value_raw and counter_value_raw.isdigit() else 0
            
            if true_running_count != counter_value:
                logger.warning(
                    f"Running jobs counter drifted. "
                    f"Counter value: {counter_value}, Actual running jobs: {true_running_count}. "
                    f"Resetting counter."
                )
                # Forcibly set the counter to the correct value
                await cache_service.redis_client.set(CRAWL_RUNNING_COUNT_KEY, true_running_count)
            else:
                logger.info(f"Running jobs counter is consistent. Value: {true_running_count}")

        except Exception as e:
            logger.error(f"Error during running jobs reconciliation: {e}", exc_info=True)
        
        # Wait for the next interval
        await asyncio.sleep(settings.RECONCILIATION_INTERVAL_SECONDS)


app = FastAPI(
    title="Crawler Service",
    description="An API to manage scalable web crawling jobs.",
    version="1.0.0"
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
    global reconciliation_task
    logger.info("Crawler Service starting up.")
    await init_redis_pool()
    # Start the background reconciliation task
    reconciliation_task = asyncio.create_task(reconcile_running_jobs_count())
    logger.info(f"Started background task for reconciling running jobs every {settings.RECONCILIATION_INTERVAL_SECONDS} seconds.")

@app.on_event("shutdown")
async def shutdown_event():
    global reconciliation_task
    logger.info("Crawler Service shutting down. Stopping all active crawls and disconnecting from Redis.")
    
    # Cancel the reconciliation task
    if reconciliation_task:
        reconciliation_task.cancel()
        try:
            await reconciliation_task
        except asyncio.CancelledError:
            logger.info("Reconciliation task successfully cancelled.")
            
    await crawler_manager.shutdown()
    await close_redis_pool()
    logger.info("All crawl processes terminated and Redis connection closed.")

app.include_router(CrawlerRouter, prefix="/crawler", tags=["Crawler"])

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Crawler API"}