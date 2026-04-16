import json
import logging
import aio_pika

logger = logging.getLogger(__name__)


class Publisher:
    """Async Publisher: prix-caracterisation → notification fin de traitement."""

    def __init__(self):
        self.exchange = None
        self.exchange_name = "prix_pipeline_exchange"
        self.routing_key = "prix.caracterisation.complete"

    async def setup(self, channel: aio_pika.abc.AbstractChannel):
        self.exchange = await channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        logger.info(f"✅ Prix-Caracterisation Publisher initialized: {self.exchange_name}")

    async def publish_message(self, message_dict: dict):
        if not self.exchange:
            raise RuntimeError("Publisher not initialized.")
        message = aio_pika.Message(
            body=json.dumps(message_dict).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self.exchange.publish(message, routing_key=self.routing_key)
        logger.info(f"📤 Prix-Caracterisation: notification publiée → {self.routing_key}")
