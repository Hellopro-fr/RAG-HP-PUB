import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from infrastructure.milvus_connector import milvus_connector
from application.milvus_use_case import MilvusUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.config import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def main():
    # Start Prometheus metrics server
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    # Connect to Milvus
    milvus_connector.connect()

    # Setup collections (if not exist)
    try:
        milvus_connector.setup_collections()
    except Exception as e:
        logging.warning(f"Collections may already exist: {e}")

    # Initialize use case
    use_case = MilvusUseCase()

    logging.info("Starting Graph RAG Milvus Service...")
    await serve(use_case)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
