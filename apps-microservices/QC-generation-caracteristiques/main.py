import pika
import os
import time

from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher

def main():
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    print("=" * 60)
    print("🚀 Démarrage du service QC-GENERATION-CARACTERISTIQUES")
    print("=" * 60)

    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ QC-Caracteristiques: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ QC-Caracteristiques: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ QC-Caracteristiques: Impossible de se connecter, arrêt.")
        exit(1)

    try:
        publisher = Publisher(connection)
        consumer = Consumer(connection, publisher)
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 QC-Caracteristiques: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ QC-Caracteristiques: Connexion fermée.")

if __name__ == '__main__':
    main()
