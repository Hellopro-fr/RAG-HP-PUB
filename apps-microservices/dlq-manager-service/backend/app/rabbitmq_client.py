import os
import json
import pika
from functools import lru_cache
import contextlib

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")

class RabbitMQClient:
    """
    A stateless client for publishing messages to RabbitMQ.
    Connection management is handled externally by a context manager.
    """
    def publish_message(self, channel, message: dict):
        """
        Publishes a single message using a provided channel. This is a SYNCHRONOUS method.
        """
        source = message["_source"]
        original_payload = source.get("original_payload", {})
        original_exchange = source.get("original_exchange")
        original_routing_key = source.get("original_routing_key")

        if not original_exchange or not original_routing_key:
            raise ValueError(f"Message {message['_id']} is missing original exchange or routing key.")

        channel.basic_publish(
            exchange=original_exchange,
            routing_key=original_routing_key,
            body=json.dumps(original_payload).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent)
        )

@contextlib.contextmanager
def get_rabbitmq_channel():
    """
    A context manager that provides a RabbitMQ channel and ensures the connection is closed.
    """
    connection = None
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        yield channel
    finally:
        if connection and connection.is_open:
            connection.close()

@lru_cache()
def get_rabbitmq_client() -> RabbitMQClient:
    """
    Returns a cached, stateless instance of the RabbitMQClient.
    """
    return RabbitMQClient()