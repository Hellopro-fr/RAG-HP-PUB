import pika
import os
import json
import time
from datetime import datetime
from elasticsearch import Elasticsearch, helpers
from es_mapping import INDEX_MAPPING # Import the new mapping

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
# Les queues DLQ à écouter, séparées par des virgules
DLQ_QUEUES_STR = os.environ.get("DLQ_QUEUES", "embedding_queue_dlq,insertion_siteweb_queue_dlq,llm_templating_queue_dlq,website_processing_queue_dlq")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = "failed_messages_archive" # Point to the new index
BATCH_SIZE = 50 # Nombre de messages à archiver en une seule fois
BATCH_TIMEOUT_SECONDS = 5.0 # Temps d'attente max avant d'archiver un batch non plein

def get_rabbitmq_connection():
    """Tente de se connecter à RabbitMQ avec des retries."""
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("✅ DLQ Archiver: Connecté à RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ DLQ Archiver: En attente de RabbitMQ... {i+1}s")
            time.sleep(i + 1)
    raise ConnectionError("❌ DLQ Archiver: Impossible de se connecter à RabbitMQ.")

def get_elasticsearch_client():
    """Tente de se connecter à Elasticsearch avec des retries."""
    for i in range(10):
        try:
            es_client = Elasticsearch(ELASTICSEARCH_URL)
            if es_client.ping():
                print("✅ DLQ Archiver: Connecté à Elasticsearch.")
                return es_client
            else:
                raise ConnectionError("Ping Elasticsearch a échoué.")
        except Exception as e:
            print(f"⏳ DLQ Archiver: En attente d'Elasticsearch... {i+1}s ({e})")
            time.sleep(i + 1)
    raise ConnectionError("❌ DLQ Archiver: Impossible de se connecter à Elasticsearch.")

def _get_retry_count_from_headers(headers):
    """Inspecte les headers pour trouver le compte de tentatives de la file de retry."""
    if headers and 'x-death' in headers:
        for death in headers['x-death']:
            if "retry" in death.get('queue', ''):
                return death.get('count', 0)
    return 0

def process_message(body, properties):
    """Transforme un message RabbitMQ en document Elasticsearch."""
    try:
        original_payload = json.loads(body)
    except json.JSONDecodeError:
        original_payload = {"raw_body": body.decode('utf-8', errors='ignore')}

    headers = properties.headers or {}

    # Stratégie 1: Lire les en-têtes personnalisés explicites (préféré)
    if 'x-service-name' in headers:
        service_name = headers.get('x-service-name', 'N/A')
        error_reason = headers.get('x-error-reason', 'Raison inconnue')
        original_exchange = headers.get('x-original-exchange', 'N/A')
        original_routing_key = headers.get('x-original-routing-key', 'N/A')
        retry_count = headers.get('x-retry-count', _get_retry_count_from_headers(headers))
    # Stratégie 2: Fallback sur l'analyse de x-death (pour anciens messages ou DLX par TTL)
    else:
        error_reason = "Raison inconnue"
        original_exchange = "N/A"
        original_routing_key = "N/A"
        original_queue = "N/A"
        
        if 'x-death' in headers and headers['x-death']:
            death_info = headers['x-death'][0]
            error_reason = death_info.get('reason', 'N/A')
            original_exchange = death_info.get('exchange', 'N/A')
            original_routing_key = death_info.get('routing-keys', ['N/A'])[0]
            original_queue = death_info.get('queue', 'N/A')

        retry_count = _get_retry_count_from_headers(headers)
        service_name = original_queue.replace('_queue', '').replace('_retry', '')

    # --- Sanitization and Type Coercion ---
    try:
        safe_retry_count = int(retry_count) if retry_count is not None else 0
    except (ValueError, TypeError):
        safe_retry_count = 0
        
    source_doc = {
        "@timestamp": datetime.utcnow().isoformat(),
        "service_name": str(service_name or "N/A"),
        "error_reason": str(error_reason or "Raison inconnue"),
        "retry_count": safe_retry_count,
        "original_exchange": str(original_exchange or "N/A"),
        "original_routing_key": str(original_routing_key or "N/A"),
        "original_payload": original_payload,
    }

    document = {
        "_index": ELASTIC_INDEX_NAME,
        "_source": source_doc
    }
    return document

