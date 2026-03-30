import os
import asyncio
import json
import aio_pika
import aiohttp
import aiormq
from common_utils.autres.DLQProperties import DLQProperties

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
DEEPSEEK_METRICS_COLLECTOR_URL = os.environ.get("DEEPSEEK_METRICS_COLLECTOR_URL") # e.g., "http://api-gateway:8500/v1/log-metrics"

# --- Adaptive Batching Configuration ---
MAX_BATCH_SIZE = 50  # L'objectif maximum de taille de batch.
MIN_BATCH_SIZE = 5    # La taille minimale après détection d'un blocage.
SUCCESS_THRESHOLD_FOR_INCREASE = 5 # Nombre de succès consécutifs avant d'augmenter la taille.
BATCH_TIMEOUT_SECONDS = 15.0 # Temps d'attente fixe avant chaque envoi
MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

# --- HTTP Headers to pass through WAF ---
HTTP_HEADERS = {
    'User-Agent': 'deepseek-metrics-collector/1.0 (internal-service)',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
}

SERVICE_NAME = 'deepseek-metrics-collector-service'

class MetricsConsumer:
    def __init__(self, connection: aio_pika.RobustConnection):
        self.connection = connection
        self.metrics_buffer = asyncio.Queue()
        self._shutdown = asyncio.Event()

        # --- State for Adaptive Batching ---
        self.current_batch_size = MAX_BATCH_SIZE
        self.successful_sends_in_a_row = 0

        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'metrics.deepseek.result'
        self.queue_name = 'deepseek_metrics_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'


    async def setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare toutes les files d'attente et les échanges nécessaires pour la résilience."""

        # DLQ Finale
        dlx = await channel.declare_exchange(self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True)
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        # File d'attente de Retry
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

        # File d'attente principale
        exchange = await channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': self.retry_exchange,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await queue.bind(exchange, self.routing_key)

        return queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _safe_ack(self, msg: aio_pika.abc.AbstractIncomingMessage) -> bool:
        """ACK with protection against dead channels."""
        try:
            await msg.ack()
            return True
        except (aiormq.exceptions.ChannelInvalidStateError, RuntimeError) as e:
            print(f"      ⚠️  ACK échoué (tag: {msg.delivery_tag}): {e}")
            return False

    async def _safe_nack(self, msg: aio_pika.abc.AbstractIncomingMessage, requeue: bool = False) -> bool:
        """NACK with protection against dead channels."""
        try:
            await msg.nack(requeue=requeue)
            return True
        except (aiormq.exceptions.ChannelInvalidStateError, RuntimeError) as e:
            print(f"      ⚠️  NACK échoué (tag: {msg.delivery_tag}): {e}")
            return False

    def stop(self):
        """Signal the batch_sender to stop gracefully."""
        self._shutdown.set()

    async def on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Met le message entier dans le buffer pour traitement. Pas d'ack/nack ici."""
        await self.metrics_buffer.put(message)

    async def batch_sender(self):
        """Tâche de fond qui envoie les métriques avec une taille de batch adaptative."""
        print(f"⚙️  Expéditeur de batch démarré. Taille initiale: {self.current_batch_size}, Max: {MAX_BATCH_SIZE}.")
        while not self._shutdown.is_set():
            try:
                await asyncio.sleep(BATCH_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                break

            batch = []
            # Utiliser la taille de batch adaptative actuelle pour collecter les messages
            while len(batch) < self.current_batch_size:
                try:
                    message = self.metrics_buffer.get_nowait()
                    batch.append(message)
                except asyncio.QueueEmpty:
                    break

            if not batch:
                continue

            # Extraire les corps des messages pour l'envoi HTTP
            metrics_to_send = []
            valid_messages_in_batch = []
            for msg in batch:
                try:
                    metrics_to_send.append(json.loads(msg.body))
                    valid_messages_in_batch.append(msg)
                except json.JSONDecodeError:
                    print(f"   -> ERREUR: Impossible de décoder le message métrique: {msg.body}. Le message sera ignoré et ack.")
                    await self._safe_ack(msg)

            if not metrics_to_send:
                continue # Le batch ne contenait que des messages invalides

            print(f"   -> Tentative d'envoi d'un batch de {len(metrics_to_send)} métriques (Taille adaptative: {self.current_batch_size})...")
            try:
                async with aiohttp.ClientSession(headers=HTTP_HEADERS) as session:
                    async with session.post(DEEPSEEK_METRICS_COLLECTOR_URL, json=metrics_to_send) as resp:
                        if resp.status != 200:
                            body = await resp.text()
                            print(f"      ⚠️  HTTP {resp.status} — Response body: {body[:500]}")
                            resp.raise_for_status()

                        print(f"      • [SUCCESS] Batch envoyé. ACK des {len(valid_messages_in_batch)} messages.")
                        for msg in valid_messages_in_batch:
                            await self._safe_ack(msg)

                        # Logique adaptative en cas de succès
                        self.successful_sends_in_a_row += 1
                        if self.successful_sends_in_a_row >= SUCCESS_THRESHOLD_FOR_INCREASE:
                            new_size = self.current_batch_size + (MAX_BATCH_SIZE // 10) # Augmente de 10% du max
                            self.current_batch_size = min(MAX_BATCH_SIZE, new_size)
                            self.successful_sends_in_a_row = 0
                            print(f"      📈 Succès consécutifs. Augmentation de la taille du batch à {self.current_batch_size}.")

            except aiohttp.ClientError as e:
                # Logique adaptative en cas d'échec
                if isinstance(e, aiohttp.ClientResponseError) and e.status == 403:
                    new_size = self.current_batch_size // 2
                    self.current_batch_size = max(MIN_BATCH_SIZE, new_size)
                    print(f"      📉 ERREUR 403 (WAF Block) détectée! Réduction drastique de la taille du batch à {self.current_batch_size}.")

                # Pour toute erreur, on reset le compteur de succès
                self.successful_sends_in_a_row = 0

                print(f"      • [FAILURE] Erreur lors de l'envoi du batch: {e}. Lancement de la procédure de retry/DLQ.")
                await self._handle_failed_batch(valid_messages_in_batch, e)

    async def _handle_failed_batch(self, messages: list, error: Exception):
        """NACK les messages réessayables, publie les épuisés vers la DLQ."""
        for msg in messages:
            retry_count = self._get_retry_count(msg)
            if retry_count < MAX_RETRIES:
                print(f"         - NACK du message (tag: {msg.delivery_tag}) pour nouvelle tentative ({retry_count + 1}/{MAX_RETRIES}).")
                await self._safe_nack(msg, requeue=False)
            else:
                print(f"         - Échec final pour le message (tag: {msg.delivery_tag}). Envoi à la DLQ finale.")
                try:
                    async with self.connection.channel() as channel:
                        dlx = await channel.declare_exchange(
                            self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True
                        )
                        dlq_headers = DLQProperties.create_dlq_headers(
                            error, SERVICE_NAME, MAX_RETRIES, msg
                        )
                        await dlx.publish(
                            aio_pika.Message(
                                body=msg.body,
                                headers=dlq_headers,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                            ),
                            routing_key=self.routing_key
                        )
                        await self._safe_ack(msg)
                except Exception as dlq_err:
                    print(f"         ⚠️  Impossible de publier vers la DLQ: {dlq_err}. Le message sera redelivré par RabbitMQ.")
                    await self._safe_nack(msg, requeue=False)

async def main():
    if not RABBITMQ_URL or not DEEPSEEK_METRICS_COLLECTOR_URL:
        print("❌ ERREUR: RABBITMQ_URL et DEEPSEEK_METRICS_COLLECTOR_URL doivent être définis.")
        exit(1)

    print("🚀 deepseek-metrics-collector-service: Démarrage...")

    while True:
        sender_task = None
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            print("✅ Connecté à RabbitMQ.")

            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=MAX_BATCH_SIZE * 2)

                consumer = MetricsConsumer(connection)
                queue = await consumer.setup_queues(channel)

                # Démarrer la tâche de fond qui enverra les batches
                sender_task = asyncio.create_task(consumer.batch_sender())

                await queue.consume(consumer.on_message)

                print("👂 En attente de messages de métriques...")
                # Si le sender crashe, on sort de la boucle pour reconnecter
                await sender_task

        except (aiormq.exceptions.AMQPConnectionError, ConnectionError) as e:
            print(f"🔴 Erreur de connexion RabbitMQ: {e}. Tentative de reconnexion dans 10 secondes...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"❌ Erreur inattendue: {e}. Redémarrage dans 10 secondes...")
            await asyncio.sleep(10)
        finally:
            if sender_task and not sender_task.done():
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass

if __name__ == '__main__':
    asyncio.run(main())
