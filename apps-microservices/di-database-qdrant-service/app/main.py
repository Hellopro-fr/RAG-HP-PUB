import pika
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from di_database_qdrant_service.messaging.consumer import Consumer
from di_database_qdrant_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread

def main():
    """
    Point d'entrée principal du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    # Boucle de connexion robuste
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            logger.info("Database-Devis-Processor: Connecte a RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning("Database-Devis-Processor: En attente de RabbitMQ... %ss", i+1)
            time.sleep(1)

    if not connection:
        logger.error("Database-Devis-Processor: Impossible de se connecter, arret du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)
        
        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher)
        
        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("Database-Devis-Processor: Arret demande.")
    finally:
        if connection and not connection.is_closed:
            try:
                connection.close()
                logger.info("Database-Devis-Processor: Connexion RabbitMQ fermee.")
            except Exception:
                pass

if __name__ == '__main__':
    main()