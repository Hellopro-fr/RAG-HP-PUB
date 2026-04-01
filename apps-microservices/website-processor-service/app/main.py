import os
import asyncio
import logging

from common_utils.logging import setup_logging
setup_logging("website-processor-service")

import aio_pika
import aiormq

from website_processor_service.messaging.consumer import Consumer
from website_processor_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logger = logging.getLogger(__name__)

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("❌ Website-Processor: RABBITMQ_URL n'est pas définie.")
        return

    logger.info("🚀 Website-Processor: Démarrage...")

    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    loop = asyncio.get_event_loop()
    try:
        connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
        logger.info("✅ Website-Processor: Connecté à RabbitMQ.")

        async with connection:
            publisher = Publisher(connection)
            consumer = Consumer(connection, publisher)

            await consumer.start_consuming()

            # Garder le service en vie
            await asyncio.Future()

    except (aiormq.exceptions.AMQPConnectionError, aio_pika.exceptions.AMQPConnectionError) as e:
        logger.error(f"❌ Website-Processor: Impossible de se connecter après plusieurs tentatives. Erreur: {e}")
        exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Website-Processor: Arrêt demandé.")
    finally:
        logger.info("✅ Website-Processor: Service arrêté.")

if __name__ == '__main__':
    asyncio.run(main())