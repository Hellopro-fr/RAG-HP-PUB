import pika
import json
import time
import asyncio
import os
import uuid
import hashlib

from unittest.mock import MagicMock
from template_llm_service.messaging.publisher import Publisher
# On importe la nouvelle fonction de traitement par batch
from template_llm_service.core.processor import classify_page_template_batch
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.autres.DLQProperties import DLQProperties

# --- Configuration du Batching ---
# Détermine le nombre maximum de messages à traiter en un seul batch.
# Une valeur plus élevée augmente le débit (throughput) mais aussi la latence potentielle.
# À ajuster en fonction de la charge et de la VRAM du GPU.
BATCH_SIZE = 32

# Détermine le temps d'attente maximum (en secondes) avant de traiter un batch,
# même s'il n'est pas plein. C'est une sécurité pour éviter que des messages
# ne restent bloqués indéfiniment en période de faible trafic.
BATCH_TIMEOUT_SECONDS = 2.0
MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative
RECOVERY_DIR = 'recovery_data'

# --- Configuration for the deduplication cache ---
CACHE_TIMEOUT_SECONDS = 600  # 10 minutes: A message is unlikely to be redelivered after this time
CACHE_CLEANUP_INTERVAL_SECONDS = 120 # 2 minutes: How often to prune the cache

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.channel = self.connection.channel()
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

        self.rabbitmq_connection = RabbitMQConnection()

        # --- État interne pour la gestion du batch ---
        # Le buffer stockera les messages entrants avant qu'ils ne soient traités.
        # Chaque élément sera un tuple: (delivery_tag, body).
        self.message_buffer = []
        # Garde en mémoire le moment où le dernier batch a été traité.
        self.last_batch_time = time.time()

        # --- Deduplication Cache ---
        self.processing_cache = {}
        self.last_cache_cleanup = time.time()
        
        self.connect()
        print(f"✅ Consumer initialisé en mode BATCH (Taille: {BATCH_SIZE}, Timeout: {BATCH_TIMEOUT_SECONDS}s).")

    def connect(self):
        """
        Établit la connexion, configure le consumer, synchronise le publisher,
        et traite immédiatement les fichiers de récupération existants.
        """
        if not self.connection or self.connection.is_closed:
            self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()

        # --- 1. Infrastructure pour les échecs FINALS (Dead-Letter Queue) ---
        self.channel.exchange_declare(exchange=self.dead_letter_exchange, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(exchange=self.dead_letter_exchange, queue=self.dead_letter_queue_name, routing_key=self.routing_key)

        # --- 2. Infrastructure pour les tentatives (Retry Queue) ---
        self.channel.exchange_declare(exchange=self.retry_exchange, exchange_type='topic', durable=True)
        retry_queue_args = {
            'x-message-ttl': RETRY_TTL_MS,
            'x-dead-letter-exchange': self.exchange_name, # Renvoyer au main exchange après TTL
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # --- 3. Configuration de la Queue Principale ---
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        main_queue_args = {
            'x-dead-letter-exchange': self.retry_exchange, # Les échecs vont d'abord vers le retry
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.queue_name, durable=True, arguments=main_queue_args)
        
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        
        # 'Quality of Service' : demande à RabbitMQ de ne pas nous envoyer plus de BATCH_SIZE
        # messages à la fois. Cela évite de surcharger la mémoire du client et
        # distribue mieux la charge entre plusieurs replicas du service.
        self.channel.basic_qos(prefetch_count=BATCH_SIZE)
        
        # Synchroniser le publisher avec le nouveau canal valide
        self.publisher.update_channel(self.channel)
        
        # Traiter les fichiers de récupération immédiatement après une connexion réussie
        self._process_recovery_files()

    def _get_retry_count(self, properties: pika.BasicProperties) -> int:
        """Inspecte les headers pour compter le nombre de tentatives."""
        if properties and properties.headers and 'x-death' in properties.headers:
            # `x-death` est une liste, on prend la première entrée qui correspond à notre retry queue
            for death in properties.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    def _finalize_batch_from_recovery_file(self, recovery_filepath: str):
        print(f"📄 Tentative de finalisation du batch depuis le fichier de récupération: {recovery_filepath}")
        try:
            with open(recovery_filepath, 'r') as f:
                recovery_data = json.load(f)
            
            successful_messages = recovery_data.get('successful_messages', [])
            successful_acks = recovery_data.get('successful_acks', [])
            failed_messages = recovery_data.get('failed_messages', [])

            # 1. Publier les messages réussis
            for msg in successful_messages:
                self.publisher.publish_message(msg)
            
            # 2. Acquitter les messages réussis (de manière idempotente)
            for delivery_tag in successful_acks:
                try:
                    self.channel.basic_ack(delivery_tag=delivery_tag)
                except pika.exceptions.AMQPChannelError as e:
                    # Cette erreur est attendue si un autre worker a déjà acquitté le message.
                    print(f"   -> AVERTISSEMENT: Impossible d'acquitter le message (tag: {delivery_tag}). Il a probablement déjà été traité par une autre réplique. Erreur: {e}")
                    pass # On continue, c'est le comportement attendu.

            # 3. Gérer les messages échoués (de manière idempotente)
            for failed_item in failed_messages:
                delivery_tag = failed_item['delivery_tag']
                properties = pika.BasicProperties(**failed_item.get('properties', {}))
                body = json.dumps(failed_item['body']).encode('utf-8')
                error_message = failed_item['error_message']

                try:
                    retry_count = self._get_retry_count(properties)
                    if retry_count < MAX_RETRIES:
                        print(f"   -> NACK du message échoué (tag: {delivery_tag}) pour nouvelle tentative.")
                        self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                    else:
                        print(f"   -> Échec final pour le message (tag: {delivery_tag}). Envoi à la DLQ finale.")
                        dlq_props = DLQProperties.create_dlq_properties(Exception(error_message), 'template-llm-service', MAX_RETRIES, MagicMock(exchange=self.exchange_name, routing_key=self.routing_key))
                        self.channel.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                        self.channel.basic_ack(delivery_tag=delivery_tag)
                except pika.exceptions.AMQPChannelError as e:
                    print(f"   -> AVERTISSEMENT: Impossible de traiter l'échec pour le message (tag: {delivery_tag}). Il a probablement déjà été traité. Erreur: {e}")
                    pass

            # 4. Supprimer le fichier de récupération
            os.remove(recovery_filepath)
            print(f"✓ Fichier de récupération {recovery_filepath} traité et supprimé.")

        except pika.exceptions.StreamLostError as e:
            print(f"❌ ERREUR DE CONNEXION pendant la finalisation du batch. La récupération sera retentée à la prochaine reconnexion. Erreur: {e}")
            raise e # Propage pour que la boucle principale tente de se reconnecter
        except Exception as e:
            print(f"❌ Erreur critique lors de la finalisation du batch depuis {recovery_filepath}: {e}")
            # Ne pas supprimer le fichier pour une inspection manuelle

    def _process_recovery_files(self):
        print("🔎 Recherche de fichiers de récupération...")
        try:
            recovery_files = [f for f in os.listdir(RECOVERY_DIR) if f.startswith('recovery_') and f.endswith('.json')]
            if not recovery_files:
                print("   -> Aucun fichier de récupération trouvé.")
                return

            print(f"   -> {len(recovery_files)} fichier(s) de récupération trouvé(s). Traitement...")
            for filename in recovery_files:
                filepath = os.path.join(RECOVERY_DIR, filename)
                self._finalize_batch_from_recovery_file(filepath)
        except pika.exceptions.StreamLostError as e:
            raise e # Propage l'erreur pour que la boucle principale tente de se reconnecter
        except Exception as e:
            print(f"   -> ⚠️ Échec du traitement des fichiers de récupération: {e}. Ils seront ré-essayés après la prochaine reconnexion.")

    def _prune_cache(self):
        """
        Removes old entries from the processing cache to prevent it from growing indefinitely.
        """
        current_time = time.time()
        if current_time - self.last_cache_cleanup > CACHE_CLEANUP_INTERVAL_SECONDS:
            print("🧹 Exécution du nettoyage du cache de déduplication...")
            keys_to_delete = [
                key for key, timestamp in self.processing_cache.items()
                if current_time - timestamp > CACHE_TIMEOUT_SECONDS
            ]
            for key in keys_to_delete:
                del self.processing_cache[key]
            
            self.last_cache_cleanup = current_time
            print(f"   -> Cache nettoyé. {len(keys_to_delete)} entrée(s) expirée(s) supprimée(s). Taille actuelle: {len(self.processing_cache)}.")

    def _process_batch(self):
        """Orchestre le traitement du batch avec une logique de retry/DLQ."""
        if not self.message_buffer:
            return

        start_time = time.monotonic()
        batch_size = len(self.message_buffer)
        print(f"⚙️  Traitement d'un batch de {batch_size} messages...")
        
        # On copie le buffer actuel pour le traitement et on vide l'original
        # pour qu'il puisse recommencer à se remplir immédiatement.
        current_batch = list(self.message_buffer)
        self.message_buffer.clear()

        valid_batch_items = []
        for delivery_tag, properties, body in current_batch:
            try:
                message_data = json.loads(body)
                if message_data.get("data", {}).get("text"):
                    valid_batch_items.append((delivery_tag, properties, body))
                else:
                    raise ValueError("Contenu du message ('text') manquant.")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"🗑️  Message invalide (tag: {delivery_tag}) envoyé directement à la DLQ finale. Erreur: {e}")
                dlq_props = DLQProperties.create_dlq_properties(e, 'template-llm-service', 0, MagicMock(exchange=self.exchange_name, routing_key=self.routing_key))
                self.channel.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                self.channel.basic_ack(delivery_tag=delivery_tag)

        # --- Traitement des messages valides (s'il y en a) ---
        if not valid_batch_items:
            print("   -> Aucun message valide dans ce batch. Attente du suivant.")
            self.last_batch_time = time.time()
            return

        print(f"⚙️  Traitement d'un batch de {len(valid_batch_items)} message(s) valide(s)...")

        messages_to_process = [json.loads(item[2]) for item in valid_batch_items]
        
        recovery_package = {
            "successful_messages": [],
            "successful_acks": [],
            "failed_messages": []
        }

        try:
            processed_results = asyncio.run(classify_page_template_batch(messages_to_process))
            
            for i, result in enumerate(processed_results):
                delivery_tag, properties, body = valid_batch_items[i]
                
                if result['status'] == 'success':
                    recovery_package['successful_messages'].append(result['processed_message'])
                    recovery_package['successful_acks'].append(delivery_tag)
                else:
                    # Pour pika.BasicProperties, les headers doivent être un dictionnaire
                    props_dict = {'headers': properties.headers} if properties and properties.headers else {}
                    
                    recovery_package['failed_messages'].append({
                        "delivery_tag": delivery_tag,
                        "properties": props_dict,
                        "body": json.loads(body),
                        "error_message": result['error_message']
                    })

            batch_id = str(uuid.uuid4())
            recovery_filepath = os.path.join(RECOVERY_DIR, f"recovery_{batch_id}.json")

            with open(recovery_filepath, 'w') as f:
                json.dump(recovery_package, f)
            
            print(f"   -> Fichier de récupération {recovery_filepath} créé.")
            self._finalize_batch_from_recovery_file(recovery_filepath)

        except pika.exceptions.StreamLostError as e:
            print(f"❌ ERREUR DE CONNEXION PENDANT LE TRAITEMENT: {e}. Le batch sera retraité par RabbitMQ après reconnexion.")
            # En ne les acquittant pas, RabbitMQ les remettra dans la file d'attente.
            # On propage l'erreur pour déclencher la reconnexion.
            raise e

        except Exception as e:
            print(f"❌ ERREUR CATASTROPHIQUE sur le batch (ex: LLM indisponible): {e}. NACK de tous les messages du batch.")
            for delivery_tag, _, _ in valid_batch_items:
                try:
                    self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                except pika.exceptions.StreamLostError:
                    raise # Propage l'erreur de connexion pour la gérer dans la boucle principale
                except Exception as nack_e:
                    print(f"   -> Erreur lors du NACK du message {delivery_tag}: {nack_e}")
        
        finally:
            end_time = time.monotonic()
            duration = end_time - start_time
            print(f"🏁 Traitement du batch de {batch_size} message(s) terminé en {duration:.4f} secondes.")
            # On réinitialise le timer du batch.
            self.last_batch_time = time.time()
            self._prune_cache()

    def start_consuming(self):
        """
        Démarre une boucle de consommation résiliente qui gère la logique de batching
        et les reconnexions automatiques.
        """
        while True:
            try:
                print("👂 template-llm-service: En attente de messages pour le batching...")
                # channel.consume() est un générateur qui nous donne plus de contrôle.
                # 'inactivity_timeout' est crucial : il permet à la boucle de continuer
                # même si aucun message n'arrive, afin de traiter les batches incomplets.
                for method_frame, properties, body in self.channel.consume(self.queue_name, inactivity_timeout=BATCH_TIMEOUT_SECONDS):
                    
                    # Si method_frame est None, cela signifie que le timeout a été atteint.
                    if method_frame is None:
                        # S'il y a des messages en attente dans le buffer, il est temps de les traiter.
                        if self.message_buffer:
                            print("   -> Timeout atteint, traitement du batch en cours...")
                            self._process_batch()
                        # On continue la boucle pour attendre de nouveaux messages.
                        continue
                    
                    # --- Deduplication Check ---
                    message_hash = hashlib.sha256(body).hexdigest()

                    if message_hash in self.processing_cache:
                        print(f"🟡 Doublon détecté (hash: {message_hash[:8]}...). Message (tag: {method_frame.delivery_tag}) acquitté et ignoré.")
                        self.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                        continue

                    self.processing_cache[message_hash] = time.time()
                    self.message_buffer.append((method_frame.delivery_tag, properties, body))
                    
                    # Si le buffer a atteint sa taille maximale, on traite le batch immédiatement
                    # sans attendre le timeout.
                    if len(self.message_buffer) >= BATCH_SIZE:
                        print(f"   -> Taille maximale du batch ({BATCH_SIZE}) atteinte, traitement...")
                        self._process_batch()

            except pika.exceptions.StreamLostError as e:
                print(f"⚠️ Connexion perdue dans la boucle principale: {e}. Tentative de reconnexion...")
                self.connect() # Tente de se reconnecter
            except KeyboardInterrupt:
                print("\n🛑 Interruption manuelle. Arrêt du consumer.")
                break
            except pika.exceptions.AMQPChannelError as e:
                # This specific error occurs when an ack/nack is sent for a delivery tag
                # that RabbitMQ no longer recognizes (reply-code 406).
                if e.reply_code == 406:
                    print(f"🟡 AVERTISSEMENT de condition de course: {e}. Un message a probablement été traité par une autre réplique. On continue.")
                    # We just continue the loop without reconnecting, the channel is fine.
                    continue
                else:
                    # For other channel errors, it's safer to reconnect.
                    print(f"❌ Erreur de canal inattendue: {e}. Tentative de reconnexion...")
                    self.connect()
            except Exception as e:
                print(f"❌ Erreur inattendue dans la boucle de consommation: {e}. Tentative de reconnexion...")
                self.connect() # Tente de se reconnecter