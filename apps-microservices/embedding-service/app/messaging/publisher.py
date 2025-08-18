import pika
import json

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le publisher avec une connexion RabbitMQ existante.
        """
        self.channel = connection.channel(
        print("✅ Publisher initialisé.")

    def publish_message(self, message_dict: dict):
        """
        Publie un message (dictionnaire) sur le topic configuré.
        """
        collection = message_dict.get("collection", "inconnu")
        collection = collection.lower()
        
        self.exchange_name = f"{collection}_embedded_data_exchange"
        self.routing_key = f"data.{collection}.ready_for_insertion"

        # Déclare l'exchange où il va publier
        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )

        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        print(f"   📤 routing_key : '{self.routing_key}'")
        print(f"   📤 Output Message post embedding '{message_dict}'")
        print(f"   📤 Message traité et publié post embedding.")