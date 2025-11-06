import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.router.crawler import router as CrawlerRouter
from app.core.crawler_manager import crawler_manager
from app.core.redis_service import redis_service

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

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
    logger.info("Crawler Service starting up.")
    await redis_service.connect()
    # You can initialize other resources here if needed

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Crawler Service shutting down. Stopping all active crawls and disconnecting from Redis.")
    await crawler_manager.shutdown()
    await redis_service.disconnect()
    logger.info("All crawl processes terminated and Redis connection closed.")

app.include_router(CrawlerRouter, prefix="/crawler", tags=["Crawler"])

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Crawler API"}