import json
import logging
import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class Publisher:
    """Async Publisher: QC-generation-question1 → Publie vers QC-generation-question2aN"""

    def __init__(self):
        self.exchange = None
        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.step2.start'

    async def setup(self, channel: aio_pika.abc.AbstractChannel):
        """Setup l'exchange sur le channel fourni."""
        self.exchange = await channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        logger.info(f"✅ QC-Question1 Publisher initialized: {self.exchange_name}")

    async def publish_message(self, message_dict: dict):
        """Publie un message vers l'étape suivante du pipeline."""
        if not self.exchange:
            raise RuntimeError("Publisher not initialized. Call setup() first.")

        try:
            message_body = json.dumps(message_dict).encode("utf-8")
            message = aio_pika.Message(
                body=message_body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.exchange.publish(message, routing_key=self.routing_key)
            logger.info(f"📤 QC-Question1: Message publié vers {self.routing_key}")

        except Exception as e:
            logger.error(f"⚠️ Échec publication message: {e}")
            raise e
