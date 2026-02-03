import pika
import json
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Publisher:
    """Publisher: QC-generation-caracteristiques → Publie vers QC-generation-valeurs"""
    def __init__(self, connection: pika.BlockingConnection):
        self.rabbitmq_connection = RabbitMQConnection()
        self.connection = connection
        self.channel = connection.channel()
        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.step4.start'

        try:
            self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        except pika.exceptions.ChannelClosedByBroker:
            self.channel = connection.channel()
            self.channel.exchange_declare(exchange=self.exchange_name, passive=True)
        
        print("✅ QC-Caracteristiques Publisher initialisé.")
    
    def _ensure_channel_open(self):
        """Vérifie que le channel est ouvert, sinon reconnecte."""
        try:
            if self.channel.is_closed or not self.connection or self.connection.is_closed:
                print("⚠️ Publisher: Channel/Connection fermé, reconnexion...")
                self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
                self.channel = self.connection.channel()
                self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
                return self.channel
            return self.channel
        except:
            print("⚠️ Publisher: Erreur lors de la vérification, reconnexion...")
            self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
            self.channel = self.connection.channel()
            self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
            return self.channel

    def publish_message(self, message_dict: dict):
        """Publie un message vers l'étape suivante du pipeline."""
        for i in range(3):
            try:
                active_ch = self._ensure_channel_open()
                
                active_ch.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=self.routing_key,
                    body=json.dumps(message_dict).encode('utf-8'),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                print(f"   📤 QC-Caracteristiques: Message publié vers {self.routing_key}")
                break
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker, 
                    pika.exceptions.StreamLostError, pika.exceptions.ChannelWrongStateError) as e:
                print(f"⚠️ Connexion perdue: {e}")
                self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
                self.channel = self.connection.channel()
