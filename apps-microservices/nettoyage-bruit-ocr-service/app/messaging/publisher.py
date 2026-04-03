import aio_pika
import json
import logging

logger = logging.getLogger(__name__)

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        self.metric_routing_key = 'metrics.deepseek.result'
        logger.info("Publisher initialise (vers exchange '%s').", self.exchange_name)

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de maniere asynchrone sur le canal fourni.
        """
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.routing_key
        )
        logger.debug("Message publie avec la cle '%s'.", self.routing_key)

    async def publish_metric_message(self, metric_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de metrique de maniere asynchrone sur le canal fourni.
        """
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(metric_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.metric_routing_key
        )
