import os
import asyncio
import logging
import aio_pika
import aiormq
import redis.asyncio as aioredis

from document_database_qdrant_service.messaging.consumer import Consumer
from document_database_qdrant_service.messaging.publisher import Publisher
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard import MilvusConcurrencyGuard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    logger.info("Database-Document-processor-service: Démarrage...")

    loop = asyncio.get_event_loop()
    
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
            logger.info("Database-Document-processor-service: Connecté à RabbitMQ.")
            
            async with connection:
                # --- Initialize Milvus concurrency guard ---
                redis_url = os.environ.get("REDIS_URL")
                redis_client = None
                if redis_url:
                    try:
                        redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                        await redis_client.ping()
                        logger.info("Connected to Redis for concurrency guard.")
                    except Exception as e:
                        logger.warning("Could not connect to Redis: %s — guard will use local fallback", e)
                        redis_client = None

                guard_config = GuardConfig(service_name="document-database-qdrant-service")
                concurrency_guard = MilvusConcurrencyGuard(redis_client, guard_config)
                await concurrency_guard.start_correction_loop()

                # Make guard available to processor
                import document_database_qdrant_service.core.processor as proc_module
                proc_module._concurrency_guard = concurrency_guard

                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)
                
                # Lancer le consumer, qui va démarrer ses propres tâches de fond
                await consumer.start_consuming()
                
                # Garder le service en vie pour que les tâches de fond continuent de tourner
                await asyncio.Future()

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            logger.warning(f"Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            logger.info("Database-Document-processor-service: Arrêt demandé.")
            break
        except Exception as e:
            logger.error(f"Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...", exc_info=True)
            await asyncio.sleep(10)
    
    logger.info("Database-Document-processor-service: Service arrêté.")


if __name__ == '__main__':
    asyncio.run(main())