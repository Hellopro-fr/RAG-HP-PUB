import asyncio
import logging
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    """Main entry point for the prix-caracterisation service."""
    logging.info("=" * 60)
    logging.info("🚀 Démarrage du service PRIX-CARACTERISATION (async)")
    logging.info("=" * 60)

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
