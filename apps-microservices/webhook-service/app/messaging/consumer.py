import asyncio
import json
import logging
from typing import Dict, List, Optional
import aio_pika
from webhook_service.core.processor import WebhookSender, BATCH_SIZE, BATCH_TIMEOUT_S

logger = logging.getLogger(__name__)


class Consumer:
    """
    Consumer async RabbitMQ avec batching.

    Accumule les messages dans un buffer et les envoie en batch
    lorsque le buffer atteint BATCH_SIZE ou après BATCH_TIMEOUT_S secondes.
    Le lock couvre l'intégralité du flush (drain + HTTP + ACK/NACK) pour
    éviter les double-flush et double-ACK.
    """

    def __init__(self, connection: aio_pika.RobustConnection):
        self.connection = connection
        self.exchange_name = 'inserted_data_exchange'
        self.routing_key = 'data.ready_for_webhook'
        self.queue_name = 'webhook_queue'

        self.sender = WebhookSender()

        # Buffer pour le batching — on stocke les IncomingMessage pour ACK/NACK
        self._buffer: List[dict] = []
        self._messages: List[aio_pika.IncomingMessage] = []
        self._channel: Optional[aio_pika.abc.AbstractChannel] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def _setup(self):
        """Déclare l'exchange, la queue et le binding."""
        self._channel = await self.connection.channel()
        await self._channel.set_qos(prefetch_count=BATCH_SIZE * 2)

        exchange = await self._channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        queue = await self._channel.declare_queue(
            self.queue_name,
            durable=True,
        )

        await queue.bind(exchange, routing_key=self.routing_key)
        logger.info(
            f"Queue '{self.queue_name}' bound to '{self.exchange_name}' "
            f"(routing_key: '{self.routing_key}')"
        )
        return queue

    async def _flush_buffer(self):
        """
        Envoie le contenu du buffer en batch et ACK/NACK les messages.
        Le lock couvre toute l'opération pour empêcher les double-flush.
        """
        async with self._lock:
            if not self._buffer:
                return

            batch = self._buffer[:]
            messages = self._messages[:]
            self._buffer.clear()
            self._messages.clear()

            logger.info(f"Flush batch de {len(batch)} message(s)")

            try:
                # Grouper par URL de destination pour éviter le mauvais routage
                groups = self._group_by_url(batch, messages)

                for url, group_batch, group_messages in groups:
                    if url == "__no_url__":
                        success = False
                    else:
                        success = await self.sender.send_batch(group_batch, url=url)
                    for msg in group_messages:
                        try:
                            if success:
                                await msg.ack()
                            else:
                                await msg.nack(requeue=False)
                        except Exception as e:
                            logger.error(f"Erreur ACK/NACK message: {e}")

            except Exception as e:
                logger.exception(f"❌ Erreur lors du flush batch: {e}")
                for msg in messages:
                    try:
                        await msg.nack(requeue=False)
                    except Exception as nack_err:
                        logger.error(f"Erreur NACK message: {nack_err}")

    @staticmethod
    def _group_by_url(batch, messages):
        """Regroupe les payloads et messages par URL de destination."""
        from webhook_service.core.processor import resolve_webhook_url

        groups: Dict[str, tuple] = {}
        for data, msg in zip(batch, messages):
            url = resolve_webhook_url(data) or "__no_url__"
            if url not in groups:
                groups[url] = ([], [])
            groups[url][0].append(data)
            groups[url][1].append(msg)

        result = []
        for url, (group_batch, group_messages) in groups.items():
            if url == "__no_url__":
                logger.warning(f"Aucune URL pour {len(group_messages)} message(s), sera NACK au flush")
                result.append((url, group_batch, group_messages))
            else:
                result.append((url, group_batch, group_messages))
        return result

    async def _schedule_flush(self):
        """
        Planifie un flush après BATCH_TIMEOUT_S secondes.
        Appelé sous le lock pour éviter la création de timers multiples.
        """
        if self._flush_task and not self._flush_task.done():
            return
        self._flush_task = asyncio.create_task(self._timed_flush())

    async def _timed_flush(self):
        """Attend le timeout puis flush le buffer."""
        try:
            await asyncio.sleep(BATCH_TIMEOUT_S)
            await self._flush_buffer()
        except asyncio.CancelledError:
            pass

    async def _cancel_flush_task(self):
        """Annule proprement le timer de flush."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        self._flush_task = None

    async def _on_message(self, message: aio_pika.IncomingMessage):
        """Callback pour chaque message reçu."""
        try:
            data = json.loads(message.body)
            logger.info(f"📥 Message reçu pour collection: {data.get('collection', 'unknown')}")

            # Filtrage : seuls les messages mode=update sont traités
            if data.get("mode") != "update":
                await message.ack()
                logger.info(f"Message ignoré (mode={data.get('mode', 'none')} != 'update'), ACK silencieux")
                return

            # Ajouter au buffer et décider du flush (tout sous le lock)
            async with self._lock:
                self._buffer.append(data)
                self._messages.append(message)
                buffer_size = len(self._buffer)

                if buffer_size >= BATCH_SIZE:
                    await self._cancel_flush_task()
                else:
                    await self._schedule_flush()

            # Flush hors du lock d'ajout, mais _flush_buffer prend le lock lui-même
            if buffer_size >= BATCH_SIZE:
                await self._flush_buffer()

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON invalide: {e}")
            await message.nack(requeue=False)
        except Exception as e:
            logger.exception(f"❌ Erreur traitement message: {e}")
            await message.nack(requeue=True)

    async def start_consuming(self):
        """Démarre la consommation asynchrone des messages."""
        queue = await self._setup()

        await queue.consume(self._on_message)
        logger.info(f"👂 webhook-service en attente de messages sur queue '{self.queue_name}'...")

        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass

    async def stop(self):
        """Arrêt propre : flush le buffer restant et ferme la session HTTP."""
        logger.info("🛑 Arrêt du consumer, flush du buffer restant...")
        await self._cancel_flush_task()
        await self._flush_buffer()
        await self.sender.close()
        logger.info("✅ Consumer arrêté proprement")
