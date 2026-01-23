import json
import logging
import aio_pika
from app.config import settings


class Publisher:
    """Async Publisher for sending extracted entities to normalization processor."""

    def __init__(self):
        self.exchange = None

    async def setup(self, channel: aio_pika.abc.AbstractChannel):
        """Setup the exchange on the provided channel."""
        self.exchange = await channel.declare_exchange(
            settings.OUTPUT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        logging.info(
            f"✅ LLM Extractor Publisher initialized: {settings.OUTPUT_EXCHANGE}"
        )

    async def publish_message(self, message_dict: dict):
        """Publish a message asynchronously."""
        if not self.exchange:
            raise RuntimeError("Publisher not initialized. Call setup() first.")

        try:
            message_body = json.dumps(message_dict).encode("utf-8")
            message = aio_pika.Message(
                body=message_body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.exchange.publish(
                message, routing_key=settings.OUTPUT_ROUTING_KEY
            )
            logging.debug(
                f"📤 Published to {settings.OUTPUT_EXCHANGE}/{settings.OUTPUT_ROUTING_KEY}"
            )

        except Exception as e:
            logging.error(f"⚠️ Failed to publish message: {e}")
            raise e
