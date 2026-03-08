import aio_pika
import json

class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        self.channel = None
        self._exchanges = {}
        print("✅ Publisher initialisé.")

    async def _get_channel(self) -> aio_pika.abc.AbstractChannel:
        """Retourne un canal persistant dédié à la publication."""
        if self.channel is None or self.channel.is_closed:
            self.channel = await self.connection.channel()
            # On vide le cache des exchanges si le canal a été réouvert
            self._exchanges.clear()
        return self.channel

    async def publish_message(self, message_dict: dict):
        """
        Publie un message (dictionnaire) sur le topic configuré de manière asynchrone.
        Utilise un canal dédié pour ne pas interférer avec le canal de consommation.
        """
        collection = message_dict.get("collection", "inconnu").lower()
        exchange_name = f"{collection}_embedded_data_exchange"
        routing_key = f"data.{collection}.ready_for_insertion"

        channel = await self._get_channel()

        # Cache des exchanges pour éviter de redéclarer à chaque message (optimisation réseau)
        if exchange_name not in self._exchanges:
            exchange = await channel.declare_exchange(
                exchange_name, 
                aio_pika.ExchangeType.TOPIC, 
                durable=True
            )
            self._exchanges[exchange_name] = exchange
        else:
            exchange = self._exchanges[exchange_name]

        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=routing_key
        )
        
        print(f"    📤 Message avec embedding pour la collection '{collection}' publié avec la clé '{routing_key}'.")