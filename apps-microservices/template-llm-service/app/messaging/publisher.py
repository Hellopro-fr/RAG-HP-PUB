import aio_pika
import json
class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        self.metric_routing_key = 'metrics.deepseek.result'
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de manière asynchrone sur le canal fourni.
        """
        collection = message_dict.get("collection","")
        
        exchange_name = 'processed_data_exchange'
        routing_key   = 'data.ready_for_embedding'

        if collection == "document":
            page_type = message_dict.get("data",{}).get("page_type","")
            if page_type == "autre":
                exchange_name = 'document_embedded_data_exchange'
                routing_key   = 'data.document.ready_for_insertion'
            else:
                exchange_name = 'processed_data_exchange'
                routing_key   = 'data.ready_for_ocr_cleaning'

        # La déclaration de l'exchange est idempotente et rapide, on s'assure qu'elle existe.
        exchange = await channel.get_exchange(exchange_name, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        print(f"   📤 Message classifié publié avec la clé '{routing_key}'.")

    async def publish_metric_message(self, metric_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de métrique de manière asynchrone sur le canal fourni.
        """
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)
        # exchange = await channel.get_exchange(self.exchange_name, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(metric_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.metric_routing_key
        )