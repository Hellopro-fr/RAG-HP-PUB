import pika
import time
import os
# On utilise des imports relatifs pour la robustesse dans Docker
from .messaging.consumer import Consumer
# Le publisher n'est plus une classe à instancier ici

def main():
    """
    Point d'entrée principal du service de classification LLM.
    """
    # --- CORRECTION ICI ---
    # On lit l'URL depuis les variables d'environnement.
    # Le .env et Docker Compose se chargeront de la fournir.
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)
    # --- FIN DE LA CORRECTION ---
        
    connection = None
    # ... (la boucle de connexion est parfaite) ...
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
        # --- CORRECTION ICI ---
        # On n'instancie plus le publisher, on passe juste la connexion au consumer
        consumer = Consumer(connection)
        # --- FIN DE LA CORRECTION ---
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ template-llm-service: Connexion RabbitMQ fermée.")

if __name__ == '__main__':
    main()