import json
import logging
import aio_pika

logger = logging.getLogger(__name__)


class Publisher:
    """Async Publisher: QC-generation-question2aN → Publie vers QC-generation-caracteristiques"""

    def __init__(self):
        self.exchange = None
        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.step3.start'

    async def setup(self, channel: aio_pika.abc.AbstractChannel):
        self.exchange = await channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        logger.info(f"✅ QC-Question2aN Publisher initialized: {self.exchange_name}")

    async def publish_message(self, message_dict: dict):
        if not self.exchange:
            raise RuntimeError("Publisher not initialized. Call setup() first.")
        message_body = json.dumps(message_dict).encode("utf-8")
        message = aio_pika.Message(body=message_body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        await self.exchange.publish(message, routing_key=self.routing_key)
        logger.info(f"📤 QC-Question2aN: Message publié vers {self.routing_key}")
