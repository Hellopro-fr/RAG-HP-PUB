import pika
import os
import time
import logging

from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher
from app.config import settings
from common_utils.metrics.prometheus import start_metrics_server_in_thread


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True
)

def main():

    """
    Main entry point for the Graph RAG Product Processor.
    Sets up RabbitMQ connection and starts consuming messages.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", settings.RABBITMQ_URL)
    connection = None

    # Start Prometheus metrics server
    # start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    logging.info("✅ Graph-RAG-Produit-Processor: Starting up")
    # Robust connection loop
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            logging.info("✅ Graph-RAG-Produit-Processor: Connected to RabbitMQ")
            break
        except pika.exceptions.AMQPConnectionError:
            logging.warning(f"⏳ Waiting for RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        logging.error("❌ Could not connect to RabbitMQ, shutting down")
        exit(1)

    try:
        # Initialize publisher
        publisher = Publisher(connection)

        # Initialize consumer with publisher
        consumer = Consumer(connection, publisher)

        # Start consuming
        consumer.start_consuming()

    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logging.info("✅ RabbitMQ connection closed")


if __name__ == "__main__":
    main()
