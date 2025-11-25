import aio_pika
import os
import time
import json
import asyncio
import aiormq
import traceback

from nettoyage_bruit_ocr_service.messaging.publisher import Publisher  # Importe notre publisher local
from nettoyage_bruit_ocr_service.core.processor import nettoyer_bruits_ocr # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative
BATCH_SIZE = 20
BATCH_TIMEOUT_SECONDS = 2.0

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        
        self.message_buffer = asyncio.Queue()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_ocr_cleaning'
        self.queue_name = 'nettoyage_bruit_ocr_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        print("✅ Consumer initialisé.")

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        dlx = await channel.declare_exchange(self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        retry_exchange = await channel.declare_exchange(self.retry_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        retry_queue = await channel.declare_queue(
            self.retry_queue_name, durable=True,
            arguments={'x-message-ttl': RETRY_TTL_MS, 'x-dead-letter-exchange': self.exchange_name, 'x-dead-letter-routing-key': self.routing_key}
        )
        await retry_queue.bind(retry_exchange, self.routing_key)

        exchange = await channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(
            self.queue_name, durable=True,
            arguments={'x-dead-letter-exchange': self.retry_exchange, 'x-dead-letter-routing-key': self.routing_key}
        )
        await queue.bind(exchange, self.routing_key)
        return queue

    async def batch_processor(self):
        """Tâche de fond qui traite les messages par lots de manière asynchrone."""
        print("⚙️  Processeur de batch démarré. En attente de messages...")
        
        while True:
            batch = []
            try:
                # 1. Attendre indéfiniment le premier message pour démarrer un batch
                first_message = await self.message_buffer.get()
                batch.append(first_message)

                # 2. Une fois le premier message reçu, essayer de remplir le reste du batch
                #    en respectant le BATCH_TIMEOUT et le BATCH_SIZE.
                while len(batch) < BATCH_SIZE:
                    try:
                        message = await asyncio.wait_for(self.message_buffer.get(), timeout=BATCH_TIMEOUT_SECONDS)
                        batch.append(message)
                    except asyncio.TimeoutError:
                        # Le timeout a été atteint, on sort pour traiter le batch partiel
                        break
            except asyncio.CancelledError:
                print("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            print(f"⚙️  Traitement d'un batch de {batch_size} messages...")
            messages_to_process = [json.loads(msg.body) for msg in batch]
            
            try:
                processed_results = await nettoyer_bruits_ocr(messages_to_process)
                
                async with self.connection.channel() as channel:
                    for i, result in enumerate(processed_results):
                        original_message = batch[i]
                        
                        # Toujours publier la métrique
                        if 'metric_payload' in result:
                            await self.publisher.publish_metric_message(result['metric_payload'], channel)

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
                                    'nettoyage-bruit-ocr-service', 
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
                print(f"❌ ERREUR CATASTROPHIQUE sur le batch: {e}. NACK de tous les messages du batch.")
                traceback.print_exc()
                
                for msg in batch:
                    try:
                        await msg.nack(requeue=False)
                    except aiormq.exceptions.ChannelInvalidStateError:
                        # Le canal est déjà mort, on ne peut rien faire d'autre que de laisser la boucle principale se reconnecter.
                        print("   -> Le canal est déjà fermé. Impossible de NACK les messages restants. Ils seront re-délivrés après reconnexion.")
                        break # Sortir de la boucle de nack
            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                print(f"🏁 Traitement du batch de {batch_size} message(s) terminé en {duration:.4f} secondes.")
    
    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Callback léger qui met les messages dans un buffer asynchrone."""
        await self.message_buffer.put(message)


    async def start_consuming(self):
        """Démarre le consumer et la tâche de traitement de batch."""
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=BATCH_SIZE)
        
        queue = await self._setup_queues(channel)
        
        # Démarrer la tâche de fond qui traitera les batches
        asyncio.create_task(self.batch_processor())
        
        # Commencer à consommer les messages et à les mettre dans le buffer
        print("👂 Nettoyage-bruit-ocr-service: En attente de messages...")
        await queue.consume(self._on_message)