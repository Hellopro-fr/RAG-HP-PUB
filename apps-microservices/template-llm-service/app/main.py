import pika
import time
import os
import asyncio

# On utilise des imports absolus basés sur le nom du module qui sera dans le PYTHONPATH
from template_llm_service.messaging.consumer import Consumer
from template_llm_service.messaging.publisher import Publisher
import aio_pika

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Établit la connexion et lance les composants RabbitMQ.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 template-llm-service: Démarrage...")
    
    # Créer le répertoire de récupération s'il n'existe pas
    os.makedirs('recovery_data', exist_ok=True)

    loop = asyncio.get_event_loop()
    try:
        connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
        print("✅ template-llm-service: Connecté à RabbitMQ.")
        
        async with connection:
            publisher = Publisher(connection)
            consumer = Consumer(connection, publisher)
            
            # Lancer le consumer, qui va démarrer ses propres tâches de fond
            await consumer.start_consuming()
            
            # Garder le service en vie pour que les tâches de fond continuent de tourner
            await asyncio.Future()

    except pika.exceptions.AMQPConnectionError as e:
        print(f"❌ template-llm-service: Impossible de se connecter après plusieurs tentatives. Erreur: {e}")
        exit(1)
    except KeyboardInterrupt:
        print("\n🛑 template-llm-service: Arrêt demandé.")
    finally:
        print("✅ template-llm-service: Service arrêté.")

if __name__ == '__main__':
    asyncio.run(main())