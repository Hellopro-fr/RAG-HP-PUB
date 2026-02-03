import aio_pika
import json
import logging
from image_download_service.core.downloader import Downloader
from common_utils.autres.DLQProperties import DLQProperties

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000


class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le consumer avec une logique de retry et DLQ.
        Utilise RobustConnection pour une reconnexion automatique.
        NOTE: Publisher supprimé car les messages ne sont pas consommés.
        """
        self.connection = connection
        self.downloader = Downloader()
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'data_exchange_produits'
        self.routing_key = 'new_data.product'
        self.queue_name = 'image_download_tasks_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        logger.info("✅ Consumer initialisé (aio_pika RobustConnection).")

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare toutes les files d'attente et les échanges nécessaires."""
        
        # --- 1. Infrastructure pour les échecs FINALS (Dead-Letter Queue) ---
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        # --- 2. Infrastructure pour les tentatives (Retry Queue) ---
        retry_exchange = await channel.declare_exchange(
            self.retry_exchange, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
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
        exchange = await channel.declare_exchange(
            self.exchange_name, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
        main_queue = await channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                'x-dead-letter-exchange': self.retry_exchange,
                'x-dead-letter-routing-key': self.routing_key
            }
        )
        await main_queue.bind(exchange, self.routing_key)
        
        logger.info(f"✅ Queue '{self.queue_name}' declared and bound to '{self.exchange_name}'.")
        return main_queue

    def _get_retry_count(self, message: aio_pika.abc.AbstractIncomingMessage) -> int:
        """Récupère le nombre de tentatives depuis les headers x-death."""
        if message.headers and 'x-death' in message.headers:
            for death in message.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    async def _on_message_callback(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Callback asynchrone pour traiter un message avec logique de retry/DLQ.
        """
        async with message.process():
            product_id = "unknown"
            try:
                data = json.loads(message.body)
                product_data = data.get("data", data)
                product_id = product_data.get('id_produit', 'unknown')
                
                logger.info(f"📥 Message reçu pour le produit '{product_id}'.")
                
                # --- FILTER: Process only 'SITEWEB' or 'test_web' source ---
                source = product_data.get("source") or data.get("origin")
                
                if source not in ["SITEWEB", "test_web"]:
                    logger.info(f"⏭️ Skipping product {product_id}: Source '{source}' not in allowed list.")
                    return  # ACK automatique via context manager
                
                logger.info(f"🔄 Processing product {product_id} (Source: {source})")
                
                # Appel async natif - pas besoin de wrapper synchrone !
                result_data = await self.downloader.process_product(product_data)
                
                # Log si l'image existait déjà (déduplication)
                if result_data.get("skipped"):
                    logger.info(f"⏭️ Image already exists for {product_id}, skipped download.")
                elif result_data.get("processed_images"):
                    logger.info(f"✅ Downloaded {len(result_data['processed_images'])} image(s) for {product_id}")
                else:
                    logger.warning(f"⚠️ No images processed for {product_id}")

            except (json.JSONDecodeError, ValueError) as e:
                # Erreur permanente: le message est invalide.
                logger.error(f"❌ Erreur permanente pour {product_id}. Message envoyé à la DLQ finale. Erreur: {e}")
                await self._send_to_dlq(message, e, 0)

            except Exception as e:
                # Erreur potentiellement transitoire.
                retry_count = self._get_retry_count(message)
                if retry_count < MAX_RETRIES:
                    logger.warning(f"❌ Erreur transitoire pour {product_id} (essai {retry_count + 1}/{MAX_RETRIES + 1}). Retrying. Erreur: {e}")
                    await message.nack(requeue=False)  # NACK pour retry via DLX
                else:
                    logger.error(f"❌ Échec après {MAX_RETRIES + 1} tentatives pour {product_id}. Envoi à la DLQ. Erreur: {e}")
                    await self._send_to_dlq(message, e, MAX_RETRIES)
    
    async def _send_to_dlq(self, message: aio_pika.abc.AbstractIncomingMessage, error: Exception, retry_count: int):
        """Envoie le message à la Dead-Letter Queue avec les métadonnées d'erreur."""
        try:
            async with self.connection.channel() as channel:
                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                
                # Utiliser DLQProperties de common_utils
                dlq_headers = DLQProperties.create_dlq_headers(
                    error, 
                    'image-download-service', 
                    retry_count, 
                    message
                )
                
                await dlx.publish(
                    aio_pika.Message(
                        body=message.body,
                        headers=dlq_headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                    ),
                    routing_key=self.routing_key
                )
                logger.info(f"📤 Message envoyé à la DLQ: {self.dead_letter_queue_name}")
        except Exception as dlq_error:
            logger.error(f"❌ Erreur lors de l'envoi à la DLQ: {dlq_error}")

    async def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        RobustConnection gère automatiquement les reconnexions.
        """
        channel = await self.connection.channel()
        
        # Traiter 1 message à la fois pour les tâches longues (téléchargement d'images)
        await channel.set_qos(prefetch_count=1)
        
        queue = await self._setup_queues(channel)
        
        logger.info("👂 Image-Download-Service: En attente de messages...")
        await queue.consume(self._on_message_callback)
