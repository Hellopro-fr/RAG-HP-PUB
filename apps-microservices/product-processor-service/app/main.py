import os
import time
import logging

from common_utils.logging import setup_logging
setup_logging("product-processor-service")

import pika
from product_processor_service.messaging.consumer import Consumer
from product_processor_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logger = logging.getLogger(__name__)

def main():
    """
    Point d'entrée principal du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        logger.error("❌ Product-Processor: RABBITMQ_URL n'est pas définie.")
        exit(1)

    connection = None

    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    # Boucle de connexion robuste
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            logger.info("✅ Product-Processor: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            logger.info(f"⏳ Product-Processor: En attente de RabbitMQ... tentative {i+1}/10")
            time.sleep(1)

    if not connection:
        logger.error("❌ Product-Processor: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)
        
        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(publisher)
        
        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("🛑 Product-Processor: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logger.info("✅ Product-Processor: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()