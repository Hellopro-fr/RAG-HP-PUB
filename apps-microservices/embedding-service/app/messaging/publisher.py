import aio_pika
import json

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        print("✅ Publisher initialisé.")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message (dictionnaire) sur le topic configuré de manière asynchrone.
        """
        collection = message_dict.get("collection", "inconnu").lower()
        exchange_name = f"{collection}_embedded_data_exchange"
        routing_key = f"data.{collection}.ready_for_insertion"

        # Déclare l'exchange (idempotent)
        exchange = await channel.declare_exchange(
            exchange_name, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        
        print(f"   📤 Message avec embedding pour la collection '{collection}' publié avec la clé '{routing_key}'.")