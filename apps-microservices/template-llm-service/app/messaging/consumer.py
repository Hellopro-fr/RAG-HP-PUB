import aio_pika
import json
import asyncio
import time

from template_llm_service.messaging.publisher import Publisher
from template_llm_service.core.processor import classify_page_template_batch
from common_utils.autres.DLQProperties import DLQProperties

# --- Configuration du Batching ---
# Détermine le nombre maximum de messages à traiter en un seul batch.
# Une valeur plus élevée augmente le débit (throughput) mais aussi la latence potentielle.
# À ajuster en fonction de la charge et de la VRAM du GPU.
BATCH_SIZE = 8

# Détermine le temps d'attente maximum (en secondes) avant de traiter un batch,
# même s'il n'est pas plein. C'est une sécurité pour éviter que des messages
# ne restent bloqués indéfiniment en période de faible trafic.
BATCH_TIMEOUT_SECONDS = 2.0
MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.message_buffer = asyncio.Queue()
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare toutes les files d'attente et les échanges nécessaires."""
        
        # DLQ Finale
        dlx = await channel.declare_exchange(self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        # File d'attente de Retry
        retry_exchange = await channel.declare_exchange(self.retry_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        retry_queue = await channel.declare_queue(
            self.retry_queue_name,
            durable=True,
            arguments={
                'x-message-ttl': RETRY_TTL_MS,
                'x-dead-letter-exchange': self.exchange_name,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await retry_queue.bind(retry_exchange, self.routing_key)

        # File d'attente principale
        exchange = await channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': self.retry_exchange,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await queue.bind(exchange, self.routing_key)
        
        return queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Callback léger qui met les messages dans un buffer asynchrone."""
        await self.message_buffer.put(message)

    async def batch_processor(self):
        """Tâche de fond qui traite les messages par lots de manière asynchrone."""
        print("⚙️  Processeur de batch démarré. En attente de messages...")
        batch = []
        
        while True:
            try:
                # Attendre un message avec un timeout
                timeout = BATCH_TIMEOUT_SECONDS if batch else None
                message = await asyncio.wait_for(self.message_buffer.get(), timeout=timeout)
                batch.append(message)
            except asyncio.TimeoutError:
                # Le timeout a été atteint, on traite le batch actuel s'il n'est pas vide
                pass

            if len(batch) >= BATCH_SIZE or (batch and timeout is not None):
                start_time = time.monotonic()
                batch_size = len(batch)
                print(f"⚙️  Traitement d'un batch de {batch_size} messages...")
                messages_to_process = [json.loads(msg.body) for msg in batch]
                
                try:
                    processed_results = await classify_page_template_batch(messages_to_process)
                    
                    async with self.connection.channel() as channel:
                        for i, result in enumerate(processed_results):
                            original_message = batch[i]
                            if result['status'] == 'success':
                                await self.publisher.publish_message(result['processed_message'], channel)
                                await original_message.ack()
                            else: # status == 'error'
                                retry_count = self._get_retry_count(original_message)
                                if retry_count < MAX_RETRIES:
                                    print(f"   -> NACK du message (tag: {original_message.delivery_tag}) pour nouvelle tentative.")
                                    await original_message.nack(requeue=False)
                                else:
                                    print(f"   -> Échec final pour le message (tag: {original_message.delivery_tag}). Envoi à la DLQ finale.")
                                    dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                    
                                    dlq_headers = DLQProperties.create_dlq_headers(
                                        Exception(result['error_message']), 
                                        'template-llm-service', 
                                        MAX_RETRIES, 
                                        original_message
                                    )
                                    
                                    await dlx.publish(
                                        aio_pika.Message(
                                            body=original_message.body,
                                            headers=dlq_headers,
                                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                        ),
                                        routing_key=self.routing_key
                                    )
                                    await original_message.ack()

                except Exception as e:
                    print(f"❌ ERREUR CATASTROPHIQUE sur le batch (ex: LLM indisponible): {e}. NACK de tous les messages du batch.")
                    for msg in batch:
                        await msg.nack(requeue=False)
                finally:
                    end_time = time.monotonic()
                    duration = end_time - start_time
                    print(f"🏁 Traitement du batch de {batch_size} message(s) terminé en {duration:.4f} secondes.")
                    batch = []

    async def start_consuming(self):
        """Démarre le consumer et la tâche de traitement de batch."""
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=BATCH_SIZE)
        
        queue = await self._setup_queues(channel)
        
        # Démarrer la tâche de fond qui traitera les batches
        asyncio.create_task(self.batch_processor())
        
        # Commencer à consommer les messages et à les mettre dans le buffer
        print("👂 template-llm-service: En attente de messages...")
        await queue.consume(self._on_message)