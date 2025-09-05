import pika
import json
import os

def publish_message(message_dict: dict):
    """
    Établit une connexion à RabbitMQ, publie un message, puis ferme la connexion.
    C'est une méthode robuste pour les tâches de longue durée.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("PUBLISHER ERROR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        return

    connection = None
    try:
        connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        channel = connection.channel()

        # Destination : le service d'embedding
        exchange_name = 'processed_data_exchange'
        routing_key = 'data.ready_for_embedding'

        channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)

        channel.basic_publish(
            exchange=exchange_name,
            routing_key=routing_key,
            body=json.dumps(message_dict).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        print(f"   📤 Message classifié publié avec la clé '{routing_key}'.")

    except Exception as e:
        print(f"PUBLISHER ERROR: Une erreur est survenue lors de la publication : {e}")
    
    finally:
        if connection and connection.is_open:
            connection.close()