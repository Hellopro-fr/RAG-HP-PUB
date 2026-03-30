import pika
import time
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from website_database_qdrant_service.messaging.consumer import Consumer
from website_database_qdrant_service.messaging.publisher import Publisher

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
            logger.info("Database-Website-Processor: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning(f"Database-Website-Processor: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        logger.error("Database-Website-Processor: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)
        
        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher)
        
        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("Database-Website-Processor: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            try:
                connection.close()
                logger.info("Database-Website-Processor: Connexion RabbitMQ fermée.")
            except Exception:
                pass

if __name__ == '__main__':
    main()