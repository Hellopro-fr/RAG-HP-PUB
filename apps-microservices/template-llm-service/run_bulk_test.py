import pika
import json
import time

# ===================================================================
# CONFIGURATION
# Remplacez par votre URL de connexion CloudAMQP
RABBITMQ_URL = "amqps://ezvrvpcr:epljQvbs4j0R0qJUMKWtBRNV-whMOxF7@whale.rmq.cloudamqp.com/ezvrvpcr"
# ===================================================================

def send_bulk_messages():
    """
    Se connecte à RabbitMQ, lit un fichier de tests et publie tous les messages.
    """
    try:
        print("PRODUCER: Connexion à RabbitMQ...")
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        print("PRODUCER: ✅ Connecté.")

        # Ces valeurs DOIVENT correspondre à ce que votre service écoute
        exchange_name = 'cleaned_data_exchange'
        routing_key = 'data.ready_for_templating'

        channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
        
        # Charger les messages depuis le fichier JSON
        with open('bulk_test_data.json', 'r') as f:
            test_messages = json.load(f)
        
        print(f"PRODUCER: Envoi de {len(test_messages)} messages...")

        # Publier chaque message
        for i, message in enumerate(test_messages):
            channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=json.dumps(message).encode('utf-8'),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"   -> 📤 Message {i+1}/{len(test_messages)} envoyé (URL: {message['data']['url']})")
            time.sleep(0.2) # Petite pause pour ne pas surcharger
        
        print(f"\nPRODUCER: ✅ Tous les messages ont été envoyés !")
        connection.close()

    except FileNotFoundError:
        print("PRODUCER: ❌ ERREUR: Le fichier 'bulk_test_data.json' est introuvable. Assurez-vous qu'il est à la racine du projet.")
    except Exception as e:
        print(f"PRODUCER: ❌ Une erreur est survenue : {e}")

if __name__ == '__main__':
    send_bulk_messages()