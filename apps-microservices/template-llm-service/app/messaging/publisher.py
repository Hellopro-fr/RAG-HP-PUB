import pika
import json
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Publisher:
    def __init__(self, connection: pika.BlockingConnection):
        
        self.rabbitmq_connection = RabbitMQConnection()
        self.connection = connection
        self.channel = self.connection.channel()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'

        self.channel.exchange_declare(
            exchange=self.exchange_name, 
            exchange_type='topic', 
            durable=True
        )
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    def publish_message(self, message_dict: dict):
        for i in range(3):  # Essaye de se reconnecter 3 fois
            try:
                self.channel.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=self.routing_key,
                    body=json.dumps(message_dict).encode('utf-8'),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                print(f"   📤 Message classifié publié avec la clé '{self.routing_key}'.")
                break
            except (pika.exceptions.AMQPConnectionError,pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
                self.channel = self.connection.channel()
