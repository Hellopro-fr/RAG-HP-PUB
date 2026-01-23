import asyncio
import logging
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher
from app.config import settings
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    """Main entry point for the Async Product Processor."""
    # start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    publisher = Publisher()
    consumer = Consumer(publisher)

    try:
        await consumer.start_consuming()
    except asyncio.CancelledError:
        logging.info("🛑 Task cancelled")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}", exc_info=True)
    finally:
        await consumer.close()
        logging.info("✅ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested via KeyboardInterrupt")
