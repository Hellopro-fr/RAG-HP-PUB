import logging
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher
from app.core.archiver import Archiver
import os
import aio_pika

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
    
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    loop = asyncio.get_running_loop()
    
    connection = None
    while not connection:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
            logger.info("✅ Connected to RabbitMQ.")
        except Exception as e:
             logger.warning(f"⏳ Waiting for RabbitMQ: {e}")
             await asyncio.sleep(5)

    app.state.rabbitmq_connection = connection
    
    # Initialize Publisher
    app.state.publisher = Publisher(connection)
    
    # Initialize Consumer
    app.state.consumer = Consumer(connection, app.state.publisher)
    asyncio.create_task(app.state.consumer.start_consuming())
    
    yield
    
    # Shutdown
    logger.info("🛑 Image-Download-Service: Shutting down...")
    if app.state.rabbitmq_connection:
        await app.state.rabbitmq_connection.close()

app = FastAPI(title="Image Download Service", lifespan=lifespan)

archiver = Archiver()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/archive/{domain}")
async def trigger_archive(domain: str):
    """
    Triggers creation of a .tar.gz archive for the specified domain.
    """
    try:
        path = await archiver.create_archive(domain)
        return {"status": "success", "archive_path": path}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Archive error: {e}")
        return {"status": "error", "message": "Internal server error during archiving"}
