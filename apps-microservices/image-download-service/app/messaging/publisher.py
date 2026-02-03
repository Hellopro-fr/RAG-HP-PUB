import aio_pika
import json

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        self.exchange_name = "image_updates_exchange"
        self.routing_key = "image.downloaded"
        print("✅ Publisher initialisé.")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message (dictionnaire) sur l'exchange configuré de manière asynchrone.
        """
        domain = message_dict.get("domaine", "unknown")
        product_id = message_dict.get("id_produit", "unknown")

        # Déclare l'exchange (idempotent)
        exchange = await channel.declare_exchange(
            self.exchange_name, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.routing_key
        )
        
        print(f"   📤 Image update publié pour le produit '{product_id}' (domaine: {domain}) avec la clé '{self.routing_key}'.")
