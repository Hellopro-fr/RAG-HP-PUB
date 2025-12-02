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
        Tâche de fond qui maintient le canal actif pendant les longs traitements.
        Envoie une opération légère toutes les 30 secondes.
        """
        print("💓 Tâche keep-alive du canal démarrée")
        
        while True:
            try:
                await asyncio.sleep(30)  # Toutes les 30 secondes
                
                if self.consumer_channel and not self.consumer_channel.is_closed:
                    # 🔥 Opération légère : vérifier l'existence d'une exchange
                    try:
                        await self.consumer_channel.get_exchange(
                            self.exchange_name, 
                            ensure=False  # Ne pas créer, juste vérifier
                        )
                        print("💓 Heartbeat canal envoyé (canal actif)")
                    except Exception as e:
                        print(f"⚠️  Erreur lors du heartbeat: {e}")
                else:
                    print("⚠️  Canal consumer fermé ou inexistant")
                    
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
        """
        Tâche de fond qui traite les messages.
        Avec BATCH_SIZE=1, traite 1 message à la fois.
        """
        print("⚙️  Processeur de batch démarré. En attente de messages...")
        
        while True:
            batch = []
            try:
                # 1. Attendre le premier message
                first_message = await self.message_buffer.get()
                batch.append(first_message)
                print(f"📨 Message reçu (delivery_tag: {first_message.delivery_tag})")

                # 2. Essayer de remplir le batch (avec BATCH_SIZE=1, cette boucle ne s'exécute pas)
                while len(batch) < BATCH_SIZE:
                    try:
                        message = await asyncio.wait_for(
                            self.message_buffer.get(), 
                            timeout=BATCH_TIMEOUT_SECONDS
                        )
                        batch.append(message)
                        print(f"📨 Message additionnel reçu (delivery_tag: {message.delivery_tag})")
                    except asyncio.TimeoutError:
                        break
                        
            except asyncio.CancelledError:
                print("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            start_time = time.monotonic()
            batch_size = len(batch)
            print(f"⚙️  Traitement d'un batch de {batch_size} message(s)...")
            messages_to_process = [json.loads(msg.body) for msg in batch]
            
            try:
                # 🔥 Traitement dans les threads - l'event loop reste libre pour le keep-alive
                print(f"🧵 Démarrage du traitement LLM (threads actifs avant: {asyncio.all_tasks().__len__()})")
                processed_results = await nettoyer_bruits_ocr(messages_to_process)
                print(f"✅ Traitement LLM terminé")
                
                # 🔥 Ouvrir un NOUVEAU canal pour les publications et ACK
                # Ne pas réutiliser self.consumer_channel
                async with self.connection.channel() as processing_channel:
                    print(f"📡 Canal de traitement ouvert")
                    
                    for i, result in enumerate(processed_results):
                        original_message = batch[i]
                        
                        try:
                            # Publier la métrique
                            if 'metric_payload' in result:
                                await self.publisher.publish_metric_message(
                                    result['metric_payload'], 
                                    processing_channel
                                )
                                print(f"   📊 Métrique publiée pour message {original_message.delivery_tag}")


                            text = "ok"
                            if "processed_message" in result:
                                if "data" in result['processed_message']:
                                    text = result['processed_message'].get("data",{}).get("text","")
                                    print(f"Suivi text : {text[:10]}...")

                            if result['status'] == 'success' and text:
                                # Publier le message traité
                                await self.publisher.publish_message(
                                    result['processed_message'], 
                                    processing_channel
                                )
                                print(f"   ✅ Message publié pour {original_message.delivery_tag}")
                                
                                # ACK le message original
                                await original_message.ack()
                                print(f"   ✅ ACK envoyé pour {original_message.delivery_tag}")
                                
                            else:  # status == 'error'
                                print(f"   ❌ Échec pour message {original_message.delivery_tag}: {result.get('error_message', 'Erreur inconnue')}")
                                
                                # Envoyer à la DLQ
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
                                print(f"   📮 Message envoyé à la DLQ")
                                
                                # ACK quand même (car envoyé à DLQ)
                                await original_message.ack()
                                print(f"   ✅ ACK envoyé après DLQ pour {original_message.delivery_tag}")
                        
                        except aiormq.exceptions.ChannelInvalidStateError as e:
                            print(f"⚠️  Canal fermé pour message {i} (tag: {original_message.delivery_tag}): {e}")
                            print("   -> Message sera re-délivré automatiquement")
                            break  # Sortir de la boucle for

            except (aiormq.exceptions.ChannelInvalidStateError,
                    aiormq.exceptions.ConnectionClosed) as e:
                print(f"⚠️  Connexion/Canal perdu pendant le traitement: {e}")
                print("   -> Les messages non-ACK seront re-délivrés automatiquement par RabbitMQ")
                
            except Exception as e:
                print(f"❌ ERREUR CATASTROPHIQUE sur le batch: {e}")
                traceback.print_exc()
                
                # Tentative de NACK des messages non traités
                for msg in batch:
                    try:
                        await msg.nack(requeue=False)
                        print(f"   ⚠️  NACK envoyé pour {msg.delivery_tag}")
                    except Exception as nack_error:
                        print(f"   ❌ Impossible de NACK {msg.delivery_tag}: {nack_error}")
                        
            finally:
                end_time = time.monotonic()
                duration = end_time - start_time
                print(f"🏁 Batch de {batch_size} message(s) terminé en {duration:.2f}s ({duration/60:.2f} min)")
    
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
