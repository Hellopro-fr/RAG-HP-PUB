import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.router.comparator import router as ComparatorRouter
from app.core.job_manager import job_manager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Image Comparison Service",
    description="High-performance microservice for batch image similarity detection.",
    version="1.0.0"
    # Removed prefixes/custom paths. Service runs at root.
    # Nginx handles path stripping.
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
    await job_manager.connect_redis()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Service shutting down.")
    await job_manager.close_redis()

# Include router without prefix
app.include_router(ComparatorRouter, tags=["Comparator"])

@app.get("/", tags=["Health Check"])
def read_root():
    return {"status": "ok", "service": "Image Comparison API"}