def main():
    """Point d'entrée principal du service d'archivage."""
    print("🚀 DLQ Archiver: Démarrage du service...")
    
    es_client = get_elasticsearch_client()
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    dlq_queues = [q.strip() for q in DLQ_QUEUES_STR.split(',')]
    
    # Assurer que l'index existe dans Elasticsearch avec le bon mapping
    if not es_client.indices.exists(index=ELASTIC_INDEX_NAME):
        print(f"Index '{ELASTIC_INDEX_NAME}' non trouvé. Création avec le mapping correct...")
        es_client.indices.create(index=ELASTIC_INDEX_NAME, body=INDEX_MAPPING)

    documents_buffer = []
    last_archive_time = time.time()

    def callback(ch, method, properties, body):
        """Callback simple qui ajoute les messages reçus à un buffer."""
        print(f"📥 DLQ Archiver: Message reçu de la queue '{method.routing_key}' (tag: {method.delivery_tag})")
        doc = process_message(body, properties)
        documents_buffer.append((method.delivery_tag, doc))

    try:
        for queue_name in dlq_queues:
            print(f"👂 DLQ Archiver: Enregistrement du consumer pour la queue '{queue_name}'...")
            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)
        
        print("👂 DLQ Archiver: Démarrage de la boucle de traitement...")
        while True:
            # Traite les événements (messages entrants) pendant 1 seconde
            channel.connection.process_data_events(time_limit=1)

            batch_is_full = len(documents_buffer) >= BATCH_SIZE
            timeout_reached = (time.time() - last_archive_time) > BATCH_TIMEOUT_SECONDS

            if documents_buffer and (batch_is_full or timeout_reached):
                if timeout_reached:
                    print(f"   -> Timeout ({BATCH_TIMEOUT_SECONDS}s) atteint, archivage du batch en cours...")
                archive_and_ack_batch(channel, es_client, documents_buffer)
                last_archive_time = time.time()

    except KeyboardInterrupt:
        print("\n🛑 DLQ Archiver: Arrêt demandé. Archivage des messages restants...")
        if documents_buffer:
            archive_and_ack_batch(channel, es_client, documents_buffer)
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE dans le DLQ Archiver: {e}")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ DLQ Archiver: Connexion RabbitMQ fermée.")

def archive_and_ack_batch(channel, es_client, buffer):
    """Archive un batch de messages et acquitte ou rejette chaque message individuellement."""
    if not buffer:
        return
        
    print(f"📦 DLQ Archiver: Tentative d'archivage d'un batch de {len(buffer)} documents...")
    docs_to_es = [doc for _, doc in buffer]
    
    successes = 0
    failures = 0
    
    try:
        # Utiliser `raise_on_error=False` pour obtenir un rapport détaillé des erreurs
        for ok, action in helpers.streaming_bulk(es_client, docs_to_es, raise_on_error=False):
            if not ok:
                failures += 1
                # L'objet 'action' contient l'erreur détaillée d'Elasticsearch
                print(f"   -> ❌ Échec de l'indexation: {action}")
                # Nous ne connaissons pas le delivery_tag ici, nous le gérerons plus tard
            else:
                successes += 1
        
        print(f"   -> Résultat du bulk: {successes} succès, {failures} échecs.")

        # Maintenant, nous acquittons ou rejetons en nous basant sur le succès
        # NOTE: Cette approche simple suppose que l'ordre est conservé, ce qui est le cas pour streaming_bulk.
        # Dans un scénario plus complexe, on pourrait mapper les erreurs à l'ID du document.
        if failures > 0:
            # Pour la simplicité de cette correction, nous rejetons l'ensemble du lot si une partie échoue.
            # Cela empêche la perte de messages mais peut entraîner le retraitement des messages réussis.
            # C'est un compromis sûr.
            last_delivery_tag = buffer[-1][0]
            print(f"   -> Au moins un document a échoué. NACK de tout le batch (jusqu'au tag {last_delivery_tag}) pour un retraitement sûr.")
            channel.basic_nack(delivery_tag=last_delivery_tag, multiple=True, requeue=True) # Requeue pour nouvelle tentative
        else:
            # Si tout a réussi, on acquitte tout le batch.
            last_delivery_tag = buffer[-1][0]
            channel.basic_ack(delivery_tag=last_delivery_tag, multiple=True)
            print(f"   -> Batch entièrement archivé et acquitté avec succès (jusqu'au tag {last_delivery_tag}).")

        buffer.clear()

    except Exception as e:
        print(f"❌ ERREUR CRITIQUE lors de la communication avec Elasticsearch: {e}. Les messages ne seront pas acquittés et seront retraités.")
        # Ne pas acquitter permet de retenter au prochain redémarrage du service.