import os
import asyncio
import aio_pika
import aiormq
from document_echange_processor_service.messaging.publisher import Publisher
from document_echange_processor_service.messaging.consumer import Consumer  # consumer adapté à aio-pika


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
    
    os.makedirs('recovery_data', exist_ok=True)

    loop = asyncio.get_event_loop()
    
    while True:
        try:
            # 1️⃣ Connexion robuste avec heartbeat élevé (10 minutes)
            connection = await aio_pika.connect_robust(
                rabbitmq_url,
                loop=loop,
                heartbeat=600
            )
            print("✅ Document-Processor: Connecté à RabbitMQ.")
            
            async with connection:
                # 2️⃣ Instanciation du publisher et du consumer asynchrone
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)

                # 3️⃣ Lancement du consumer
                await consumer.start_consuming()

                # 4️⃣ Maintenir le service vivant
                await asyncio.Future()  # bloquant jusqu'à arrêt

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
