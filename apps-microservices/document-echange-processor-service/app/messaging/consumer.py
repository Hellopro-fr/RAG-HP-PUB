
import aio_pika
import json
import asyncio
from concurrent.futures import ProcessPoolExecutor

from document_echange_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from document_echange_processor_service.core.processor import process_document_data_for_templating # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.executor = ProcessPoolExecutor(max_workers=1)
        
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
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _process_message_task(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Tâche pour traiter un seul message, y compris la logique de retry/dlq."""
        try:
            data = json.loads(message.body)
            document_data = data.get('data', {})
            bdd = data.get('database', "milvus")

            if not document_data or not document_data.get('document'):
                raise ValueError("Données invalides (contenu vide ou 'document' manquant).")

            print(f"\n📥 Document-Processor: Message reçu pour URL: {document_data.get('fichier_source', 'Source inconnue')}")
            
            # loop = asyncio.get_running_loop()
            # output_message = await loop.run_in_executor(
            #     self.executor, process_document_data_for_templating, document_data, bdd
            # )
            output_message = await process_document_data_for_templating(document_data, bdd, self.executor)
            
            routing_key = 'data.ready_for_templating' if not output_message.get("data", {}).get("page_type") else 'data.ready_for_embedding'
            output_message['routing_key'] = routing_key
            
            async with self.connection.channel() as channel:
                await self.publisher.publish_message(output_message, channel)
            
            await message.ack()

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message ne sera jamais valide.
            print(f"❌ Document-Processor: Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}")
            await self._send_to_dlq(message, e, 0)
            await message.ack()

        except Exception as e:
            retry_count = self._get_retry_count(message)
            if retry_count < MAX_RETRIES:
                print(f"❌ Document-Processor: Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES+1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                await message.nack(requeue=False)
            else:
                print(f"❌ Document-Processor: Échec après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale. Erreur: {e}")
                await self._send_to_dlq(message, e, MAX_RETRIES)
                await message.ack()

    async def _send_to_dlq(self, message: aio_pika.abc.AbstractIncomingMessage, error: Exception, retry_count: int):
        async with self.connection.channel() as channel:
            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
            dlq_headers = DLQProperties.create_dlq_headers(error, 'Document-processor-service', retry_count, message)
            await dlx.publish(
                aio_pika.Message(
                    body=message.body,
                    headers=dlq_headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=self.routing_key
            )

    async def start_consuming(self):
        """Démarre le consumer avec contrôle du parallélisme et gestion des erreurs."""
        
        # 1. Crée le channel et configure le prefetch
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=2)  # Nombre maximum de messages traités en parallèle
        
        # 2. Déclare et bind les queues/exchanges
        queue = await self._setup_queues(channel)
        
        # 3. Crée un semaphore pour limiter le nombre de traitements simultanés
        semaphore = asyncio.Semaphore(2)
        
        async def safe_process(message):
            """Wrapper pour limiter le parallélisme et capturer les erreurs."""
            async with semaphore:
                try:
                    await self._process_message_task(message)
                except Exception as e:
                    print(f"⚠️ Erreur lors du traitement du message: {e}")
                    # NACK pour remettre le message en queue
                    await message.nack(requeue=True)
        
        # 4. Commence à consommer les messages
        print("👂 Document-Processor: En attente de messages...")
        await queue.consume(lambda message: asyncio.create_task(safe_process(message)))

