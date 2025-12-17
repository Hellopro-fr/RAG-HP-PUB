import aio_pika
import os
import time
import json
import asyncio
import aiormq
import traceback
import gc

from document_echange_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from document_echange_processor_service.core.processor import process_document_data_for_templating # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative
BATCH_SIZE = 10
BATCH_TIMEOUT_SECONDS = 0.5

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        
        self.message_buffer = asyncio.Queue()
        self.exchange_name = 'data_exchange_document'
        self.routing_key = 'new_data.document'
        self.queue_name = 'document_processing_queue'
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

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        headers = message.headers or {}
        if 'x-retry-count' in headers:
            return int(headers['x-retry-count'])

        if 'x-death' in headers:
            for death in headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0
    
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
                        break
            except asyncio.CancelledError:
                print("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            print(f"⚙️  Traitement d'un batch de {batch_size} messages...")
            
            # --- ACK-EARLY STRATEGY ---
            # On acquitte les messages AVANT le traitement long pour éviter le timeout RabbitMQ.
            # Si le traitement échoue, on devra republier manuellement le message.
            for msg in batch:
                try:
                    await msg.ack()
                except Exception as e:
                    print(f"⚠️ Impossible d'acquitter le message {msg.delivery_tag} avant traitement: {e}")
                    # On continue quand même, car si la co est coupée, le traitement sera probablement perdu ou republié plus tard.

            messages_to_process = []
            valid_batch_indices = [] # Indices des messages qui ont pu être décodés
            
            for i, msg in enumerate(batch):
                try:
                    messages_to_process.append(json.loads(msg.body))
                    valid_batch_indices.append(i)
                except json.JSONDecodeError:
                     print(f"❌ Erreur de décodage JSON pour le message {msg.delivery_tag}. Message ignoré (déjà acké).")
                     # Optionnel: Envoyer directement en DLQ si JSON invalide irrécupérable

            if not messages_to_process:
                continue

            try:
                # Ce traitement peut être TRÈS long (minutes/heures)
                processed_results = await process_document_data_for_templating(messages_to_process)
                
                async with self.connection.channel() as channel:
                    # processed_results correspond aux messages_to_process, qui correspondent aux valid_batch_indices
                    for i, result in enumerate(processed_results):
                        original_msg_index = valid_batch_indices[i]
                        original_message = batch[original_msg_index]
                        retry_count = self._get_retry_count(original_message)

                        if result['status'] == 'success':
                            await self.publisher.publish_message(result['processed_message'], channel)
                            # Message déjà acké au début
                            
                        elif result['status'] == 'error':
                            # Envoi direct à la DLQ sans retry
                            print(f"   -> Erreur de traitement pour le message (tag: {original_message.delivery_tag}). Envoi direct à la DLQ.")
                            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                            
                            dlq_headers = DLQProperties.create_dlq_headers(
                                Exception(result['error_message']), 
                                'document-echange-processor-service', 
                                retry_count,  # On garde le compteur actuel pour traçabilité
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

            except Exception as e:
                print(f"❌ ERREUR CATASTROPHIQUE sur le batch: {e}.")
                traceback.print_exc()

                # En cas de crash global du batch, on essaie de sauver les messages en les republiant
                # Attention : si la connexion est morte, ceci échouera aussi.
                try:
                     async with self.connection.channel() as rescue_channel:
                        retry_ex = await rescue_channel.get_exchange(self.retry_exchange, ensure=True)
                        
                        for idx in valid_batch_indices:
                            msg = batch[idx]
                            current_headers = (msg.headers or {}).copy()
                            cnt = self._get_retry_count(msg)
                            current_headers['x-retry-count'] = cnt + 1
                            
                            if cnt < MAX_RETRIES:
                                await retry_ex.publish(
                                    aio_pika.Message(
                                        body=msg.body,
                                        headers=current_headers,
                                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                    ),
                                    routing_key=self.routing_key
                                )
                            else:
                                # DLQ logic if needed for batched crash
                                pass 
                except Exception as rescue_error:
                    print(f"💀 Impossible de sauver le batch après crash : {rescue_error}")

            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                print(f"🏁 Traitement du batch terminé en {duration:.4f} secondes.")
                
                # Nettoyage explicite de la mémoire après chaque batch
                try:
                    del batch
                    if 'messages_to_process' in locals(): del messages_to_process
                    if 'processed_results' in locals(): del processed_results
                    gc.collect()
                    print("🧹 Mémoire nettoyée (GC collect).")
                except Exception as e:
                    print(f"Message non critique : Erreur lors du nettoyage mémoire : {e}")
    
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
        print("👂 Document-processor-service: En attente de messages...")
        await queue.consume(self._on_message)