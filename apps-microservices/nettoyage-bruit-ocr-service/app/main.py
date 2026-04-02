import os
import asyncio
import logging
import aio_pika
import aiormq

from common_utils.logging import setup_logging
from nettoyage_bruit_ocr_service.messaging.publisher import Publisher
from nettoyage_bruit_ocr_service.messaging.consumer import Consumer

setup_logging("nettoyage-bruit-ocr-service")
logger = logging.getLogger(__name__)


async def main():
    """
    Point d'entree principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("La variable d'environnement RABBITMQ_URL n'est pas definie.")
        exit(1)

    logger.info("Nettoyage-bruit-ocr-service: Demarrage...")

    while True:
        try:
            connection = await aio_pika.connect_robust(
                rabbitmq_url,
                heartbeat=3600,
                connection_timeout=7200
            )
            logger.info("Nettoyage-bruit-ocr-service: Connecte a RabbitMQ.")

            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)

                await consumer.start_consuming()

                # Keep the service alive
                await asyncio.Future()

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            logger.warning("Erreur de connexion RabbitMQ: %s. Tentative de reconnexion dans 10 secondes...", e)
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            logger.info("Nettoyage-bruit-ocr-service: Arret demande.")
            break
        except Exception as e:
            logger.error("Erreur inattendue dans main: %s. Redemarrage dans 10 secondes...", e, exc_info=True)
            await asyncio.sleep(10)

    logger.info("Nettoyage-bruit-ocr-service: Service arrete.")


if __name__ == '__main__':
    asyncio.run(main())
