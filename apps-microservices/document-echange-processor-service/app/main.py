import os
import asyncio
import aio_pika
import aiormq
from document_echange_processor_service.messaging.publisher import Publisher
from document_echange_processor_service.messaging.consumer import Consumer

async def main():
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        print("❌ ERREUR: La variable d'environnement RABBITMQ_URL n'est pas définie.")
        exit(1)

    print("🚀 Document-Processor: Démarrage...")
    
    os.makedirs('recovery_data', exist_ok=True)

    # Récupérer la boucle d'événements une seule fois
    loop = asyncio.get_event_loop()
    
    while True:
        try:
            connection = await aio_pika.connect_robust(
                rabbitmq_url,
                loop=loop,
                heartbeat=600 # 10 minutes, c'est bien pour des tâches longues
            )
            print("✅ Document-Processor: Connecté à RabbitMQ.")
            
            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)

                # Démarrer le consumer comme une tâche
                consumer_task = asyncio.create_task(consumer.start_consuming())

                # Attendre que le consumer (ou la connexion) se termine.
                # Cela permet de réagir si le consumer s'arrête pour une raison interne.
                await consumer_task
                
                print("⚠️ Document-Processor: Le consommateur s'est arrêté. Tentative de redémarrage...")

        except (aiormq.exceptions.AMQPConnectionError, aiormq.exceptions.ChannelInvalidStateError) as e:
            print(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Document-Processor: Arrêt demandé.")
            if 'consumer' in locals() and consumer.executor:
                consumer.executor.shutdown(wait=True, cancel_futures=True) # cancel_futures pour les processus
            break
        except Exception as e:
            print(f"❌ Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...")
            if 'consumer' in locals() and consumer.executor:
                consumer.executor.shutdown(wait=True, cancel_futures=True)
            await asyncio.sleep(10)
    
    print("✅ Document-Processor: Service arrêté.")