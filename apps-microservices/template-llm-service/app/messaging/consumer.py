import aio_pika
import json
import asyncio
import time
import aiormq
import logging
from collections import defaultdict

from template_llm_service.messaging.publisher import Publisher
from template_llm_service.core.processor import classify_page_template_batch
from common_utils.autres.DLQProperties import DLQProperties
from common_utils.autres.fenetre_tarifaire import est_heure_pleine, libelle_fenetre

# --- Configuration du Batching ---
# Détermine le nombre maximum de messages à traiter en un seul batch.
# Une valeur plus élevée augmente le débit (throughput) mais aussi la latence potentielle.
# À ajuster en fonction de la charge et de la VRAM du GPU.
BATCH_SIZE = 16

# Détermine le temps d'attente maximum (en secondes) avant de traiter un batch,
# même s'il n'est pas plein. C'est une sécurité pour éviter que des messages
# ne restent bloqués indéfiniment en période de faible trafic.
BATCH_TIMEOUT_SECONDS = 2.0
MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

# Pas de la boucle qui surveille la fenêtre tarifaire DeepSeek. 60 s suffisent : la
# reprise n'a pas besoin d'être à la seconde près, et une vérification courte évite de
# tenir la boucle éveillée pour rien pendant 3 à 4 h.
ATTENTE_FENETRE_PLEINE_S = 60

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.message_buffer = asyncio.Queue()
        # Tag de l'abonnement, indispensable pour pouvoir s'en détacher pendant les
        # fenêtres chères de DeepSeek. `queue.consume()` le retourne ; il était jeté.
        self._consumer_tag = None

        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

    async def _setup_queues(self, channel: aio_pika.abc.AbstractChannel):
        """Déclare toutes les files d'attente et les échanges nécessaires."""
        
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

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        """Callback léger qui met les messages dans un buffer asynchrone."""
        await self.message_buffer.put(message)

    async def batch_processor(self):
        """Tâche de fond qui traite les messages par lots de manière asynchrone."""
        print("⚙️  Processeur de batch démarré. En attente de messages...")
        
        while True:
            batch = []
            try:
                # 1. Attendre indéfiniment le premier message pour démarrer un batch
                first_message = await self.message_buffer.get()
                batch.append(first_message)

                # 2. Une fois le premier message reçu, essayer de remplir le reste du batch
                #    en respectant le BATCH_TIMEOUT et le BATCH_SIZE.
                while len(batch) < BATCH_SIZE:
                    try:
                        message = await asyncio.wait_for(self.message_buffer.get(), timeout=BATCH_TIMEOUT_SECONDS)
                        batch.append(message)
                    except asyncio.TimeoutError:
                        # Le timeout a été atteint, on sort pour traiter le batch partiel
                        break
            except asyncio.CancelledError:
                print("   -> Tâche de traitement de batch annulée.")
                break

            if not batch:
                continue

            # --- Group messages by collection type ---
            grouped_messages = defaultdict(list)
            grouped_raw_data = defaultdict(list)
            
            for msg in batch:
                try:
                    raw_data = json.loads(msg.body)
                    collection = raw_data.get('collection', 'unknown')
                    grouped_messages[collection].append(msg)
                    grouped_raw_data[collection].append(raw_data)
                except json.JSONDecodeError:
                    logging.error(f"Failed to decode message body: {msg.body}")
                    # Handle poison pill message if necessary, e.g., send to DLQ

            # --- Process each group as a separate batch ---
            for collection, messages_to_process in grouped_raw_data.items():
                original_message_group = grouped_messages[collection]
                
                start_time = time.monotonic()
                batch_size = len(messages_to_process)
                print(f"⚙️  Traitement d'un batch de {batch_size} messages pour la collection '{collection}'...")

                try:
                    processed_results = await classify_page_template_batch(messages_to_process)
                    
                    async with self.connection.channel() as channel:
                        for i, result in enumerate(processed_results):
                            original_message = original_message_group[i]
                            
                            if 'metric_payload' in result:
                                await self.publisher.publish_metric_message(result['metric_payload'], channel)

                            if result['status'] == 'success':
                                logging.info(f"\n\nTexte juste après identification template :\n{result['processed_message']}")
                                await self.publisher.publish_message(result['processed_message'], channel)
                                await original_message.ack()
                            else: # status == 'error'
                                retry_count = self._get_retry_count(original_message)
                                if retry_count < MAX_RETRIES:
                                    print(f"   -> NACK du message (tag: {original_message.delivery_tag}) pour nouvelle tentative.")
                                    await original_message.nack(requeue=False)
                                else:
                                    print(f"   -> Échec final pour le message (tag: {original_message.delivery_tag}). Envoi à la DLQ finale.")
                                    dlx = await channel.get_exchange(self.dead_letter_exchange, ensure=True)
                                    
                                    dlq_headers = DLQProperties.create_dlq_headers(
                                        Exception(result['error_message']), 
                                        'template-llm-service', 
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

                except Exception as e:
                    print(f"❌ ERREUR CATASTROPHIQUE sur le batch (ex: LLM indisponible): {e}. NACK de tous les messages du batch.")
                    for msg in original_message_group:
                        try:
                            await msg.nack(requeue=False)
                        except aiormq.exceptions.ChannelInvalidStateError:
                            print("   -> Le canal est déjà fermé. Impossible de NACK les messages restants. Ils seront re-délivrés après reconnexion.")
                            break
                finally:
                    end_time = time.monotonic()
                    duration = end_time - start_time
                    print(f"🏁 Traitement du batch '{collection}' de {batch_size} message(s) terminé en {duration:.4f} secondes.")

    async def start_consuming(self):
        """Démarre le consumer et la tâche de traitement de batch."""
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=BATCH_SIZE)

        queue = await self._setup_queues(channel)

        # Démarrer la tâche de fond qui traitera les batches
        asyncio.create_task(self.batch_processor())

        # Commencer à consommer les messages et à les mettre dans le buffer
        print("👂 template-llm-service: En attente de messages...")
        logging.info("💰 Fenêtre tarifaire DeepSeek au démarrage : %s", libelle_fenetre())
        await self._boucle_fenetre_tarifaire(queue)

    async def _boucle_fenetre_tarifaire(self, queue):
        """S'abonne / se désabonne de la file selon la fenêtre tarifaire DeepSeek.

        Ce service ne pioche pas dans sa file : il s'y ABONNE, et `_on_message` ne fait
        que déposer le message dans `self.message_buffer`. On ne peut donc pas rendre les
        messages un par un comme un consumer à itérateur — on annule l'abonnement, et le
        `batch_processor` finit tranquillement ce qu'il a en tampon.

        Le tampon est borné par le prefetch (BATCH_SIZE), donc au pire 16 messages sont
        traités au tarif double à chaque bascule — mesuré à ~1,6 % du volume quotidien.
        Le vider en `nack` a été essayé puis ABANDONNÉ : `nack()` lève
        `MessageProcessError` sur un message déjà acquitté, donc l'opération court contre
        le `batch_processor` qui acquitte au même moment.

        ⚠️ Les erreurs de canal et de connexion ne sont PAS attrapées, volontairement.
        `main.py` les traite déjà (`except (AMQPConnectionError,
        ChannelInvalidStateError)`) en reconstruisant connexion + consumer. Une première
        version les avalait et retentait : après une coupure, `queue` restait attachée au
        canal mort et la boucle retentait à l'infini — service muet, rien en DLQ, aucune
        alerte. C'est pourquoi cette boucle est AWAITÉE ici et non lancée en
        `create_task()` : sinon l'exception mourrait dans une tâche orpheline.

        Prouvé contre un vrai broker (RabbitMQ 3.12.1, aio_pika 9.6.2) :
        `tests/test_integration_garde_callback.py`.
        """
        while True:
            if est_heure_pleine():
                if self._consumer_tag is not None:
                    await queue.cancel(self._consumer_tag)
                    self._consumer_tag = None
                    logging.warning(
                        "⏸️  DeepSeek en %s : abonnement à %s ANNULÉ, les messages "
                        "restent en file (vérification toutes les %ss)",
                        libelle_fenetre(), self.queue_name, ATTENTE_FENETRE_PLEINE_S)
            elif self._consumer_tag is None:
                self._consumer_tag = await queue.consume(self._on_message)
                logging.info("▶️  %s : réabonnement à %s (tag %s)",
                             libelle_fenetre(), self.queue_name, self._consumer_tag)
            await asyncio.sleep(ATTENTE_FENETRE_PLEINE_S)