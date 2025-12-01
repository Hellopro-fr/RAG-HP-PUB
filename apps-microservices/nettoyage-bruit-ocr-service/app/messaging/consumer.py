import aio_pika
import os
import time
import json
import asyncio
import aiormq
import traceback

from nettoyage_bruit_ocr_service.messaging.publisher import Publisher  # Importe notre publisher local
from nettoyage_bruit_ocr_service.core.processor import nettoyer_bruits_ocr # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative
BATCH_SIZE = 1
BATCH_TIMEOUT_SECONDS = 2.0
class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        
        self.message_buffer = asyncio.Queue()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_ocr_cleaning'
        self.queue_name = 'nettoyage_bruit_ocr_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        # 🔥 Canal de consommation stocké
        self.consumer_channel = None
        self._keep_alive_task = None
        
        print("✅ Consumer initialisé.")

    async def _keep_channel_alive(self):
        """
        Tâche de fond qui garde le canal de consommation actif
        en envoyant des opérations légères régulièrement.
        """
        print("💓 Tâche keep-alive du canal démarrée")
        
        while True:
            try:
                await asyncio.sleep(30)  # Toutes les 30 secondes
                
                if self.consumer_channel and not self.consumer_channel.is_closed:
                    # 🔥 Opération légère pour maintenir le canal actif
                    # Déclarer une exchange qui existe déjà ne coûte rien
                    await self.consumer_channel.get_exchange(
                        self.exchange_name, 
                        ensure=False  # Ne pas créer si n'existe pas
                    )
                    print("💓 Heartbeat canal envoyé")
                else:
                    print("⚠️  Canal consumer fermé ou inexistant")
                    
            except asyncio.CancelledError:
                print("💓 Tâche keep-alive arrêtée")
                break
            except Exception as e:
                print(f"⚠️  Erreur keep-alive: {e}")
                # Continuer malgré l'erreur

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

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

        exchange = await channel.declare_exchange(
            self.exchange_name, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
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

    async def batch_processor(self):
        """Tâche de fond qui traite les messages par lots de manière asynchrone."""
        print("⚙️  Processeur de batch démarré. En attente de messages...")
        
        while True:
            batch = []
            try:
                first_message = await self.message_buffer.get()
                batch.append(first_message)

                while len(batch) < BATCH_SIZE:
                    try:
                        message = await asyncio.wait_for(
                            self.message_buffer.get(), 
                            timeout=BATCH_TIMEOUT_SECONDS
                        )
                        batch.append(message)
                    except asyncio.TimeoutError:
                        break
                        
            except asyncio.CancelledError:
                print("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            print(f"⚙️  Traitement d'un batch de {batch_size} messages...")
            messages_to_process = [json.loads(msg.body) for msg in batch]
            
            try:
                # 🔥 Traitement dans les threads - l'event loop reste libre
                processed_results = await nettoyer_bruits_ocr(messages_to_process)
                
                # 🔥 Ouvrir un NOUVEAU canal dédié pour les ACK/publications
                # Ne pas réutiliser le canal consumer
                async with self.connection.channel() as processing_channel:
                    for i, result in enumerate(processed_results):
                        original_message = batch[i]
                        
                        try:
                            if 'metric_payload' in result:
                                await self.publisher.publish_metric_message(
                                    result['metric_payload'], 
                                    processing_channel
                                )

                            if result['status'] == 'success':
                                await self.publisher.publish_message(
                                    result['processed_message'], 
                                    processing_channel
                                )
                                # 🔥 ACK via le message original (qui connaît son canal)
                                await original_message.ack()
                            else:
                                print(f"   -> Échec pour message (tag: {original_message.delivery_tag})")
                                dlx = await processing_channel.get_exchange(
                                    self.dead_letter_exchange, 
                                    ensure=True
                                )
                                
                                dlq_headers = DLQProperties.create_dlq_headers(
                                    Exception(result['error_message']), 
                                    'nettoyage-bruit-ocr-service', 
                                    MAX_RETRIES, 
                                    original_message
                                )
                                
                                await dlx.publish(
                                    aio_pika.Message(
                                        body=original_message.body,
                                        headers=dlq_headers,
                                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                    ),
                                    routing_key=self.routing_key
                                )
                                await original_message.ack()
                        
                        except aiormq.exceptions.ChannelInvalidStateError:
                            print(f"⚠️  Canal fermé pour message {i}. Messages restants seront re-délivrés.")
                            break

            except (aiormq.exceptions.ChannelInvalidStateError,
                    aiormq.exceptions.ConnectionClosed) as e:
                print(f"⚠️  Connexion perdue: {e}")
                print("   -> Messages non-ACK seront re-délivrés automatiquement.")
                
            except Exception as e:
                print(f"❌ ERREUR sur le batch: {e}")
                traceback.print_exc()
                
                # Tentative de NACK
                for msg in batch:
                    try:
                        await msg.nack(requeue=False)
                    except Exception:
                        pass
                        
            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                print(f"🏁 Batch de {batch_size} message(s) terminé en {duration:.4f}s")
    
    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Callback léger qui met les messages dans un buffer asynchrone."""
        await self.message_buffer.put(message)

    async def start_consuming(self):
        """Démarre le consumer et la tâche de traitement de batch."""
        # 🔥 Créer et stocker le canal consumer
        self.consumer_channel = await self.connection.channel()
        await self.consumer_channel.set_qos(prefetch_count=BATCH_SIZE)
        
        queue = await self._setup_queues(self.consumer_channel)
        
        # 🔥 Démarrer la tâche keep-alive
        self._keep_alive_task = asyncio.create_task(self._keep_channel_alive())
        
        # Démarrer la tâche de fond qui traitera les batches
        asyncio.create_task(self.batch_processor())
        
        # Commencer à consommer les messages et à les mettre dans le buffer
        print("👂 Nettoyage-bruit-ocr-service: En attente de messages...")
        await queue.consume(self._on_message)
    
    async def stop(self):
        """Arrêt propre du consumer."""
        print("🛑 Arrêt du consumer...")
        
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass
        
        if self.consumer_channel and not self.consumer_channel.is_closed:
            await self.consumer_channel.close()
        
        print("✅ Consumer arrêté proprement")