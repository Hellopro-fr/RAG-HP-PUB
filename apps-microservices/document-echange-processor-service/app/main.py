import aio_pika
import os
import asyncio
import aiormq

from document_echange_processor_service.messaging.consumer import Consumer
from document_echange_processor_service.messaging.publisher import Publisher

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 Document-Processor: Démarrage...")
    
    # Créer le répertoire de récupération s'il n'existe pas
    os.makedirs('recovery_data', exist_ok=True)

    loop = asyncio.get_event_loop()
    
    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
            print("✅ Document-Processor: Connecté à RabbitMQ.")
            
            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)
                
                # Lancer le consumer, qui va démarrer ses propres tâches de fond
                await consumer.start_consuming()
                
                # Garder le service en vie pour que les tâches de fond continuent de tourner
                await asyncio.Future()

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            print(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Document-Processor: Arrêt demandé.")
            break
        except Exception as e:
            print(f"❌ Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...")
            await asyncio.sleep(10)
    
    print("✅ Document-Processor: Service arrêté.")


if __name__ == '__main__':
    asyncio.run(main())