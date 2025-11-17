import aio_pika
import json

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        #todo à modifier si process pipeline normal
        # self.exchange_name = 'inserted_data_exchange'
        # self.routing_key = 'data.document.ready_for_insertion'

        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'

        # à modifier selon le flow de l'application
        self.exchange_name_metrics = 'processed_data_exchange'
        self.metric_routing_key = 'metrics.deepseek.result'

        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de manière asynchrone sur le canal fourni.
        """
        # routing_key = message_dict.get('routing_key', 'data.ready_for_embedding')
        routing_key = self.routing_key
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        print(f"   📤 Message traité et publié avec la clé '{routing_key}'.")

    async def publish_metric_message(self, metric_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de métrique de manière asynchrone sur le canal fourni.
        """
        exchange = await channel.get_exchange(self.exchange_name_metrics, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(metric_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.metric_routing_key
        )