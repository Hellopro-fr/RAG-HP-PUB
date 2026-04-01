import pika
import json
import logging
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

logger = logging.getLogger(__name__)

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
        logger.info("✅ Publisher initialisé.")

    def publish_message(self, message_dict: dict):
        for i in range(3):  # Essaye de se reconnecter 3 fois
            try:
                """
                Publie un message (dictionnaire) sur le topic configuré.
                """
                id_demande = message_dict.get("lead_id", "ID DI inconnu")
                self.channel.basic_publish(
                    exchange=self.exchange_name,
                    routing_key=self.routing_key,
                    body=json.dumps(message_dict).encode('utf-8'),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                logger.info(f"   📤 Message pour '{id_demande}' traité et publié pour embedding.")
                break  # Si la publication réussit, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError,pika.exceptions.ChannelClosedByBroker) as e:
                logger.warning(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
                self.channel = self.connection.channel()