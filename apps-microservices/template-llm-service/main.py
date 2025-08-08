import pika
import time
import os
from app.messaging.consumer import Consumer
from app.messaging.publisher import Publisher

def main():
    """
    Point d'entrée principal du service de classification LLM.
    Met en place la connexion RabbitMQ et lance le consommateur.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    connection = None

    # Boucle de connexion robuste à RabbitMQ
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