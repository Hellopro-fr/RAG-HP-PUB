import pika
import json

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le publisher avec une connexion RabbitMQ existante.
        """
        self.channel = connection.channel()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'

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
        id_demande = message_dict.get("id_demande", "ID DI inconnu")
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"   📤 Message pour '{id_demande}' traité et publié pour embedding.")