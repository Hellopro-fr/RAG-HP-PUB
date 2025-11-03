import aio_pika
import os
import json
import asyncio
import hashlib
import aiofiles
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from document_echange_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from document_echange_processor_service.core.processor import process_document_data_for_templating # Importe la logique métier
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        # self.executor = ProcessPoolExecutor(max_workers=1)
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)
        
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

    async def _process_message_task(self, message: aio_pika.abc.AbstractIncomingMessage):
        try:
            data = json.loads(message.body)
            document_data = data.get('data', {})
            document_id = document_data.get('fichier_source')
            bdd = "milvus"

            # Vérifie si déjà en cours de traitement
            if await self._is_processing(document_id):
                print(f"⚠️ Document {document_id} déjà en traitement, skip")
                await message.ack()
                return
            
            # Marque comme "en cours" AVANT l'ACK
            await self._mark_as_processing(document_id, message.body)
            
            # ✅ ACK immédiat
            await message.ack()
            
            print(f"📥 Traitement OCR démarré pour {document_id}...")
            
            try:
                print(f"Document data : {document_data}")

                # Traitement long
                output_message = await process_document_data_for_templating(
                    document_data, bdd, self.executor
                )
                
                print(f"Output message : {output_message}")

                # Publie le résultat
                routing_key = 'data.ready_for_templating' if not output_message.get("data", {}).get("page_type") else 'data.ready_for_embedding'
                output_message['routing_key'] = routing_key
                
                print(f"routing_key : {routing_key}")


                async with self.connection.channel() as channel:
                    await self.publisher.publish_message(output_message, channel)
                
                print(f"Après publication")

                # ✅ Marque comme terminé
                await self._mark_as_completed(document_id)
                print(f"✅ Traitement terminé pour {document_id}")
                
            except Exception as e:
                # ❌ En cas d'erreur, republier le message
                print(f"❌ Erreur durant traitement: {e}")
                print(f"Message body : {message.body}")
                await self._handle_processing_error(message.body, message.headers, e, document_id)
                
        except Exception as e:
            print(f"❌ Erreur critique: {e}")
            await message.nack(requeue=True)

    def _get_processing_filepath(self, document_id: str) -> str:
        """Génère un chemin de fichier sécurisé basé sur un hash"""
        # Crée un hash unique du document_id
        hash_id = hashlib.md5(document_id.encode()).hexdigest()
        return f"/tmp/processing_{hash_id}.json"

    async def _mark_as_processing(self, document_id: str, message_body: bytes):
        """Sauvegarde l'état 'en cours'"""
        filepath = self._get_processing_filepath(document_id)
        
        # Sauvegarde aussi l'ID original pour debug
        data = {
            'original_id': document_id,
            'message': message_body.decode()
        }
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(json.dumps(data))

    async def _is_processing(self, document_id: str) -> bool:
        """Vérifie si le document est déjà en traitement"""
        import os
        filepath = self._get_processing_filepath(document_id)
        return os.path.exists(filepath)

    async def _mark_as_completed(self, document_id: str):
        """Supprime l'état 'en cours'"""
        import os
        filepath = self._get_processing_filepath(document_id)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass

    async def _handle_processing_error(self, message_body: bytes, message_headers: dict, error: Exception, document_id: str):
        """Gère les erreurs après ACK"""
        try:
            data = json.loads(message_body)
            retry_count = data.get('_retry_count', 0)
            
            if retry_count < MAX_RETRIES:
                data['_retry_count'] = retry_count + 1
                
                async with self.connection.channel() as channel:
                    exchange = await channel.get_exchange(self.retry_exchange)
                    await exchange.publish(
                        aio_pika.Message(
                            body=json.dumps(data).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                        ),
                        routing_key=self.routing_key
                    )
                
                print(f"🔄 Message republié (tentative {retry_count + 1}/{MAX_RETRIES})")
            else:
                await self._send_to_dlq(message_body, message_headers, error, MAX_RETRIES)
            
            # Nettoie l'état
            await self._mark_as_completed(document_id)
            
        except Exception as e:
            print(f"⚠️ Erreur lors de la gestion d'erreur: {e}")

    async def _send_to_dlq(self, message_body: bytes, message_headers: dict, error: Exception, retry_count: int):
        """Envoie à la DLQ en utilisant l'utilitaire partagé (après un ACK)."""
        async with self.connection.channel() as channel:
            dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
            
            # Create a mock message object that DLQProperties.create_dlq_headers can use.
            # This is necessary because the original message was already ACK'd.
            mock_message = SimpleNamespace(body=message_body, headers=message_headers)

            dlq_headers = DLQProperties.create_dlq_headers(
                error,
                'document-echange-processor-service',
                retry_count,
                mock_message
            )

            await dlx.publish(
                aio_pika.Message(
                    body=message_body,
                    headers=dlq_headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=self.routing_key
            )

    async def start_consuming(self):
        """Démarre le consumer avec contrôle du parallélisme et gestion des erreurs."""
        
        # 1. Crée le channel et configure le prefetch
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=5)  # Nombre maximum de messages traités en parallèle
        
        # 2. Déclare et bind les queues/exchanges
        queue = await self._setup_queues(channel)
        
        # 3. Crée un semaphore pour limiter le nombre de traitements simultanés
        semaphore = asyncio.Semaphore(5)
        
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