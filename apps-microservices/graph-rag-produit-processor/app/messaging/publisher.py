import pika
import json
import logging
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

from app.config import settings


class Publisher:
    """Publisher for sending processed products to the next processor in the pipeline."""

    def __init__(self, connection: pika.BlockingConnection):
        self.rabbitmq_connection = RabbitMQConnection()
        self.connection = connection
        self.channel = connection.channel()
        self.exchange_name = settings.OUTPUT_EXCHANGE
        self.routing_key = settings.OUTPUT_ROUTING_KEY

        # Declare the output exchange
        self.channel.exchange_declare(
            exchange=self.exchange_name, exchange_type="topic", durable=True
        )
        logging.info(f"✅ Publisher initialized for exchange: {self.exchange_name}")

    def publish_message(self, message_dict: dict):
        """Publish a message to the output exchange."""
        for i in range(3):
            try:
                self.channel.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=self.routing_key,
                    body=json.dumps(message_dict).encode("utf-8"),
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                logging.info(
                    f"📤 Message published to {self.exchange_name}/{self.routing_key}"
                )
                break
            except (
                pika.exceptions.AMQPConnectionError,
                pika.exceptions.ChannelClosedByBroker,
            ) as e:
                logging.warning(f"⚠️ Connection lost: {e}, attempting to reconnect...")
                self.connection = self.rabbitmq_connection.create_connection(
                    max_retries=10, retry_delay=5
                )
                self.channel = self.connection.channel()
