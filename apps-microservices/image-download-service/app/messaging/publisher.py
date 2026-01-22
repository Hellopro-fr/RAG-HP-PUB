import pika
import json
import logging
import os

logger = logging.getLogger(__name__)

class Publisher:
    def __init__(self):
        self.exchange_name = "image_updates_exchange"
        self.routing_key = "image.downloaded"
        self.connection = None
        self.channel = None

    def connect(self):
        """Establish connection to RabbitMQ."""
        rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
        self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)

    def publish_update(self, message: dict):
        """Publish an update message."""
        try:
            if not self.channel or self.channel.is_closed:
                self.connect()
            
            self.channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=self.routing_key,
                body=json.dumps(message).encode(),
                properties=pika.BasicProperties(delivery_mode=2)  # Persistent
            )
            logger.info(f"Published update for product {message.get('id_produit')} (Domain: {message.get('domaine')})")
        except Exception as e:
            logger.error(f"Failed to publish update: {e}")
