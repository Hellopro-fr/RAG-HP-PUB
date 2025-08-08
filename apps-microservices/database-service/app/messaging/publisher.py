import pika
import json

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le publisher avec une connexion RabbitMQ existante.
        """
        self.channel = connection.channel()
        self.exchange_name = 'inserted_data_exchange'

        # à modifier selon le flow de l'application
        self.routing_key = 'data.ready_for_webhook'

        # Déclare l'exchange où il va publier
        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )
        print("✅ Publisher initialisé.")

    def publish_message(self, message_dict: dict):
        """
        Publie un message (dictionnaire) sur le topic configuré.
        """
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        
        print(f"   📤 Output Message '{message_dict}'")
        print(f"   📤 Message traité et publié.")