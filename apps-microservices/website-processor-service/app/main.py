import pika
import os
import time
import asyncio

from website_processor_service.messaging.consumer import Consumer
from website_processor_service.messaging.publisher import Publisher
import aio_pika

from common_utils.metrics.prometheus import start_metrics_server_in_thread

async def main():
    """
    Point d'entrée principal asynchrone du service.
    Met en place la connexion et lance les composants.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
    
    print("🚀 Website-Processor: Démarrage...")
    
    # --- Start Prometheus metrics server ---
    start_metrics_server_in_thread(port=8530)

    loop = asyncio.get_event_loop()
    try:
        connection = await aio_pika.connect_robust(rabbitmq_url, loop=loop)
        print("✅ Website-Processor: Connecté à RabbitMQ.")
        
        async with connection:
            publisher = Publisher(connection)
            consumer = Consumer(connection, publisher)
            
            await consumer.start_consuming()
            
            # Garder le service en vie
            await asyncio.Future()

    except pika.exceptions.AMQPConnectionError as e:
        print(f"❌ Website-Processor: Impossible de se connecter après plusieurs tentatives. Erreur: {e}")
        exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Website-Processor: Arrêt demandé.")
    finally:
        print("✅ Website-Processor: Service arrêté.")

if __name__ == '__main__':
    asyncio.run(main())