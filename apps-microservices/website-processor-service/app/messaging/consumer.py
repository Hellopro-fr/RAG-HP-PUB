import aio_pika
import json
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from website_processor_service.messaging.publisher import Publisher
from website_processor_service.core.processor import process_website_data_for_embedding
from common_utils.autres.DLQProperties import DLQProperties

from common_utils.metrics.prometheus import measure_processing_time

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.executor = ThreadPoolExecutor()
        
        self.exchange_name = 'data_exchange_siteweb'
        self.routing_key = 'new_data.website'
        self.queue_name = 'website_processing_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        logging.info("✅ Consumer initialisé.")

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

    @measure_processing_time(service_name="website-processor-service")
    async def _instrumented_processing_logic(self, message: aio_pika.abc.AbstractIncomingMessage):
        """A new helper function containing the logic to be decorated."""
        data = json.loads(message.body)
        website_data = data.get('data', {})
        bdd = data.get('database', "qdrant")

        if not website_data or not website_data.get('text'):
            raise ValueError("Données invalides (contenu vide ou 'text' manquant).")

        logging.info(f"\n📥 Website-Processor: Message reçu pour URL: {website_data.get('url', 'URL inconnue')}")
        
        loop = asyncio.get_running_loop()
        output_message = await loop.run_in_executor(
            self.executor, process_website_data_for_embedding, website_data, bdd
        )
        
        routing_key = 'data.ready_for_templating' if not output_message.get("data", {}).get("page_type") else 'data.ready_for_embedding'
        output_message['routing_key'] = routing_key
        
        async with self.connection.channel() as channel:
            await self.publisher.publish_message(output_message, channel)


    async def _process_message_task(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Tâche pour traiter un seul message, y compris la logique de retry/dlq."""
        url = "URL not available"
        try:
            # Attempt to get URL for logging, even if processing fails
            try:
                data = json.loads(message.body)
                url = data.get('data', {}).get('url', 'URL not found in data')
            except json.JSONDecodeError:
                url = "URL not available (JSON decode error)"

            # We call our new decorated function
            await self._instrumented_processing_logic(message)
            await message.ack()

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message ne sera jamais valide.
            logging.error(f"❌ Website-Processor: Erreur permanente pour URL: {url}. Message envoyé à la DLQ finale. Erreur: {e}")
            await self._send_to_dlq(message, e, 0)
            await message.ack()

        except Exception as e:
            retry_count = self._get_retry_count(message)
            if retry_count < MAX_RETRIES:
                logging.warning(f"⚠️ Website-Processor: Erreur transitoire pour URL: {url} (essai {retry_count + 1}/{MAX_RETRIES+1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                await message.nack(requeue=False)
            else:
                logging.error(f"❌ Website-Processor: Échec après {MAX_RETRIES + 1} tentatives pour URL: {url}. Message envoyé à la DLQ finale. Erreur: {e}")
                await self._send_to_dlq(message, e, MAX_RETRIES)
                await message.ack()

    async def _send_to_dlq(self, message: aio_pika.abc.AbstractIncomingMessage, error: Exception, retry_count: int):
        async with self.connection.channel() as channel:
            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
            dlq_headers = DLQProperties.create_dlq_headers(error, 'website-processor-service', retry_count, message)
            await dlx.publish(
                aio_pika.Message(
                    body=message.body,
                    headers=dlq_headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=self.routing_key
            )

    async def start_consuming(self):
        """Démarre le consumer."""
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=10) # Traiter jusqu'à 10 messages en parallèle
        
        queue = await self._setup_queues(channel)
        
        logging.info("👂 Website-Processor: En attente de messages...")
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                # Lance le traitement de chaque message comme une tâche de fond
                # Le service peut ainsi continuer à recevoir des messages pendant que les autres sont traités.
                asyncio.create_task(self._process_message_task(message))