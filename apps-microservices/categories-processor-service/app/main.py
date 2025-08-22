import pika
import os
import time

from categories_processor_service.messaging.consumer import Consumer
from categories_processor_service.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    # Boucle de connexion robuste
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
            print("✅ DI-Processor: Connecté à RabbitMQ.")
            break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ DI-Processor: En attente de RabbitMQ... {i+1}s")
            time.sleep(1)

    if not connection:
        print("❌ DI-Processor: Impossible de se connecter, arrêt du service.")
        exit(1)

    try:
        # 1. Créer une instance du publisher
        publisher = Publisher(connection)
        
        # 2. Créer une instance du consumer et lui passer le publisher
        consumer = Consumer(connection, publisher)
        
        # 3. Lancer l'écoute
        consumer.start_consuming()

    except KeyboardInterrupt:
        print("\n🛑 DI-Processor: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ DI-Processor: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()