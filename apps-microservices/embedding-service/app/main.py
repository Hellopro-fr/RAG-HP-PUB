import os
import asyncio
import logging
import aio_pika

# Importer les modules locaux
from embedding_service.messaging.consumer import Consumer
from embedding_service.messaging.publisher import Publisher
from common_utils.metrics.prometheus import start_metrics_server_in_thread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("embedding-service")

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
                
                # Lancer le consumer. start_consuming() bloque jusqu'à ce que
                # le canal soit fermé, puis lève AMQPConnectionError pour
                # déclencher la reconnexion.
                await consumer.start_consuming()

        except aio_pika.exceptions.AMQPConnectionError as e:
            logger.warning(f"🔴 Connexion RabbitMQ perdue: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n🛑 Embedding-Service: Arrêt demandé.")
            break
        except Exception as e:
            logger.error(f"❌ Erreur inattendue dans main: {e}. Redémarrage dans 10 secondes...", exc_info=True)
            await asyncio.sleep(10)
    
    print("✅ Embedding-Service: Service arrêté.")

if __name__ == '__main__':
    asyncio.run(main())