import asyncio
import json
import logging
from typing import List
import aio_pika
from webhook_service.core.processor import WebhookSender, BATCH_SIZE, BATCH_TIMEOUT_S

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Consumer:
    """
    Consumer async RabbitMQ avec batching.

    Accumule les messages dans un buffer et les envoie en batch
    lorsque le buffer atteint BATCH_SIZE ou après BATCH_TIMEOUT_S secondes.
    """

    def __init__(self, connection: aio_pika.RobustConnection):
        self.connection = connection
        self.exchange_name = 'inserted_data_exchange'
        self.routing_key = 'data.ready_for_webhook'
        self.queue_name = 'webhook_queue'

        self.sender = WebhookSender()

        # Buffer pour le batching
        self._buffer: List[dict] = []
        self._delivery_tags: List[int] = []
        self._channel: aio_pika.abc.AbstractChannel = None
        self._flush_task: asyncio.Task = None
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
        """Envoie le contenu du buffer en batch et ACK les messages."""
        async with self._lock:
            if not self._buffer:
                return

            batch = self._buffer[:]
            tags = self._delivery_tags[:]
            self._buffer.clear()
            self._delivery_tags.clear()

        logger.info(f"Flush batch de {len(batch)} message(s)")

        try:
            success = await self.sender.send_batch(batch)

            for tag in tags:
                if success:
                    await self._channel.default_exchange  # no-op, just to keep ref
                    # ACK via the underlying channel
                    await self._ack(tag)
                else:
                    await self._nack(tag)

        except Exception as e:
            logger.exception(f"❌ Erreur lors du flush batch: {e}")
            for tag in tags:
                await self._nack(tag)

    async def _ack(self, delivery_tag: int):
        try:
            await self._channel.underlying_channel.basic_ack(delivery_tag)
        except Exception as e:
            logger.error(f"Erreur ACK delivery_tag={delivery_tag}: {e}")

    async def _nack(self, delivery_tag: int):
        try:
            await self._channel.underlying_channel.basic_nack(delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Erreur NACK delivery_tag={delivery_tag}: {e}")

    async def _schedule_flush(self):
        """Planifie un flush après BATCH_TIMEOUT_S secondes."""
        if self._flush_task and not self._flush_task.done():
            return  # Un flush est déjà planifié
        self._flush_task = asyncio.create_task(self._timed_flush())

    async def _timed_flush(self):
        """Attend le timeout puis flush le buffer."""
        await asyncio.sleep(BATCH_TIMEOUT_S)
        await self._flush_buffer()

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

            # Ajouter au buffer (sans ACK pour l'instant, géré au flush)
            async with self._lock:
                self._buffer.append(data)
                self._delivery_tags.append(message.delivery_tag)
                buffer_size = len(self._buffer)

            # Flush si le buffer est plein
            if buffer_size >= BATCH_SIZE:
                if self._flush_task and not self._flush_task.done():
                    self._flush_task.cancel()
                await self._flush_buffer()
            else:
                await self._schedule_flush()

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON invalide: {e}")
            await message.nack(requeue=False)
        except Exception as e:
            logger.exception(f"❌ Erreur traitement message: {e}")
            await message.nack(requeue=True)

    async def start_consuming(self):
        """Démarre la consommation asynchrone des messages."""
        queue = await self._setup()

        # Consommation avec manual ACK (no_ack=False par défaut)
        await queue.consume(self._on_message)
        logger.info(f"👂 webhook-service en attente de messages sur queue '{self.queue_name}'...")

        # Boucle infinie pour maintenir le consumer actif
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass

    async def stop(self):
        """Arrêt propre : flush le buffer restant et ferme la session HTTP."""
        logger.info("🛑 Arrêt du consumer, flush du buffer restant...")
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        await self._flush_buffer()
        await self.sender.close()
        logger.info("✅ Consumer arrêté proprement")
