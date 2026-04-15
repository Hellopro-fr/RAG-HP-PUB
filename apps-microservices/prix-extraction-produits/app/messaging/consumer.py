import json
import logging
import asyncio
from typing import Set
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from common_utils.autres.CollectionName import CollectionName, RoutingKeys
from app.core.credentials import settings
from app.messaging.publisher import Publisher
from app.core.prix_extractor import PrixExtractor
from app.core.api_client import HelloProAPIClient
from app.core.utils import process_product_data_for_embedding
from app.schemas.prix_extraction import RequestProcessus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000


class Consumer:
    """Async Consumer en mode streaming pour le service prix-extraction-produits."""

    def __init__(self, publisher: Publisher):
        self.publisher = publisher
        self.connection = None
        self.channel = None
        self.queue = None
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self._active_tasks: Set[asyncio.Task] = set()
        self._processing_categories: Set[str] = set()
        self._categories_lock = asyncio.Lock()

        # Nomenclature centralisée — CollectionName.PRIX_PRODUIT
        _collection          = CollectionName.PRIX_PRODUIT          # "prix_produits"
        self.exchange_name   = f'data_exchange_{_collection}'       # data_exchange_prix_produits
        self.routing_key     = RoutingKeys[_collection]             # new_data.prix_produit
        self.queue_name      = f'{_collection}_processing_queue'    # prix_produits_processing_queue
        self.retry_exchange  = f'retry_exchange_{_collection}'      # retry_exchange_prix_produits
        self.retry_queue_name        = f'{self.queue_name}_retry'
        self.dead_letter_exchange    = f'dead_letter_exchange_{_collection}'
        self.dead_letter_queue_name  = f'{self.queue_name}_dlq'

    async def connect(self):
        logger.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)
        await self.publisher.setup(self.channel)
        await self._setup_infrastructure()
        logger.info("✅ Prix-Extraction-Produits Consumer initialized (streaming mode)")

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
        async with self._categories_lock:
            if cat_id in self._processing_categories:
                return True
            self._processing_categories.add(cat_id)
            return False

    async def _release_category(self, cat_id: str):
        async with self._categories_lock:
            self._processing_categories.discard(cat_id)
            logger.debug(f"[CAT-{cat_id}] Catégorie libérée")

    async def process_message(self, message: AbstractIncomingMessage):
        async with message.process(ignore_processed=True):
            id_categorie = None
            category_locked = False

            try:
                all_data = json.loads(message.body.decode())
                data = all_data.get('data')
                id_categorie = data.get('id_categorie')
                is_reset = data.get('is_reset', False)

                if not id_categorie:
                    raise ValueError("id_categorie manquant dans le message.")

                if await self._is_duplicate_category(str(id_categorie)):
                    logger.warning(f"[CAT-{id_categorie}] ⚠️ Catégorie déjà en cours - ignoré")
                    await message.ack()
                    return

                category_locked = True
                logger.info(f"[CAT-{id_categorie}] 📥 Début traitement extraction prix produits")

                request = RequestProcessus(id_categorie=id_categorie, is_reset=is_reset)
                api_client = HelloProAPIClient()

                # Callback pour publier les résultats de chaque batch vers embedding
                published_count = 0
                async def on_batch_publish(batch_results, cat_id):
                    nonlocal published_count
                    count = 0
                    for item_result in batch_results:
                        if item_result.status == "success" and item_result.prix_data:
                            try:
                                embedding_message = process_product_data_for_embedding(
                                    prix_data=item_result.prix_data,
                                    id_categorie=cat_id,
                                    source=item_result.source,
                                    origin="prix-extraction-produits"
                                )
                                await self.publisher.publish_message(embedding_message)
                                count += 1
                                published_count += 1
                            except Exception as pub_err:
                                logger.warning(f"[CAT-{cat_id}] ⚠️ Publication skip item {item_result.item_id}: {pub_err}")
                    return count

                extractor = PrixExtractor(api_client, on_batch_publish=on_batch_publish)

                try:
                    result = await extractor.extract_prix_for_category(request)
                    if extractor.tracking_file:
                        logger.info(f"[CAT-{id_categorie}] 📁 Tracking: {extractor.tracking_file}")
                finally:
                    await extractor.close()

                logger.info(f"[CAT-{id_categorie}] 📊 Bilan: {result.success}/{result.total_chunks} succès, {result.errors} erreurs, {published_count} messages publiés vers embedding")
                await message.ack()
                logger.info(f"[CAT-{id_categorie}] ✅ Terminé")

            except (json.JSONDecodeError, ValueError) as e:
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                logger.error(f"{cat_prefix}❌ Erreur permanente: {e}")
                headers = DLQProperties.create_dlq_headers(e, "prix-extraction-produits", 0, message)
                await self.channel.default_exchange.publish(aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=self.dead_letter_queue_name)
                await message.ack()

            except Exception as e:
                cat_prefix = f"[CAT-{id_categorie}] " if id_categorie else ""
                retry_count = self._get_retry_count(message)
                logger.error(f"{cat_prefix}❌ Exception: {e}")

                if self._is_transient_error(e) and retry_count < MAX_RETRIES:
                    logger.warning(f"{cat_prefix}⚠️ Erreur transitoire (essai {retry_count + 1}), retry")
                    await message.nack(requeue=False)
                else:
                    logger.error(f"{cat_prefix}❌ Échec définitif après {retry_count + 1} tentative(s)")
                    headers = DLQProperties.create_dlq_headers(e, "prix-extraction-produits", retry_count, message)
                    await self.channel.default_exchange.publish(aio_pika.Message(body=message.body, headers=headers, delivery_mode=aio_pika.DeliveryMode.PERSISTENT), routing_key=self.dead_letter_queue_name)
                    await message.ack()

            finally:
                if category_locked and id_categorie:
                    await self._release_category(str(id_categorie))

    async def _process_with_semaphore(self, message: AbstractIncomingMessage):
        task = asyncio.current_task()
        self._active_tasks.add(task)
        try:
            async with self.semaphore:
                await self.process_message(message)
        finally:
            self._active_tasks.discard(task)

    async def start_consuming(self):
        await self.connect()
        logger.info(f"👂 Prix-Extraction-Produits: En attente sur {self.queue_name} (streaming)")
        logger.info(f"🚀 Configuration: max_concurrency={settings.MAX_CONCURRENCY}")
        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                asyncio.create_task(self._process_with_semaphore(message))
                logger.info(f"📨 Message reçu - Tâches: {len(self._active_tasks)}/{settings.MAX_CONCURRENCY}")

    async def close(self):
        if self._active_tasks:
            logger.info(f"⏳ Attente de {len(self._active_tasks)} tâches...")
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        if self.connection:
            await self.connection.close()
