import pika
import os
import time

from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service QC-generation-question1.
    Lance le consumer RabbitMQ pour traiter les messages du pipeline.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    print("=" * 60)
    print("🚀 Démarrage du service QC-GENERATION-QUESTION1")
    print("=" * 60)

    # Boucle de connexion robuste
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ QC-Question1: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ QC-Question1: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ QC-Question1: Impossible de se connecter à RabbitMQ, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)
        
        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher)
        
        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        print("\n🛑 QC-Question1: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ QC-Question1: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()
