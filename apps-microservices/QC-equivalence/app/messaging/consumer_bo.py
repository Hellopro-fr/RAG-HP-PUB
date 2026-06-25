import json
import logging
import asyncio
from typing import Set
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.core.credentials import settings
from app.core.equivalence_generator import EquivalenceGenerator
from app.core.api_client import HelloProAPIClient
from app.schemas.question_caracteristique import RequestEquivalenceBO

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000


class ConsumerBO:
    """Async Consumer de la façade BO (équivalence indépendante du step 6).

    Génère les équivalences sur le questionnaire BO (ANNUAIRE_BO) et les
    sauvegarde dans une table dédiée. Contrairement au consumer step 6 :
    - écoute sa propre routing key (qc.equivalence_bo.start),
    - NE PUBLIE RIEN vers un service aval (pas de publisher).

    IMPORTANT: La déduplication par catégorie ne fonctionne qu'au sein d'un
    même réplica (set in-memory). La déduplication inter-réplicas relève du
    backend.
    """

    def __init__(self):
        self.connection = None
        self.channel = None
        self.queue = None
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self._active_tasks: Set[asyncio.Task] = set()
        self._processing_categories: Set[str] = set()
        self._categories_lock = asyncio.Lock()

        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.equivalence_bo.start'
        self.queue_name = 'qc_equivalence_bo_queue'
        self.retry_exchange = 'qc_retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'qc_dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

    async def connect(self):
        logger.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)
        await self._setup_infrastructure()
        logger.info("✅ QC-Equivalence-BO Consumer initialized (streaming mode)")

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
            arguments={"x-dead-letter-exchange": self.retry_exchange, "x-dead-letter-routing-key": self.routing_key, "x-consumer-timeout": 7200000})
        await self.queue.bind(main_exchange, routing_key=self.routing_key)

    def _get_retry_count(self, message: AbstractIncomingMessage) -> int:
        headers = message.headers
        if headers and "x-death" in headers:
            for death in headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    def _is_transient_error(self, exception: Exception) -> bool:
        if isinstance(exception, (aio_pika.exceptions.AMQPConnectionError, aio_pika.exceptions.AMQPChannelError, aio_pika.exceptions.ChannelClosed, aio_pika.exceptions.ConnectionClosed)):
            return True
        error_msg = str(exception).lower()
        return any(kw in error_msg for kw in ['timeout', 'connection reset', 'connection refused', 'temporarily unavailable', 'service unavailable', 'timed out', 'network unreachable', 'connection aborted', 'broken pipe', 'eof', 'end of file'])

    async def _is_duplicate_category(self, cat_id: str) -> bool:
        """Vérifie si une catégorie est déjà en cours de traitement sur CE réplica."""
        async with self._categories_lock:
            if cat_id in self._processing_categories:
                return True
            self._processing_categories.add(cat_id)
            return False

    async def _release_category(self, cat_id: str):
        """Libère une catégorie après traitement (succès ou erreur)."""
        async with self._categories_lock:
            self._processing_categories.discard(cat_id)
            logger.debug(f"[CAT-{cat_id}] Catégorie BO libérée du set local")

    async def process_message(self, message: AbstractIncomingMessage):
        """Traite un message BO : génère l'équivalence et ACK (aucune publication aval)."""
        async with message.process(ignore_processed=True):
            id_categorie = None
            category_locked = False

            try:
                # 1. Parser le message
                data = json.loads(message.body.decode())
                id_categorie = data.get('id_categorie')
                source = data.get('source', 'BO')
                is_reset = data.get('is_reset', False)

                if not id_categorie:
                    raise ValueError("id_categorie manquant dans le message.")

                # 2. Déduplication locale (par réplica uniquement)
                if await self._is_duplicate_category(str(id_categorie)):
                    logger.warning(f"[CAT-{id_categorie}] ⚠️ Catégorie BO déjà en cours sur ce réplica - message ignoré")
                    await message.ack()
                    return

                category_locked = True

                # 3. Traitement principal
                logger.info(f"[CAT-{id_categorie}] 📥 Début traitement BO (source={source})")

                request = RequestEquivalenceBO(id_categorie=id_categorie, source=source, is_reset=is_reset)
                api_client = HelloProAPIClient()
                generator = EquivalenceGenerator(api_client)

                try:
                    result = await generator.generate_equivalences_bo(request)
                    if generator.tracking_file:
                        logger.info(f"[CAT-{id_categorie}] 📁 Tracking BO: {generator.tracking_file}")
                finally:
                    await generator.close()

                # 4. Succès - ACK uniquement (PAS de publication aval)
                await message.ack()
                logger.info(f"[CAT-{id_categorie}] ✅ Équivalence BO terminée ({result.total_processed} traité(s))")

            except (json.JSONDecodeError, ValueError) as e:
                # Erreur de parsing - pas de retry
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                logger.error(f"{cat_prefix}❌ Erreur permanente (parsing) BO: {e}")
                headers = DLQProperties.create_dlq_headers(e, "qc-equivalence-bo", 0, message)
                await self.channel.default_exchange.publish(
                    aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key=self.dead_letter_queue_name
                )
                await message.ack()

            except Exception as e:
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                retry_count = self._get_retry_count(message)
                error_str = str(e)

                logger.error(f"{cat_prefix}❌ Exception BO: {error_str}")

                if self._is_transient_error(e) and retry_count < MAX_RETRIES:
                    logger.warning(f"{cat_prefix}⚠️ Erreur transitoire BO (essai {retry_count + 1}/{MAX_RETRIES}), retry prévu")
                    await message.nack(requeue=False)
                else:
                    logger.error(f"{cat_prefix}❌ Échec définitif BO après {retry_count + 1} tentative(s): {error_str}")
                    headers = DLQProperties.create_dlq_headers(e, "qc-equivalence-bo", retry_count, message)
                    await self.channel.default_exchange.publish(
                        aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                        routing_key=self.dead_letter_queue_name
                    )
                    await message.ack()

            finally:
                if category_locked and id_categorie:
                    await self._release_category(str(id_categorie))

    async def _process_with_semaphore(self, message: AbstractIncomingMessage):
        """Wrapper qui gère le semaphore et le tracking des tâches actives."""
        task = asyncio.current_task()
        self._active_tasks.add(task)
        try:
            async with self.semaphore:
                await self.process_message(message)
        finally:
            self._active_tasks.discard(task)

    async def start_consuming(self):
        """Mode streaming: traite les messages immédiatement dès leur arrivée."""
        await self.connect()
        logger.info(f"👂 QC-Equivalence-BO: En attente sur {self.queue_name} (streaming)")
        logger.info(f"🚀 Configuration: max_concurrency={settings.MAX_CONCURRENCY}")

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                asyncio.create_task(self._process_with_semaphore(message))
                logger.info(f"📨 Message BO reçu - Tâches actives: {len(self._active_tasks)}/{settings.MAX_CONCURRENCY}")

    async def close(self):
        """Ferme proprement le consumer en attendant les tâches en cours."""
        if self._active_tasks:
            logger.info(f"⏳ Attente de {len(self._active_tasks)} tâches BO en cours...")
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        if self.connection:
            await self.connection.close()
