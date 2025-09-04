# app/messaging/publisher.py
import json
import logging
import pika
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

def publish_message(channel, exchange_name: str, routing_key: str, data: dict):
    """
    Publie un message sérialisé en JSON sur un exchange RabbitMQ.

    Args:
        channel: Le canal RabbitMQ actif.
        exchange_name: Le nom de l'exchange de destination.
        routing_key: La clé de routage du message.
        data: Le dictionnaire Python à publier.
    """
    for i in range(3):  # Essaye de se reconnecter 3 fois
        try:
            data_body = json.dumps(data).encode('utf-8')

            channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=data_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # rend le message persistant
                    content_type='application/json'
                )
            )
            logging.info(f"Message publié sur exchange '{exchange_name}' avec la clé '{routing_key}'.")
            return True
        except Exception as e:
            logging.error(f"Erreur lors de la publication du message: {e}")
            print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
            connection = RabbitMQConnection().create_connection(max_retries=10, retry_delay=5)
            channel = connection.channel()