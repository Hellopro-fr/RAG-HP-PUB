import pika
import json
import time
from vllm import LLM
from template_llm_service.messaging.publisher import Publisher
# On importe la nouvelle fonction de traitement par batch
from template_llm_service.core.processor import classify_page_template_batch
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

# --- Configuration du Batching ---
# Détermine le nombre maximum de messages à traiter en un seul batch.
# Une valeur plus élevée augmente le débit (throughput) mais aussi la latence potentielle.
# À ajuster en fonction de la charge et de la VRAM du GPU.
BATCH_SIZE = 16

# Détermine le temps d'attente maximum (en secondes) avant de traiter un batch,
# même s'il n'est pas plein. C'est une sécurité pour éviter que des messages
# ne restent bloqués indéfiniment en période de faible trafic.
BATCH_TIMEOUT_SECONDS = 2.0

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher, llm: LLM, tokenizer, llm_config: dict):
        self.channel = connection.channel()
        self.publisher = publisher
        self.llm = llm
        self.tokenizer = tokenizer
        self.llm_config = llm_config
        
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'

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
        Établit la connexion à RabbitMQ et configure la file d'attente et le canal.
        """
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        
        # 'Quality of Service' : demande à RabbitMQ de ne pas nous envoyer plus de BATCH_SIZE
        # messages à la fois. Cela évite de surcharger la mémoire du client et
        # distribue mieux la charge entre plusieurs replicas du service.
        self.channel.basic_qos(prefetch_count=BATCH_SIZE)

    def _process_batch(self):
        """
        Orchestre le traitement du batch actuellement dans le buffer.
        Cette fonction est le cœur de la logique de batching résiliente.
        """
        if not self.message_buffer:
            return

        print(f"⚙️  Traitement d'un batch de {len(self.message_buffer)} messages...")
        
        # On copie le buffer actuel pour le traitement et on vide l'original
        # pour qu'il puisse recommencer à se remplir immédiatement.
        current_batch = list(self.message_buffer)
        self.message_buffer.clear()

        # --- ÉTAPE DE VALIDATION ET FILTRAGE ---
        valid_batch_items = []
        invalid_batch_items = []

        for item in current_batch:
            delivery_tag, body = item
            try:
                # On essaie de parser le JSON et de vérifier la présence du contenu.
                message_data = json.loads(body)
                content = message_data.get("data", {}).get("text")
                if content: # La clé "text" existe et n'est pas vide/None
                    valid_batch_items.append(item)
                else:
                    # Le message est invalide car le contenu est manquant.
                    invalid_batch_items.append(item)
            except json.JSONDecodeError:
                # Le message est invalide car le body n'est pas un JSON valide.
                invalid_batch_items.append(item)

        # --- Traitement des messages invalides ---
        if invalid_batch_items:
            print(f"🗑️  {len(invalid_batch_items)} message(s) invalide(s) détecté(s) (contenu manquant ou JSON corrompu).")
            for delivery_tag, body in invalid_batch_items:
                # On désacquitte (NACK) ces messages pour les supprimer définitivement de la file d'attente.
                # C'est la solution pour casser la boucle de retraitement.
                print(f"   -> Suppression du message invalide (tag: {delivery_tag}).")
                self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)

        # --- Traitement des messages valides (s'il y en a) ---
        if not valid_batch_items:
            print("   -> Aucun message valide dans ce batch. Attente du suivant.")
            self.last_batch_time = time.time()
            return

        print(f"⚙️  Traitement d'un batch de {len(valid_batch_items)} message(s) valide(s)...")
        messages = [json.loads(item[1]) for item in valid_batch_items]

        try:
            processed_messages = classify_page_template_batch(self.llm, self.tokenizer, self.llm_config, messages)
            
            # --- Gestion granulaire des ACKs/NACKs pour la résilience ---
            # On parcourt chaque résultat pour l'acquitter individuellement.
            # Si un seul message échoue, les autres ne sont pas impactés.
            for i, output_message in enumerate(processed_messages):
                original_delivery_tag = valid_batch_items[i][0]
                try:
                    # On publie le message traité.
                    self.publisher.publish_message(output_message)
                    # Si la publication réussit, on acquitte (ACK) le message original.
                    # RabbitMQ peut alors le supprimer de la file d'attente.
                    self.channel.basic_ack(delivery_tag=original_delivery_tag)
                except Exception as pub_e:
                    print(f"   -> ❌ Erreur de publication pour message {original_delivery_tag}. NACK. Erreur: {pub_e}")
                    # Si la publication échoue, on NACK le message pour qu'il soit retraité.
                    self.channel.basic_nack(delivery_tag=original_delivery_tag, requeue=True)

            print(f"   -> Batch valide traité avec succès.")

        except Exception as e:
            # Ceci est une erreur catastrophique (ex: le modèle vLLM a crashé).
            # Dans ce cas, on ne peut pas savoir quels messages ont réussi.
            # La stratégie la plus sûre est de NACK tout le batch pour un retraitement ultérieur.
            print(f"❌ ERREUR CATASTROPHIQUE sur le batch valide : {e}. NACK de tout le batch valide.")
            for item in valid_batch_items:
                self.channel.basic_nack(delivery_tag=item[0], requeue=True)
        
        finally:
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
            self.message_buffer.append((method_frame.delivery_tag, body))
            
            # Si le buffer a atteint sa taille maximale, on traite le batch immédiatement
            # sans attendre le timeout.
            if len(self.message_buffer) >= BATCH_SIZE:
                print(f"   -> Taille maximale du batch ({BATCH_SIZE}) atteinte, traitement...")
                self._process_batch()