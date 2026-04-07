import asyncio
import os
import sys
import logging
import aio_pika
from webhook_service.messaging.consumer import Consumer

logger = logging.getLogger(__name__)


def validate_environment() -> bool:
    required_vars = {
        "RABBITMQ_URL": "URL de connexion RabbitMQ",
        "KEY_WEBHOOK": "Clé secrète pour signer les webhooks",
    }

    missing_vars = [
        f"  - {var}: {desc}"
        for var, desc in required_vars.items()
        if not os.environ.get(var)
    ]

    if missing_vars:
        logger.critical("❌ Variables d'environnement manquantes:")
        for var in missing_vars:
            logger.critical(var)
        return False

    return True


async def connect_to_rabbitmq(rabbitmq_url: str, max_retries: int = 10, retry_delay: int = 1) -> aio_pika.RobustConnection:
    logger.info("🔌 Tentative de connexion à RabbitMQ...")

    for attempt in range(1, max_retries + 1):
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            logger.info("✅ webhook-service: Connexion à RabbitMQ établie avec succès")
            return connection
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"⏳ webhook-service: En attente de RabbitMQ "
                    f"(tentative {attempt}/{max_retries})... Retry dans {retry_delay}s"
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.critical(
                    f"❌ webhook-service: Impossible de se connecter à RabbitMQ "
                    f"après {max_retries} tentatives. Erreur: {e}"
                )
                raise SystemExit(1)


async def main():
    # Configuration du logging une seule fois, au point d'entrée
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("🚀 Démarrage du webhook-service (async)...")

    if not validate_environment():
        logger.critical("❌ Arrêt du service: configuration invalide")
        sys.exit(1)

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    logger.info(f"Configuration RabbitMQ: {rabbitmq_url.split('@')[1] if '@' in rabbitmq_url else 'localhost'}")

    connection = await connect_to_rabbitmq(rabbitmq_url)
    consumer = Consumer(connection)

    try:
        logger.info("🎧 webhook-service: Prêt à traiter les webhooks")
        await consumer.start_consuming()
    except asyncio.CancelledError:
        logger.info("🛑 webhook-service: Arrêt demandé")
    except Exception as e:
        logger.exception(f"❌ webhook-service: Erreur critique: {e}")
        sys.exit(1)
    finally:
        await consumer.stop()
        await connection.close()
        logger.info("✅ webhook-service: Connexion RabbitMQ fermée proprement")


if __name__ == '__main__':
    asyncio.run(main())
