import pika
import json

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        """
        Initialise le publisher. Il dépend d'un canal fourni par le Consumer.
        """
        self.connection = connection
        self.channel = self.connection.channel()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'

        # Déclare l'exchange où il va publier (une seule fois)
        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    def update_channel(self, new_channel):
        """Met à jour le canal interne, utilisé par le Consumer après une reconnexion."""
        self.channel = new_channel
        print("   -> Canal du Publisher synchronisé avec le Consumer.")

    def publish_message(self, message_dict: dict):
        """
        Publie un message en utilisant le canal actuel.
        Propage les exceptions (comme StreamLostError) pour que le Consumer les gère.
        """
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"   📤 Message classifié publié avec la clé '{self.routing_key}'.")