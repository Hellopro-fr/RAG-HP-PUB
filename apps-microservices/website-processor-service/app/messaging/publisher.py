import pika
import json
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le publisher avec une connexion RabbitMQ existante.
        """
        self.rabbitmq_connection = RabbitMQConnection()
        self.connection = connection
        self.channel = self.connection.channel()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'

        # Déclare l'exchange où il va publier
        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )
        print("✅ Publisher initialisé.")

    def update_channel(self, new_channel):
        """Met à jour le canal interne, utilisé par le Consumer après une reconnexion."""
        self.channel = new_channel
        print("   -> Canal du Publisher synchronisé avec le Consumer.")

    def publish_message(self, message_dict: dict):
        """
        Publie un message (dictionnaire) sur le topic configuré.
        Propage les exceptions pour que le Consumer les gère.
        """
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"   📤 Message traité et publié pour la prochaine étape.")