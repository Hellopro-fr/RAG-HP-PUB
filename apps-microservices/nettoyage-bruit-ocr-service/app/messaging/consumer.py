import aio_pika
import os
import time
import json
import asyncio
import logging
import aiormq
import traceback

from nettoyage_bruit_ocr_service.messaging.publisher import Publisher
from nettoyage_bruit_ocr_service.core.processor import nettoyer_bruits_ocr
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000
BATCH_SIZE = 1
BATCH_TIMEOUT_SECONDS = 0.5

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

        self.consumer_channel = None
        self._keep_alive_task = None

        logger.info("Consumer initialise.")

    async def _keep_channel_alive(self):
        """
        Tache de fond qui maintient le canal actif.
        Verifie periodiquement l'etat du canal.
        """
        logger.debug("Tache keep-alive du canal demarree")

        heartbeat_count = 0

        while True:
            try:
                await asyncio.sleep(30)
                heartbeat_count += 1

                if self.consumer_channel is None:
                    logger.warning("[%d] Canal consumer inexistant", heartbeat_count)
                    continue

                if self.consumer_channel.is_closed:
                    logger.error("[%d] Canal consumer FERME !", heartbeat_count)
                    continue

                try:
                    await self.consumer_channel.get_exchange(
                        self.exchange_name,
                        ensure=False
                    )
                    logger.debug("[%d] Heartbeat OK (canal actif)", heartbeat_count)

                except aiormq.exceptions.ChannelInvalidStateError:
                    logger.error("[%d] Canal en etat invalide !", heartbeat_count)
                except Exception as e:
                    logger.warning("[%d] Erreur heartbeat: %s - %s", heartbeat_count, type(e).__name__, e)

            except asyncio.CancelledError:
                logger.info("Tache keep-alive arretee")
                break
            except Exception as e:
                logger.error("Erreur inattendue dans keep-alive: %s", e, exc_info=True)

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Configure les queues, exchanges et bindings."""
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        retry_exchange = await channel.declare_exchange(
            self.retry_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
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

        exchange = await channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True
        )
        queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': self.retry_exchange,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await queue.bind(exchange, self.routing_key)

        logger.info("Queues configurees: %s, %s, %s", self.queue_name, self.retry_queue_name, self.dead_letter_queue_name)
        return queue

    async def batch_processor(self):
        """Tache de fond qui traite les messages un par un avec ACK-after."""
        logger.info("Processeur de batch demarre. En attente de messages...")

        while True:
            batch = []

            try:
                first_message = await self.message_buffer.get()
                batch.append(first_message)

                while len(batch) < BATCH_SIZE:
                    try:
                        message = await asyncio.wait_for(
                            self.message_buffer.get(),
                            timeout=BATCH_TIMEOUT_SECONDS
                        )
                        batch.append(message)
                    except asyncio.TimeoutError:
                        break

            except asyncio.CancelledError:
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            logger.info("Traitement de %d message(s)...", batch_size)

            try:
                messages_to_process = [json.loads(msg.body) for msg in batch]
            except json.JSONDecodeError as e:
                logger.error("Erreur de decodage JSON: %s", e)
                for msg in batch:
                    await msg.nack(requeue=False)
                continue

            try:
                processed_results = await nettoyer_bruits_ocr(messages_to_process)

                async with self.connection.channel() as channel:
                    for i, result in enumerate(processed_results):
                        msg = batch[i]

                        if 'metric_payload' in result:
                            await self.publisher.publish_metric_message(
                                result['metric_payload'],
                                channel
                            )

                        text = "ok"
                        if "processed_message" in result:
                            if "data" in result['processed_message']:
                                text = result['processed_message'].get("data",{}).get("text","")
                                logger.debug("Suivi text : %s...", text[:10] if text else "")

                        if result['status'] == 'success' and text:
                            await self.publisher.publish_message(
                                result['processed_message'],
                                channel
                            )
                            await msg.ack()
                        else:
                            try:
                                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                dlq_headers = DLQProperties.create_dlq_headers(
                                    Exception(result.get('error_message', 'Unknown error')),
                                    'nettoyage-bruit-ocr-service',
                                    MAX_RETRIES,
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
                            except Exception as dlq_err:
                                logger.critical("Impossible d'envoyer en DLQ: %s", dlq_err, exc_info=True)
                            await msg.ack()

            except Exception as e:
                logger.error("ERREUR sur le batch: %s", e, exc_info=True)
                for msg in batch:
                    try:
                        await msg.nack(requeue=False)
                    except Exception:
                        pass

            finally:
                duration = time.monotonic() - start_time
                logger.info("Batch termine en %.2fs (%.2f min)", duration, duration / 60)

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Callback appele pour chaque message recu.
        Met simplement le message dans le buffer pour traitement asynchrone.
        """
        await self.message_buffer.put(message)

    async def start_consuming(self):
        """Demarre le consumer avec prefetch=1 et la tache keep-alive."""
        logger.info("Demarrage du consumer...")

        self.consumer_channel = await self.connection.channel()

        await self.consumer_channel.set_qos(prefetch_count=1)
        logger.info("QoS configure: prefetch_count=1")

        queue = await self._setup_queues(self.consumer_channel)

        self._keep_alive_task = asyncio.create_task(self._keep_channel_alive())
        logger.info("Tache keep-alive demarree")

        asyncio.create_task(self.batch_processor())
        logger.info("Processeur de batch demarre")

        logger.debug("Canal consumer: %s", type(self.consumer_channel).__name__)
        logger.debug("Connexion: %s", type(self.connection).__name__)
        logger.debug("Queue: %s", queue.name)

        logger.info("Nettoyage-bruit-ocr-service: En attente de messages...")
        await queue.consume(self._on_message)

    async def stop(self):
        """Arret propre du consumer."""
        logger.info("Arret du consumer...")

        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                logger.info("Tache keep-alive arretee")

        if self.consumer_channel and not self.consumer_channel.is_closed:
            await self.consumer_channel.close()
            logger.info("Canal consumer ferme")

        logger.info("Consumer arrete proprement")
