import aio_pika
import json
import asyncio
import logging
import traceback

from document_database_qdrant_service.messaging.publisher import Publisher  # Importe notre publisher local
from document_database_qdrant_service.core.processor import insertion_data # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher

        # Todo: à vérifier si le nom de la queue est correct
        # self.exchange_name = 'document_embedded_data_exchange' # Todo à modifier si pipeline normal
        self.exchange_name = 'document_embedded_data_exchange'
        self.routing_key = 'data.document.ready_for_insertion'
        self.queue_name = 'insertion_document_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        logger.info("Consumer initialisé.")

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
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _process_message_task(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Tâche pour traiter un seul message, y compris la logique de retry/dlq."""
        try:
            document_data = json.loads(message.body)
            logger.info("Processing document fichier_source=%s", document_data.get("data", [{}])[0].get("fichier_source", "unknown") if isinstance(document_data.get("data"), list) and document_data.get("data") else "unknown")

            if not document_data:
                raise ValueError("Données invalides (contenu vide ou 'document_data' manquant).")

            output_message = await insertion_data(document_data)

            await self.publisher.publish_message(output_message, self._publish_channel)

            await message.ack()

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Database-Document-Processor: Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}", exc_info=True)
            await self._send_to_dlq(message, e, 0)
            await message.ack()

        except Exception as e:
            retry_count = self._get_retry_count(message)
            stack = traceback.format_exc()
            if retry_count < MAX_RETRIES:
                logger.error(f"Database-Document-Processor: Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES+1}). Erreur: {e}\n{stack}")
                await message.nack(requeue=False)
            else:
                logger.error(f"Database-Document-Processor: Échec après {MAX_RETRIES + 1} tentatives. Erreur: {e}", exc_info=True)
                await self._send_to_dlq(message, e, MAX_RETRIES)
                await message.ack()

    async def _send_to_dlq(self, message: aio_pika.abc.AbstractIncomingMessage, error: Exception, retry_count: int):
        try:
            async with self.connection.channel() as channel:
                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                dlq_headers = DLQProperties.create_dlq_headers(error, 'Database-Document-Processor-service', retry_count, message)
                await dlx.publish(
                    aio_pika.Message(
                        body=message.body,
                        headers=dlq_headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    ),
                    routing_key=self.routing_key
                )
        except Exception as dlq_error:
            logger.critical(
                "Échec de publication vers la DLQ: %s. Message original perdu: %s",
                repr(dlq_error),
                message.body[:500] if message.body else "N/A",
                exc_info=True,
            )

    async def start_consuming(self):
        """Démarre le consumer avec contrôle du parallélisme et gestion des erreurs."""

        # 1. Crée le channel de consommation et configure le prefetch
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=10)

        # 2. Crée un channel dédié à la publication (évite l'ouverture d'un channel par message)
        self._publish_channel = await self.connection.channel()

        # 3. Déclare et bind les queues/exchanges
        queue = await self._setup_queues(channel)
        
        # 3. Crée un semaphore pour limiter le nombre de traitements simultanés
        semaphore = asyncio.Semaphore(10)
        
        async def safe_process(message):
            """Wrapper pour limiter le parallélisme et capturer les erreurs."""
            async with semaphore:
                try:
                    await self._process_message_task(message)
                except Exception as e:
                    logger.error(f"Erreur lors du traitement du message: {e}", exc_info=True)
                    # NACK sans requeue — le DLX de la queue route vers retry_exchange
                    await message.nack(requeue=False)
        
        # 4. Commence à consommer les messages
        logger.info("Database-Document-Processor: En attente de messages...")
        await queue.consume(lambda message: asyncio.create_task(safe_process(message)))

