import logging
import pika
import time
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

import redis as sync_redis
from echange_database_qdrant_service.messaging.consumer import Consumer
from echange_database_qdrant_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread
from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.milvus_concurrency_guard_sync import MilvusConcurrencyGuardSync

def main():
    """
    Point d'entrée principal du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    # --- Initialize Milvus concurrency guard ---
    redis_url = os.environ.get("REDIS_URL")
    redis_client = None
    if redis_url:
        try:
            redis_client = sync_redis.from_url(redis_url, decode_responses=True)
            redis_client.ping()
            logger.info("Connected to Redis for concurrency guard.")
        except Exception as e:
            logger.warning("Could not connect to Redis: %s — guard will use local fallback", e)
            redis_client = None

    guard_config = GuardConfig(service_name="echange-database-qdrant-service")
    concurrency_guard = MilvusConcurrencyGuardSync(redis_client, guard_config)

    # Make guard available to processor module
    import echange_database_qdrant_service.core.processor as proc_module
    proc_module._concurrency_guard = concurrency_guard

    # Boucle de connexion robuste
    for i in range(10):
        try:
            params = pika.URLParameters(rabbitmq_url)
            params.heartbeat = 600
            params.blocked_connection_timeout = 300
            connection = pika.BlockingConnection(params)
            logger.info("Database-Echange-Processor: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning(f"Database-Echange-Processor: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        logger.error("Database-Echange-Processor: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)

        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher)

        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("Database-Echange-Processor: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            try:
                connection.close()
                logger.info("Database-Echange-Processor: Connexion RabbitMQ fermée.")
            except Exception:
                pass

if __name__ == '__main__':
    main()