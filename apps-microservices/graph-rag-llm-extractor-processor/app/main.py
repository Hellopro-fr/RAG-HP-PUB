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
    """Main entry point for the LLM Extractor Processor."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL", settings.RABBITMQ_URL)
    connection = None

    start_metrics_server_in_thread(port=settings.PROMETHEUS_PORT)

    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            logging.info("✅ Graph-RAG-LLM-Extractor: Connected to RabbitMQ")
            break
        except pika.exceptions.AMQPConnectionError:
            logging.warning(f"⏳ Waiting for RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        logging.error("❌ Could not connect to RabbitMQ")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher)
        consumer.start_consuming()
    except KeyboardInterrupt:
        logging.info("🛑 Shutdown requested")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            logging.info("✅ RabbitMQ connection closed")


if __name__ == "__main__":
    main()
