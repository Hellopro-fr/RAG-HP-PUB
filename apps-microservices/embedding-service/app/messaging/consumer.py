import aio_pika
import json
import asyncio
import logging
from embedding_service.messaging.publisher import Publisher
from embedding_service.core.processor import embed_input_data
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3
RETRY_TTL_MS = 30000

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher, **kwargs):
        """
        Initialise le consumer avec une logique de retry et DLQ.
        """
        self.connection = connection
        self.publisher = publisher
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        self.queue_name = 'embedding_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        print("✅ Consumer initialisé.")

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare toutes les files d'attente et les échanges nécessaires."""
        
        # --- 1. Infrastructure pour les échecs FINALS (Dead-Letter Queue) ---
        dlx = await channel.declare_exchange(self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        # --- 2. Infrastructure pour les tentatives (Retry Queue) ---
        retry_exchange = await channel.declare_exchange(self.retry_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
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

        # --- 3. Configuration de la Queue Principale ---
        exchange = await channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        main_queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': self.retry_exchange,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await main_queue.bind(exchange, self.routing_key)
        return main_queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _process_message_task(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Traite un seul message avec logique de retry/dlq.
        Utilise un pattern ACK/NACK manuel avec un filet de sécurité
        garantissant que chaque message est toujours acquitté ou rejeté.
        """
        # Utilisation du context manager `process` de aio_pika pour s'assurer
        # de ne jamais laisser un message en "unacknowledged" même en cas de crash sévère.
        async with message.process(ignore_processed=True):
            try:
                input_data = json.loads(message.body)
                print(f"\n📥 Embedding-Service: Message reçu pour la collection '{input_data.get('collection', 'inconnue')}'.")

                # 1. Appelle la logique métier PURE avec un timeout global
                output_message = await asyncio.wait_for(
                    embed_input_data(input_data),
                    timeout=120.0
                )
                
                # 2. Utilise le publisher (qui possède maintenant son propre canal dédié)
                await self.publisher.publish_message(output_message)

                # 3. Acquitte le message original
                await message.ack()

            except (json.JSONDecodeError, ValueError) as e:
                # Erreur permanente: le message est invalide.
                print(f"❌ Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}")
                await self._send_to_dlq(message, e, 0)
                await message.ack()

            except asyncio.TimeoutError as e:
                # Timeout spécifique pour éviter le gel du loop
                retry_count = self._get_retry_count(message)
                if retry_count < MAX_RETRIES:
                    print(f"⏱️ Timeout après 120s (essai {retry_count + 1}/{MAX_RETRIES + 1}). Message renvoyé pour une nouvelle tentative.")
                    await message.nack(requeue=False) # NACK pour retry via DLX
                else:
                    print(f"⏱️ Échec (Timeout) après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale.")
                    await self._send_to_dlq(message, Exception("Timeout de traitement (>120s)"), MAX_RETRIES)
                    await message.ack()

            except Exception as e:
                # Erreur potentiellement transitoire.
                retry_count = self._get_retry_count(message)
                if retry_count < MAX_RETRIES:
                    print(f"❌ Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES + 1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                    await message.nack(requeue=False) # NACK pour retry via DLX
                else:
                    print(f"❌ Échec après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale. Erreur: {e}")
                    await self._send_to_dlq(message, e, MAX_RETRIES)
                    await message.ack()

            except BaseException as e:
                # Filet de sécurité ultime
                print(f"🔴 ERREUR CRITIQUE inattendue dans le traitement du message. NACK avec requeue. Erreur: {e}")
                try:
                    await message.nack(requeue=True)
                except Exception:
                    pass  # Rien de plus à faire
    
    async def _send_to_dlq(self, message: aio_pika.abc.AbstractIncomingMessage, error: Exception, retry_count: int):
        # C'est OK d'ouvrir un canal temporaire pour la DLQ car c'est un chemin d'erreur rare
        async with self.connection.channel() as channel:
            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
            dlq_headers = DLQProperties.create_dlq_headers(error, 'embedding-service', retry_count, message)
            await dlx.publish(
                aio_pika.Message(
                    body=message.body,
                    headers=dlq_headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=self.routing_key
            )

    async def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        Traite les messages séquentiellement (inline await) pour garantir
        que chaque message est entièrement traité avant de passer au suivant.
        Avec prefetch_count=10, RabbitMQ pré-livre les messages dans le buffer du canal.
        """
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=10)
        
        queue = await self._setup_queues(channel)
        
        print("👂 Embedding-Service: En attente de messages...")
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await self._process_message_task(message)