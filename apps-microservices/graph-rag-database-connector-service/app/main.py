import asyncio
import logging
import uvloop

from infrastructure.grpc_server import serve
from application.graph_database_use_case import GraphDatabaseUseCase
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    # Start Prometheus metrics server
    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    # Initialize use case
    use_case = GraphDatabaseUseCase()

    # Apply unique constraints and indexes at startup to prevent race conditions
    logging.info("Applying Neo4j constraints and indexes...")
    try:
        constraints, indexes = use_case.setup_schema()
        logging.info(
            f"✅ Applied {len(constraints)} constraints and {len(indexes)} indexes"
        )
    except Exception as e:
        logging.error(f"⚠️ Failed to apply constraints/indexes: {e}")

    logging.info("Starting Graph RAG Database Connector Service...")
    await serve(use_case)


if __name__ == "__main__":
    uvloop.install()
    asyncio.run(main())
