import pika
import os
import time

from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service QC-generation-question2aN.
    Lance le consumer RabbitMQ pour traiter les messages du pipeline.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    print("=" * 60)
    print("🚀 Démarrage du service QC-GENERATION-QUESTION2AN")
    print("=" * 60)

    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ QC-Question2aN: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ QC-Question2aN: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ QC-Question2aN: Impossible de se connecter à RabbitMQ, arrêt du service.")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher)
        consumer.start_consuming()

    except KeyboardInterrupt:
        print("\n🛑 QC-Question2aN: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ QC-Question2aN: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()
