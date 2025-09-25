import pika
import json
import time
import asyncio

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

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        self.channel = connection.channel()
        self.publisher = publisher
        
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

        self.connect()
        print(f"✅ Consumer initialisé en mode BATCH (Taille: {BATCH_SIZE}, Timeout: {BATCH_TIMEOUT_SECONDS}s).")

    def connect(self):
        """
        Établit la connexion et configure le consumer, y compris les queues de retry et de dead-letter.
        """
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

    def _get_retry_count(self, properties: pika.BasicProperties) -> int:
        """Inspecte les headers pour compter le nombre de tentatives."""
        if properties.headers and 'x-death' in properties.headers:
            # `x-death` est une liste, on prend la première entrée qui correspond à notre retry queue
            for death in properties.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

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
                dlq_props = DLQProperties.create_dlq_properties(e, 0, MagicMock(exchange=self.exchange_name, routing_key=self.routing_key))
                self.channel.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                self.channel.basic_ack(delivery_tag=delivery_tag)

        # --- Traitement des messages valides (s'il y en a) ---
        if not valid_batch_items:
            print("   -> Aucun message valide dans ce batch. Attente du suivant.")
            self.last_batch_time = time.time()
            return

        print(f"⚙️  Traitement d'un batch de {len(valid_batch_items)} message(s) valide(s)...")
        messages = [json.loads(item[2]) for item in valid_batch_items]

        try:
            processed_messages = asyncio.run(classify_page_template_batch(messages))
            
            # --- Gestion granulaire des ACKs/NACKs pour la résilience ---
            # On parcourt chaque résultat pour l'acquitter individuellement.
            # Si un seul message échoue, les autres ne sont pas impactés.
            for i, output_message in enumerate(processed_messages):
                original_delivery_tag = valid_batch_items[i][0]
                self.publisher.publish_message(output_message)
                self.channel.basic_ack(delivery_tag=original_delivery_tag)

            print("   -> Batch valide traité avec succès.")

        except Exception as e:
            # Ceci est une erreur catastrophique (ex: le modèle vLLM a crashé).
            # Dans ce cas, on ne peut pas savoir quels messages ont réussi.
            # La stratégie la plus sûre est de NACK tout le batch pour un retraitement ultérieur.
            print(f"❌ ERREUR CATASTROPHIQUE sur le batch valide : {e}. Gestion individuelle des messages...")
            for delivery_tag, properties, body in valid_batch_items:
                retry_count = self._get_retry_count(properties)
                if retry_count < MAX_RETRIES:
                    print(f"   -> NACK du message (tag: {delivery_tag}) pour une nouvelle tentative (essai {retry_count + 1}).")
                    self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                else:
                    print(f"   -> Échec après {MAX_RETRIES + 1} tentatives (tag: {delivery_tag}). Message envoyé à la DLQ finale.")
                    dlq_props = DLQProperties.create_dlq_properties(e, MAX_RETRIES, MagicMock(exchange=self.exchange_name, routing_key=self.routing_key))
                    self.channel.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                    self.channel.basic_ack(delivery_tag=delivery_tag)
        
        finally:
            end_time = time.monotonic()
            duration = end_time - start_time
            print(f"🏁 Traitement du batch de {batch_size} message(s) terminé en {duration:.4f} secondes.")
            # On réinitialise le timer du batch.
            self.last_batch_time = time.time()

    def start_consuming(self):
        """
        Remplace la boucle de consommation basique par une boucle contrôlée
        qui gère la logique de création de batches.
        """
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

            # Un message est arrivé. On l'ajoute à notre buffer.
            self.message_buffer.append((method_frame.delivery_tag, properties, body))
            
            # Si le buffer a atteint sa taille maximale, on traite le batch immédiatement
            # sans attendre le timeout.
            if len(self.message_buffer) >= BATCH_SIZE:
                print(f"   -> Taille maximale du batch ({BATCH_SIZE}) atteinte, traitement...")
                self._process_batch()