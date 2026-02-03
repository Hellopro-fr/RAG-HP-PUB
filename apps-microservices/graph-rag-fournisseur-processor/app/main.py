import asyncio
import os
import logging
import aio_pika

from app.messaging.consumer import Consumer
from app.config import settings
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    """Main entry point for the Async Fournisseur Processor."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL", settings.RABBITMQ_URL)

    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    connection = None
    # Robust connection loop
    for i in range(10):
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            logging.info("✅ Graph-RAG-Fournisseur-Processor: Connected to RabbitMQ")
            break
        except Exception as e:
            logging.warning(f"⏳ Waiting for RabbitMQ... {i+1}s ({e})")
            await asyncio.sleep(1)

    if not connection:
        logging.error("❌ Could not connect to RabbitMQ")
        exit(1)

    consumer = Consumer(connection)

    try:
        await consumer.start_consuming()
    except asyncio.CancelledError:
        logging.info("🛑 Task cancelled")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}", exc_info=True)
    finally:
        await consumer.close()
        logging.info("✅ RabbitMQ connection closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested")
