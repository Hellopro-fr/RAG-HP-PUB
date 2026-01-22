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
    
    Returns:
        bool: True if message was published successfully, False otherwise.
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
            logging.error(f"Erreur lors de la publication du message (tentative {i+1}/3): {e}")
            print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion ({i+1}/3)...")
            try:
                connection = RabbitMQConnection().create_connection(max_retries=3, retry_delay=2)
                if connection:
                    channel = connection.channel()
                else:
                    logging.error("Impossible de créer une nouvelle connexion RabbitMQ")
            except Exception as conn_error:
                logging.error(f"Erreur lors de la reconnexion: {conn_error}")
    
    # All retries failed
    logging.error(f"Échec de la publication du message après 3 tentatives sur exchange '{exchange_name}'")
    return False