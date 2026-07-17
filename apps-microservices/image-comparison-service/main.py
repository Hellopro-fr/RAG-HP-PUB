import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.router.comparator import router as ComparatorRouter
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Image Comparison Service",
    description="High-performance microservice for batch image similarity detection.",
    version="1.0.0"
    # Reverted to default docs paths (served at root)
    # Nginx rewrites /comparator/openapi.json -> /openapi.json
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

@app.on_event("startup")
async def startup_event():
    logger.info("Image Comparison Service starting up.")
    await init_redis_pool()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Service shutting down.")
    await close_redis_pool()

# Include router WITHOUT prefix. Nginx handles the path stripping.
app.include_router(ComparatorRouter, tags=["Comparator"])

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Image Comparison API"}