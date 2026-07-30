import asyncio
import logging

from app.messaging.consumer import Consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


async def main():
    """Point d'entree du service QC-fabricant-reference (etape PSI 16).

    Consomme qc.fabricant_reference.start et extrait marque + reference des produits
    d'une categorie via le prompt 133. Etape terminale : aucune publication aval.
    """
    logging.info("=" * 60)
    logging.info("🚀 Demarrage du service QC-FABRICANT-REFERENCE (async)")
    logging.info("=" * 60)

    consumer = Consumer()

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
