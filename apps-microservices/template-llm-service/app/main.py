import pika
import time
import os

# On utilise des imports absolus basés sur le nom du module qui sera dans le PYTHONPATH
from template_llm_service.messaging.consumer import Consumer
from template_llm_service.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service.
    Charge le modèle LLM et lance les composants RabbitMQ.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 template-llm-service: Démarrage...")

    connection = None
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ template-llm-service: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ template-llm-service: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ template-llm-service: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher)
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ template-llm-service: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()