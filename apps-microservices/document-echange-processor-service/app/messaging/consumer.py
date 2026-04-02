import aio_pika
import os
import time
import json
import asyncio
import logging
import aiormq
import gc

from document_echange_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from document_echange_processor_service.core.processor import process_document_data_for_templating # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

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
        
        logger.info("✅ Consumer initialisé.")

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
        logger.info("⚙️  Processeur de batch démarré. En attente de messages...")
        
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
                logger.info("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            logger.info(f"⚙️  Traitement d'un batch de {batch_size} messages...")
            
            # --- DECODE FIRST, THEN ACK ---
            # Parse JSON before ACK so malformed messages can be sent to DLQ instead of being lost.
            messages_to_process = []
            valid_batch_indices = []

            for i, msg in enumerate(batch):
                try:
                    messages_to_process.append(json.loads(msg.body))
                    valid_batch_indices.append(i)
                except json.JSONDecodeError as e:
                    logger.error(f"Erreur de décodage JSON pour le message {msg.delivery_tag}. Envoi en DLQ.")
                    try:
                        async with self.connection.channel() as dlq_channel:
                            dlx = await dlq_channel.get_exchange(self.dead_letter_exchange, ensure=True)
                            dlq_headers = DLQProperties.create_dlq_headers(
                                e, 'document-echange-processor-service', 0, msg
                            )
                            await dlx.publish(
                                aio_pika.Message(body=msg.body, headers=dlq_headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                routing_key=self.routing_key,
                            )
                    except Exception as dlq_err:
                        logger.critical(f"Impossible d'envoyer le message malformé en DLQ: {dlq_err}")
                    await msg.ack()

            # ACK-EARLY for valid messages — before the long OCR processing to avoid RabbitMQ timeout.
            for idx in valid_batch_indices:
                try:
                    await batch[idx].ack()
                except Exception as e:
                    logger.warning(f"Impossible d'acquitter le message {batch[idx].delivery_tag} avant traitement: {e}.")

            if not messages_to_process:
                continue

            try:
                # Ce traitement peut être TRÈS long (minutes/heures)
                processed_results = await process_document_data_for_templating(messages_to_process)
                
                async with self.connection.channel() as channel:
                    for i, result in enumerate(processed_results):
                        original_msg_index = valid_batch_indices[i]
                        original_message = batch[original_msg_index]
                        retry_count = self._get_retry_count(original_message)

                        if result['status'] == 'success':
                            try:
                                await self.publisher.publish_message(result['processed_message'], channel)
                            except Exception as pub_err:
                                logger.error("Echec publication message (tag: %s): %s", original_message.delivery_tag, pub_err)
                                try:
                                    dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                    dlq_headers = DLQProperties.create_dlq_headers(
                                        pub_err, 'document-echange-processor-service', retry_count, original_message
                                    )
                                    await dlx.publish(
                                        aio_pika.Message(body=original_message.body, headers=dlq_headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                        routing_key=self.routing_key
                                    )
                                except Exception as dlq_err:
                                    logger.critical("Echec publication en DLQ apres erreur publish: %s", dlq_err)

                        elif result['status'] == 'transient_error':
                            # Transient error (OCR down, connection timeout) -> retry via retry exchange
                            if retry_count < MAX_RETRIES:
                                logger.warning("Erreur transitoire (essai %d/%d): %s", retry_count + 1, MAX_RETRIES, result.get('error_message', ''))
                                try:
                                    retry_ex = await channel.get_exchange(self.retry_exchange, ensure=True)
                                    current_headers = (original_message.headers or {}).copy()
                                    current_headers['x-retry-count'] = retry_count + 1
                                    await retry_ex.publish(
                                        aio_pika.Message(body=original_message.body, headers=current_headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                        routing_key=self.routing_key
                                    )
                                except Exception as retry_err:
                                    logger.critical("Echec republication pour retry: %s", retry_err)
                            else:
                                logger.error("MAX_RETRIES atteint pour erreur transitoire. Envoi en DLQ.")
                                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                dlq_headers = DLQProperties.create_dlq_headers(
                                    Exception(result.get('error_message', 'Transient error after max retries')),
                                    'document-echange-processor-service', retry_count, original_message
                                )
                                await dlx.publish(
                                    aio_pika.Message(body=original_message.body, headers=dlq_headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                    routing_key=self.routing_key
                                )

                        elif result['status'] == 'error':
                            # Permanent error -> DLQ directly
                            logger.error("Erreur permanente pour message (tag: %s). Envoi en DLQ.", original_message.delivery_tag)
                            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)

                            dlq_headers = DLQProperties.create_dlq_headers(
                                Exception(result['error_message']),
                                'document-echange-processor-service',
                                retry_count,
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
                logger.critical(f"❌ ERREUR CATASTROPHIQUE sur le batch: {e}.")
                logger.exception("Traceback complet:")

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
                                # MAX_RETRIES atteint : envoi à la DLQ
                                logger.error(f"   -> MAX_RETRIES atteint pour le message (tag: {msg.delivery_tag}). Envoi à la DLQ.")
                                dlx = await rescue_channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                
                                dlq_headers = DLQProperties.create_dlq_headers(
                                    Exception(f"Erreur catastrophique batch: {e}"), 
                                    'document-echange-processor-service', 
                                    cnt, 
                                    msg
                                )
                                
                                await dlx.publish(
                                    aio_pika.Message(
                                        body=msg.body,
                                        headers=dlq_headers,
                                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                    ),
                                    routing_key=self.routing_key
                                ) 
                except Exception as rescue_error:
                    logger.critical(f"💀 Impossible de sauver le batch après crash : {rescue_error}")

            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                logger.info(f"🏁 Traitement du batch terminé en {duration:.4f} secondes.")
                
                # Nettoyage explicite de la mémoire après chaque batch
                try:
                    del batch
                    if 'messages_to_process' in locals(): del messages_to_process
                    if 'processed_results' in locals(): del processed_results
                    gc.collect()
                    logger.debug("🧹 Mémoire nettoyée (GC collect).")
                except Exception as e:
                    logger.debug(f"Message non critique : Erreur lors du nettoyage mémoire : {e}")
    
    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Callback léger qui met les messages dans un buffer asynchrone."""
        await self.message_buffer.put(message)


    async def start_consuming(self):
        """Démarre le consumer et la tâche de traitement de batch."""
        self._channel = await self.connection.channel()
        await self._channel.set_qos(prefetch_count=BATCH_SIZE)

        queue = await self._setup_queues(self._channel)

        # Démarrer la tâche de fond qui traitera les batches
        self._batch_task = asyncio.create_task(self.batch_processor())
        
        # Commencer à consommer les messages et à les mettre dans le buffer
        logger.info("👂 Document-processor-service: En attente de messages...")
        await queue.consume(self._on_message)