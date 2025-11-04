import os
import json
import pika
from functools import lru_cache

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")

class RabbitMQClient:
    def __init__(self, url: str):
        self.url = url
        self.connection = None
        self.channel = None

    def _connect(self):
        if not self.connection or self.connection.is_closed:
            self.connection = pika.BlockingConnection(pika.URLParameters(self.url))
            self.channel = self.connection.channel()

    async def publish_message(self, message: dict):
        self._connect()
        source = message["_source"]
        original_payload = source.get("original_payload", {})
        original_exchange = source.get("original_exchange")
        original_routing_key = source.get("original_routing_key")

        if not original_exchange or not original_routing_key:
            raise ValueError(f"Message {message['_id']} is missing original exchange or routing key.")

        self.channel.basic_publish(
            exchange=original_exchange,
            routing_key=original_routing_key,
            body=json.dumps(original_payload).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent)
        )

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()

@lru_cache()
def get_rabbitmq_client() -> RabbitMQClient:
    return RabbitMQClient(RABBITMQ_URL)