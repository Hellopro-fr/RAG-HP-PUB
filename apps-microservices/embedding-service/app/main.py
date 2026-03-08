import os
import asyncio
import aio_pika

# Importer les modules locaux
from embedding_service.messaging.consumer import Consumer
from embedding_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    
    print("🚀 Embedding-Service: Démarrage...")
    
    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    while True:
        try:
            connection = await aio_pika.connect_robust(rabbitmq_url)
            print("✅ Embedding-Service: Connecté à RabbitMQ.")
            
            async with connection:
                publisher = Publisher(connection)
                consumer = Consumer(connection, publisher)
                
                # Lancer le consumer. Avec queue.iterator(), cette coroutine
                # reste active tant que des messages sont consommés.
                await consumer.start_consuming()

        except aio_pika.exceptions.AMQPConnectionError as e:
            print(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Embedding-Service: Arrêt demandé.")
            break
        except Exception as e:
            print(f"❌ Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...")
            await asyncio.sleep(10)
    
    print("✅ Embedding-Service: Service arrêté.")

if __name__ == '__main__':
    asyncio.run(main())