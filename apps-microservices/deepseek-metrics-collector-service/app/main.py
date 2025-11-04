import os
import asyncio
import json
import aio_pika
import aiohttp
import aiormq

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
DEEPSEEK_METRICS_COLLECTOR_URL = os.environ.get("DEEPSEEK_METRICS_COLLECTOR_URL") # e.g., "http://api-gateway:8500/v1/log-metrics"

EXCHANGE_NAME = 'processed_data_exchange'
QUEUE_NAME = 'deepseek_metrics_queue'
ROUTING_KEY = 'metrics.deepseek.result'

BATCH_SIZE = 100  # Nombre de métriques à envoyer en un seul appel HTTP
BATCH_TIMEOUT_SECONDS = 5.0 # Temps max d'attente avant d'envoyer un batch partiel

class MetricsConsumer:
    def __init__(self):
        self.metrics_buffer = asyncio.Queue()

    async def setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        exchange = await channel.declare_exchange(EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, ROUTING_KEY)
        return queue

    async def on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        async with message.process():
            try:
                metric = json.loads(message.body)
                await self.metrics_buffer.put(metric)
            except json.JSONDecodeError:
                print(f"   -> ERREUR: Impossible de décoder le message métrique: {message.body}")

    async def batch_sender(self):
        print("⚙️  Expéditeur de batch de métriques démarré.")
        batch = []
        while True:
            try:
                # Attendre un message avec un timeout
                timeout = BATCH_TIMEOUT_SECONDS if batch else None
                metric = await asyncio.wait_for(self.metrics_buffer.get(), timeout=timeout)
                batch.append(metric)
            except asyncio.TimeoutError:
                pass # Le timeout a été atteint, on traite le batch actuel

            if len(batch) >= BATCH_SIZE or (batch and timeout is not None):
                batch_to_send = list(batch) # Copier le batch
                batch.clear()
                
                print(f"   -> Envoi d'un batch de {len(batch_to_send)} métriques...")
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(DEEPSEEK_METRICS_COLLECTOR_URL, json=batch_to_send) as resp:
                            if resp.status == 200:
                                print(f"      • [SUCCESS] Batch de {len(batch_to_send)} métriques envoyé.")
                            else:
                                print(f"      • [FAILURE] Le serveur de logging a répondu {resp.status}. Les métriques de ce batch sont perdues.")
                except aiohttp.ClientError as e:
                    print(f"      • [FAILURE] Erreur de connexion au serveur de logging: {e}. Les métriques de ce batch sont perdues.")

async def main():
    if not RABBITMQ_URL or not DEEPSEEK_METRICS_COLLECTOR_URL:
        print("❌ ERREUR: RABBITMQ_URL et DEEPSEEK_METRICS_COLLECTOR_URL doivent être définis.")
        exit(1)

    print("🚀 deepseek-metrics-collector-service: Démarrage...")
    loop = asyncio.get_event_loop()
    
    while True:
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL, loop=loop)
            print("✅ Connecté à RabbitMQ.")
            
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=BATCH_SIZE * 2) # Prefetch un peu plus que la taille du batch

                consumer = MetricsConsumer()
                queue = await consumer.setup_queues(channel)
                
                # Démarrer la tâche de fond qui enverra les batches
                asyncio.create_task(consumer.batch_sender())
                
                await queue.consume(consumer.on_message)
                
                print("👂 En attente de messages de métriques...")
                await asyncio.Future()

        except (aiormq.exceptions.AMQPConnectionError, ConnectionError) as e:
            print(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Erreur inattendue: {e}. Redémarrage dans 10 secondes...")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(main())