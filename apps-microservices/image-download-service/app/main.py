import logging
import threading
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher
from app.core.archiver import Archiver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("image-download-service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Image-Download-Service: Starting up...")
    
    # Initialize Publisher
    app.state.publisher = Publisher()
    
    # Initialize Consumer and start in background thread
    app.state.consumer = Consumer(app.state.publisher)
    consumer_thread = threading.Thread(target=app.state.consumer.start_consuming, daemon=True)
    consumer_thread.start()
    
    yield
    
    # Shutdown
    logger.info("🛑 Image-Download-Service: Shutting down...")
    if app.state.consumer.connection:
        app.state.consumer.connection.close()

app = FastAPI(
    title="Image Download Service",
    description="Service for downloading and archiving images",
    version="1.0.0",
    lifespan=lifespan
)

archiver = Archiver()

@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for the service."""
    return {"status": "ok"}

@app.post("/archive/{domain}", tags=["Archive"], response_model=dict)
async def trigger_archive(domain: str):
    """
    Triggers creation of a .tar.gz archive for the specified domain.
    
    **Parameters:**
    - `domain`: The domain name for which to create the archive
    
    **Returns:**
    - `status`: "success" or "error"
    - `archive_path`: Path to the created archive (on success)
    - `message`: Error message (on failure)
    """
    try:
        path = await archiver.create_archive(domain)
        return {"status": "success", "archive_path": path}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Archive error: {e}")
        return {"status": "error", "message": "Internal server error during archiving"}
