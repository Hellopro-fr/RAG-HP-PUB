import json
import logging
import asyncio
from typing import List
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.core.credentials import settings
from app.messaging.publisher import Publisher
from app.core.equivalence_generator import EquivalenceGenerator
from app.core.api_client import HelloProAPIClient
from app.schemas.question_caracteristique import RequestProcessus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000


class Consumer:
    """Async Consumer pour le service QC-equivalence (step 6)."""

    def __init__(self, publisher: Publisher):
        self.publisher = publisher
        self.connection = None
        self.channel = None
        self.queue = None
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self._message_queue: asyncio.Queue = asyncio.Queue()

        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.step6.start'
        self.queue_name = 'qc_equivalence_queue'
        self.retry_exchange = 'qc_retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'qc_dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

    async def connect(self):
        logger.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)
        await self.publisher.setup(self.channel)
        await self._setup_infrastructure()
        logger.info("✅ QC-Equivalence Consumer initialized")

    async def _setup_infrastructure(self):
        dlq_exchange = await self.channel.declare_exchange(self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq_queue = await self.channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq_queue.bind(dlq_exchange, routing_key=self.routing_key)

        retry_exchange = await self.channel.declare_exchange(self.retry_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        retry_queue = await self.channel.declare_queue(self.retry_queue_name, durable=True,
            arguments={"x-message-ttl": RETRY_TTL_MS, "x-dead-letter-exchange": self.exchange_name, "x-dead-letter-routing-key": self.routing_key})
        await retry_queue.bind(retry_exchange, routing_key=self.routing_key)

        main_exchange = await self.channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True,
            arguments={"x-dead-letter-exchange": self.retry_exchange, "x-dead-letter-routing-key": self.routing_key})
        await self.queue.bind(main_exchange, routing_key=self.routing_key)

    def _get_retry_count(self, message: AbstractIncomingMessage) -> int:
        headers = message.headers
        if headers and "x-death" in headers:
            for death in headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    def _is_transient_error(self, exception: Exception) -> bool:
        if isinstance(exception, (
            aio_pika.exceptions.AMQPConnectionError,
            aio_pika.exceptions.AMQPChannelError,
            aio_pika.exceptions.ChannelClosed,
            aio_pika.exceptions.ConnectionClosed,
        )):
            return True
        error_msg = str(exception).lower()
        return any(kw in error_msg for kw in ['timeout', 'connection reset', 'connection refused', 'temporarily unavailable', 'service unavailable', 'timed out', 'network unreachable', 'connection aborted', 'broken pipe', 'eof', 'end of file'])

    async def _collect_messages_batch(self) -> List[AbstractIncomingMessage]:
        """
        Collecte jusqu'à BATCH_SIZE messages pendant BATCH_TIMEOUT_SECONDS max.
        Retourne dès qu'on atteint BATCH_SIZE ou que le timeout expire.
        """
        messages: List[AbstractIncomingMessage] = []
        deadline = asyncio.get_event_loop().time() + settings.BATCH_TIMEOUT_SECONDS
        
        # logger.info(f"⏳ Début collecte batch (max {settings.BATCH_SIZE} messages, timeout {settings.BATCH_TIMEOUT_SECONDS}s)")
        
        while len(messages) < settings.BATCH_SIZE:
            remaining_time = deadline - asyncio.get_event_loop().time()
            if remaining_time <= 0:
                # logger.info(f"⏰ Timeout atteint après {settings.BATCH_TIMEOUT_SECONDS}s")
                break
            
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=remaining_time
                )
                messages.append(message)
                logger.info(f"📨 Message reçu ({len(messages)}/{settings.BATCH_SIZE})")
            except asyncio.TimeoutError:
                # logger.info(f"⏰ Timeout atteint, {len(messages)} messages collectés")
                break
        
        return messages

    async def _feed_message_queue(self):
        """Alimente la queue interne avec les messages RabbitMQ."""
        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                await self._message_queue.put(message)

    async def process_message(self, message: AbstractIncomingMessage):
        """Traite un message avec logs contextualisés par catégorie."""
        async with message.process(ignore_processed=True):
            id_categorie = None
            try:
                data = json.loads(message.body.decode())
                id_categorie = data.get('id_categorie')
                is_reset = data.get('is_reset', False)

                if not id_categorie:
                    raise ValueError("id_categorie manquant dans le message.")

                # Log contextualisé avec préfixe [CAT-{id}]
                logger.info(f"[CAT-{id_categorie}] 📥 Début traitement catégorie")

                request = RequestProcessus(id_categorie=id_categorie, is_reset=is_reset)
                api_client = HelloProAPIClient()
                generator = EquivalenceGenerator(api_client)

                try:
                    result = await generator.generate_all_equivalences(request)
                    # Echo du fichier tracking dans les logs
                    if generator.tracking_file:
                        logger.info(f"[CAT-{id_categorie}] 📁 Fichier tracking: {generator.tracking_file}")
                finally:
                    await generator.close()

                output_message = {'id_categorie': id_categorie, 'is_reset': is_reset, 'step': 7, 'previous_step': 'equivalence', 'status': result.status}
                await self.publisher.publish_message(output_message)
                await message.ack()
                logger.info(f"[CAT-{id_categorie}] ✅ Traitement terminé avec succès")

            except (json.JSONDecodeError, ValueError) as e:
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                logger.error(f"{cat_prefix}❌ Erreur permanente: {e}")
                headers = DLQProperties.create_dlq_headers(e, "qc-equivalence", 0, message)
                await self.channel.default_exchange.publish(aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=self.dead_letter_queue_name)
                await message.ack()

            except Exception as e:
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                retry_count = self._get_retry_count(message)
                if self._is_transient_error(e) and retry_count < MAX_RETRIES:
                    logger.warning(f"{cat_prefix}⚠️ Erreur transitoire (essai {retry_count + 1}), retry: {e}")
                    await message.nack(requeue=False)
                else:
                    logger.error(f"{cat_prefix}❌ Échec après {retry_count + 1} tentatives: {e}")
                    headers = DLQProperties.create_dlq_headers(e, "qc-equivalence", retry_count, message)
                    await self.channel.default_exchange.publish(aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=self.dead_letter_queue_name)
                    await message.ack()

    async def start_consuming(self):
        """Démarre la boucle d'écoute avec batching et contrôle de concurrence."""
        await self.connect()
        logger.info(f"👂 QC-Equivalence: En attente sur {self.queue_name}")
        logger.info(f"📦 Configuration: batch_size={settings.BATCH_SIZE}, timeout={settings.BATCH_TIMEOUT_SECONDS}s, concurrence={settings.MAX_CONCURRENCY}")

        # Démarrer le feeder en arrière-plan
        feeder_task = asyncio.create_task(self._feed_message_queue())

        try:
            while True:
                # Collecter un batch de messages
                messages = await self._collect_messages_batch()
                
                if not messages:
                    # logger.info("📭 Aucun message reçu, attente du prochain batch...")
                    continue
                
                logger.info(f"📦 Batch collecté: {len(messages)} message(s) - Démarrage traitement parallèle")
                
                # Dédupliquer les messages par catégorie
                unique_messages = await self._deduplicate_messages(messages)
                
                if not unique_messages:
                    continue
                
                # Traiter les messages en parallèle
                tasks = []
                for message in unique_messages:
                    await self.semaphore.acquire()
                    task = asyncio.create_task(self._process_with_release(message))
                    tasks.append(task)
                
                # Attendre que tous les messages du batch soient traités
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"✅ Batch de {len(unique_messages)} message(s) traité")
        finally:
            feeder_task.cancel()

    async def _deduplicate_messages(self, messages: List[AbstractIncomingMessage]) -> List[AbstractIncomingMessage]:
        """Déduplique les messages par id_categorie, ACK les doublons sans traitement."""
        seen_categories = set()
        unique_messages = []
        
        for message in messages:
            try:
                data = json.loads(message.body.decode())
                cat_id = data.get('id_categorie')
                
                if cat_id in seen_categories:
                    logger.warning(f"[CAT-{cat_id}] ⚠️ Message dupliqué dans le batch - ignoré")
                    await message.ack()
                else:
                    seen_categories.add(cat_id)
                    unique_messages.append(message)
            except Exception as e:
                # En cas d'erreur de parsing, on garde le message pour traitement normal
                unique_messages.append(message)
        
        if len(messages) != len(unique_messages):
            logger.info(f"📊 Déduplication: {len(messages)} -> {len(unique_messages)} messages uniques")
        
        return unique_messages

    async def _process_with_release(self, message: AbstractIncomingMessage):
        """Wrapper pour process_message qui libère le semaphore après traitement."""
        try:
            await self.process_message(message)
        finally:
            self.semaphore.release()

    async def close(self):
        if self.connection:
            await self.connection.close()
