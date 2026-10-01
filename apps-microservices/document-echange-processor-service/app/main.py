import os
import asyncio
import logging
import signal

from common_utils.logging import setup_logging
setup_logging("document-echange-processor-service")

import aio_pika
import aiormq
from document_echange_processor_service.messaging.publisher import Publisher
from document_echange_processor_service.messaging.consumer import Consumer

logger = logging.getLogger(__name__)

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """

    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        return

    logger.info("🚀 Document-processor-service: Démarrage...")

    # Graceful shutdown: catch SIGTERM (docker stop / recreate) + SIGINT so an
    # in-flight batch can drain instead of being SIGKILL'd (exit 137) mid-way,
    # which — because messages are ACK'd early — would silently lose that batch.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # signal handlers unavailable (e.g. Windows) -> KeyboardInterrupt fallback

    while not stop_event.is_set():
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            logger.info("✅ Document-processor-service: Connecté à RabbitMQ.")

            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)

                # Lancer le consumer, qui va démarrer ses propres tâches de fond
                await consumer.start_consuming(stop_event)

                # Rester en vie jusqu'à une demande d'arrêt, puis drainer.
                await stop_event.wait()
                logger.info("🛑 Signal d'arrêt reçu — drain du batch en cours...")
                await consumer.stop()
                return

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            if stop_event.is_set():
                return
            logger.warning(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Document-processor-service: Arrêt demandé.")
            break
        except Exception as e:
            if stop_event.is_set():
                return
            logger.error(f"❌ Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...")
            await asyncio.sleep(10)
    


if __name__ == '__main__':
    asyncio.run(main())