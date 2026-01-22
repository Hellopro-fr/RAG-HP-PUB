import logging
import threading
from fastapi import FastAPI
from fastapi.responses import FileResponse
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
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Image Download Service",
            "description": "Operations for archiving and downloading images by domain",
        }
    ]
)

archiver = Archiver()

@app.get("/health", tags=["Image Download Service"])
def health_check():
    """Health check endpoint for the service."""
    return {"status": "ok"}

@app.post("/archive/{domain}", tags=["Image Download Service"])
async def trigger_archive(domain: str):
    """
    Triggers creation of a .tar.gz archive for the specified domain and returns it as a downloadable file.
    
    **Parameters:**
    - `domain`: The domain name for which to create the archive
    
    **Returns:**
    - The archive file (.tar.gz) as a downloadable attachment
    """
    try:
        path = await archiver.create_archive(domain)
        
        # Return the archive as a downloadable file
        return FileResponse(
            path,
            media_type="application/gzip",
            filename=f"{domain}.tar.gz",
            headers={"Content-Disposition": f"attachment; filename=\"{domain}.tar.gz\""}
        )
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Archive error: {e}")
        return {"status": "error", "message": "Internal server error during archiving"}
