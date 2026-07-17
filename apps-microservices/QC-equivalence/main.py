import asyncio
import logging
from app.messaging.consumer import Consumer
from app.messaging.consumer_bo import ConsumerBO
from app.messaging.publisher import Publisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    """Main entry point for the QC-equivalence service.

    Lance deux consumers indépendants en parallèle :
    - Consumer (step 6 canonical) : qc.step6.start -> publie step 7
    - ConsumerBO (façade BO) : qc.equivalence_bo.start -> aucune publication
    """
    logging.info("=" * 60)
    logging.info("🚀 Démarrage du service QC-EQUIVALENCE (async)")
    logging.info("=" * 60)

    publisher = Publisher()
    consumer = Consumer(publisher)
    consumer_bo = ConsumerBO()

    try:
        await asyncio.gather(
            consumer.start_consuming(),
            consumer_bo.start_consuming(),
        )
    except asyncio.CancelledError:
        logging.info("🛑 Task cancelled")
    except Exception as e:
        logging.error(f"❌ Unexpected error: {e}", exc_info=True)
    finally:
        await asyncio.gather(
            consumer.close(),
            consumer_bo.close(),
            return_exceptions=True,
        )
        logging.info("✅ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested via KeyboardInterrupt")
