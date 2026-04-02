import aio_pika
import os
import time
import json
import asyncio
import aiormq
import traceback

from nettoyage_bruit_ocr_service.messaging.publisher import Publisher
from nettoyage_bruit_ocr_service.core.processor import nettoyer_bruits_ocr
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3
RETRY_TTL_MS = 30000
BATCH_SIZE = 1  # 🔥 1 seul message à la fois
BATCH_TIMEOUT_SECONDS = 0.5  # 🔥 Timeout court

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
        
        # 🔥 Stocker le canal de consommation
        self.consumer_channel = None
        self._keep_alive_task = None
        
        print("✅ Consumer initialisé.")

    async def _keep_channel_alive(self):
        """
        Tâche de fond qui maintient le canal actif.
        Vérifie périodiquement l'état du canal.
        """
        print("💓 Tâche keep-alive du canal démarrée")
        
        heartbeat_count = 0
        
        while True:
            try:
                await asyncio.sleep(30)  # Toutes les 30 secondes
                heartbeat_count += 1
                
                if self.consumer_channel is None:
                    print(f"⚠️  [{heartbeat_count}] Canal consumer inexistant")
                    continue
                    
                if self.consumer_channel.is_closed:
                    print(f"❌ [{heartbeat_count}] Canal consumer FERMÉ !")
                    continue
                
                # 🔥 Essayer plusieurs opérations pour maintenir le canal actif
                try:
                    # Opération 1 : Vérifier l'exchange
                    await self.consumer_channel.get_exchange(
                        self.exchange_name, 
                        ensure=False
                    )
                    print(f"💓 [{heartbeat_count}] Heartbeat OK (canal actif)")
                    
                except aiormq.exceptions.ChannelInvalidStateError:
                    print(f"❌ [{heartbeat_count}] Canal en état invalide !")
                except Exception as e:
                    print(f"⚠️  [{heartbeat_count}] Erreur heartbeat: {type(e).__name__} - {e}")
                        
            except asyncio.CancelledError:
                print("💓 Tâche keep-alive arrêtée")
                break
            except Exception as e:
                print(f"❌ Erreur inattendue dans keep-alive: {e}")
                traceback.print_exc()

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Configure les queues, exchanges et bindings."""
        # Dead Letter Queue
        dlx = await channel.declare_exchange(
            self.dead_letter_exchange, 
            aio_pika.ExchangeType.TOPIC, 
            durable=True
        )
        dlq = await channel.declare_queue(self.dead_letter_queue_name, durable=True)
        await dlq.bind(dlx, self.routing_key)

        # Retry Queue
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

        # Main Queue
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
        
        print(f"✅ Queues configurées: {self.queue_name}, {self.retry_queue_name}, {self.dead_letter_queue_name}")
        return queue

    async def batch_processor(self):
        """Tâche de fond qui traite les messages un par un avec ACK-after."""
        print("Processeur de batch demarre. En attente de messages...")

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
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            print(f"Traitement de {batch_size} message(s)...")

            try:
                messages_to_process = [json.loads(msg.body) for msg in batch]
            except json.JSONDecodeError as e:
                print(f"Erreur de decodage JSON: {e}")
                for msg in batch:
                    await msg.nack(requeue=False)
                continue

            try:
                processed_results = await nettoyer_bruits_ocr(messages_to_process)

                async with self.connection.channel() as channel:
                    for i, result in enumerate(processed_results):
                        msg = batch[i]

                        if 'metric_payload' in result:
                            await self.publisher.publish_metric_message(
                                result['metric_payload'],
                                channel
                            )

                        text = "ok"
                        if "processed_message" in result:
                            if "data" in result['processed_message']:
                                text = result['processed_message'].get("data",{}).get("text","")
                                print(f"Suivi text : {text[:10]}...")

                        if result['status'] == 'success' and text:
                            await self.publisher.publish_message(
                                result['processed_message'],
                                channel
                            )
                            await msg.ack()
                        else:
                            # Send to DLQ with the correct message body
                            try:
                                dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                dlq_headers = DLQProperties.create_dlq_headers(
                                    Exception(result.get('error_message', 'Unknown error')),
                                    'nettoyage-bruit-ocr-service',
                                    MAX_RETRIES,
                                    msg
                                )
                                await dlx.publish(
                                    aio_pika.Message(
                                        body=msg.body,
                                        headers=dlq_headers,
                                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                                    ),
                                    routing_key=self.routing_key
                                )
                            except Exception as dlq_err:
                                print(f"CRITICAL: Impossible d'envoyer en DLQ: {dlq_err}")
                            await msg.ack()

            except Exception as e:
                print(f"ERREUR sur le batch: {e}")
                traceback.print_exc()
                # NACK all messages so they go through retry via DLX
                for msg in batch:
                    try:
                        await msg.nack(requeue=False)
                    except Exception:
                        pass

            finally:
                duration = time.monotonic() - start_time
                print(f"Batch termine en {duration:.2f}s ({duration/60:.2f} min)")
    
    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """
        Callback appelé pour chaque message reçu.
        Met simplement le message dans le buffer pour traitement asynchrone.
        """
        await self.message_buffer.put(message)

    async def start_consuming(self):
        """Démarre le consumer avec prefetch=1 et la tâche keep-alive."""
        print("🚀 Démarrage du consumer...")
        
        # Créer et stocker le canal de consommation
        self.consumer_channel = await self.connection.channel()
        
        # CRITIQUE : Prefetch de 1 seul message
        await self.consumer_channel.set_qos(prefetch_count=1)
        print(f"✅ QoS configuré: prefetch_count=1")
        
        # Setup des queues
        queue = await self._setup_queues(self.consumer_channel)
        
        # Démarrer la tâche keep-alive AVANT de commencer à consommer
        self._keep_alive_task = asyncio.create_task(self._keep_channel_alive())
        print("✅ Tâche keep-alive démarrée")
        
        # Démarrer le processeur de batch
        asyncio.create_task(self.batch_processor())
        print("✅ Processeur de batch démarré")
        
        # 🔥 Logs corrigés pour aio_pika
        print(f"🔍 Canal consumer: {type(self.consumer_channel).__name__}")
        print(f"🔍 Connexion: {type(self.connection).__name__}")
        print(f"🔍 Queue: {queue.name}")
        
        # Commencer à consommer
        print("👂 Nettoyage-bruit-ocr-service: En attente de messages...")
        await queue.consume(self._on_message)
    
    async def stop(self):
        """Arrêt propre du consumer."""
        print("🛑 Arrêt du consumer...")
        
        # Arrêter la tâche keep-alive
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                print("   ✅ Tâche keep-alive arrêtée")
        
        # Fermer le canal consumer
        if self.consumer_channel and not self.consumer_channel.is_closed:
            await self.consumer_channel.close()
            print("   ✅ Canal consumer fermé")
        
        print("✅ Consumer arrêté proprement")
