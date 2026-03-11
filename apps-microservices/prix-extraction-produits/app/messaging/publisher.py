import json
import logging
import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Publisher:
    """
    Async Publisher pour prix-extraction-produits.
    Publie exclusivement vers data.ready_for_embedding.
    """

    EMBED_EXCHANGE = 'processed_data_exchange'
    EMBED_ROUTING  = 'data.ready_for_embedding'

    def __init__(self):
        self._exchange = None

    async def setup(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare l'exchange sur le channel fourni."""
        self._exchange = await channel.declare_exchange(
            self.EMBED_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        logger.info(f"✅ Prix-Extraction-Produits Publisher initialized → {self.EMBED_EXCHANGE}")

    async def publish_message(self, message_dict: dict):
        """Publie un message vers data.ready_for_embedding."""
        if not self._exchange:
            raise RuntimeError("Publisher not initialized. Call setup() first.")
        body = json.dumps(message_dict, default=str).encode("utf-8")
        msg  = aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        await self._exchange.publish(msg, routing_key=self.EMBED_ROUTING)
        logger.info(f"📤 Publié vers {self.EMBED_ROUTING}")
