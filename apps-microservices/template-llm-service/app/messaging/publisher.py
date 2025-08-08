import pika
import json

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        self.channel = connection.channel()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding' # La clé exacte pour l'étape suivante.

        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")
    def publish_message(self, message_dict: dict):
        self.channel.basic_publish(
            exchange=self.exchange_name,
            routing_key=self.routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"   📤 Message classifié publié avec la clé '{self.routing_key}'.")