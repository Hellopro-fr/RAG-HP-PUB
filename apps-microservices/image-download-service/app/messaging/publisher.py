import aio_pika
import json
import logging

logger = logging.getLogger(__name__)

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        self.connection = connection
        self.exchange_name = "image_updates_exchange"
        self.routing_key = "image.downloaded"

    async def publish_update(self, message: dict):
        try:
            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.exchange_name, 
                    aio_pika.ExchangeType.TOPIC, 
                    durable=True
                )
                
                await exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(message).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    ),
                    routing_key=self.routing_key
                )
                logger.info(f"Published update for product {message.get('id_produit')} (Domain: {message.get('domain')})")
        except Exception as e:
            logger.error(f"Failed to publish update: {e}")
