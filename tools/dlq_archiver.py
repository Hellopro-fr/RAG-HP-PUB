import pika
import os
import json
import time
from datetime import datetime
from elasticsearch import Elasticsearch, helpers

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
# Les queues DLQ à écouter, séparées par des virgules
DLQ_QUEUES_STR = os.environ.get("DLQ_QUEUES", "llm_templating_queue_dlq,website_processing_queue_dlq")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = "failed_messages_archive"
BATCH_SIZE = 10 # Nombre de messages à archiver en une seule fois
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

def process_message(body, properties):
    """Transforme un message RabbitMQ en document Elasticsearch."""
    try:
        original_payload = json.loads(body)
    except json.JSONDecodeError:
        original_payload = {"raw_body": body.decode('utf-8', errors='ignore')}

    error_reason, retry_count = "Raison inconnue", 0
    original_exchange, original_routing_key, original_queue = "N/A", "N/A", "N/A"
    
    if properties.headers and 'x-death' in properties.headers:
        death_info = properties.headers['x-death'][0]
        error_reason = death_info.get('reason', 'N/A')
        original_exchange = death_info.get('exchange', 'N/A')
        original_routing_key = death_info.get('routing-keys', ['N/A'])[0]
        original_queue = death_info.get('queue', 'N/A')
        
        # Le 'count' est spécifique à la queue de retry
        for death in properties.headers['x-death']:
            if "retry" in death.get('queue', ''):
                retry_count = death.get('count', 0)
                break
    
    service_name = original_queue.replace('_queue', '').replace('_dlq', '').replace('_retry', '')

    document = {
        "_index": ELASTIC_INDEX_NAME,
        "_source": {
            "@timestamp": datetime.utcnow().isoformat(),
            "service_name": service_name,
            "error_reason": str(error_reason),
            "retry_count": retry_count,
            "original_exchange": original_exchange,
            "original_routing_key": original_routing_key,
            "original_payload": original_payload,
        }
    }
    return document

def main():
    print("🚀 DLQ Archiver: Démarrage du service...")
    
    es_client = get_elasticsearch_client()
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    dlq_queues = [q.strip() for q in DLQ_QUEUES_STR.split(',')]
    
    if not es_client.indices.exists(index=ELASTIC_INDEX_NAME):
        print(f"Index '{ELASTIC_INDEX_NAME}' non trouvé. Création...")
        es_client.indices.create(index=ELASTIC_INDEX_NAME)

    documents_buffer = []
    
    try:
        for queue_name in dlq_queues:
            print(f"👂 DLQ Archiver: Écoute de la queue '{queue_name}'...")
            channel.queue_declare(queue=queue_name, durable=True)
            
        def callback(ch, method, properties, body):
            doc = process_message(body, properties)
            documents_buffer.append((method.delivery_tag, doc))

            if len(documents_buffer) >= BATCH_SIZE:
                archive_and_ack_batch(ch, es_client, documents_buffer)

        for queue_name in dlq_queues:
            channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

        while True:
            # Process events for a short time, then check for batch timeout
            channel.connection.process_data_events(time_limit=BATCH_TIMEOUT_SECONDS)
            if documents_buffer:
                archive_and_ack_batch(ch, es_client, documents_buffer)

    except KeyboardInterrupt:
        print("\n🛑 DLQ Archiver: Arrêt demandé.")
    except Exception as e:
        print(f"❌ ERREUR CRITIQUE dans le DLQ Archiver: {e}")
    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("✅ DLQ Archiver: Connexion RabbitMQ fermée.")

def archive_and_ack_batch(channel, es_client, buffer):
    """Archive a batch of messages and then ACK them."""
    if not buffer:
        return
        
    print(f"📦 DLQ Archiver: Tentative d'archivage d'un batch de {len(buffer)} documents...")
    docs_to_es = [doc for _, doc in buffer]
    
    try:
        helpers.bulk(es_client, docs_to_es)
        last_delivery_tag = buffer[-1][0]
        channel.basic_ack(delivery_tag=last_delivery_tag, multiple=True)
        print(f"   -> Batch archivé et acquitté avec succès (jusqu'au tag {last_delivery_tag}).")
        buffer.clear()
    except Exception as e:
        print(f"❌ ERREUR: Impossible d'indexer le batch dans Elasticsearch: {e}. Les messages ne seront pas acquittés.")
        # We don't clear the buffer and don't ack, so it will be retried on next connection.

if __name__ == "__main__":
    main()