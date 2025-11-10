import pika
import os
import json
import time
import hashlib
from datetime import datetime
from elasticsearch import Elasticsearch, helpers
from es_mapping import INDEX_MAPPING

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
DLQ_QUEUES_STR = os.environ.get("DLQ_QUEUES", "embedding_queue_dlq,insertion_siteweb_queue_dlq,llm_templating_queue_dlq,website_processing_queue_dlq")
# TIER 2: Read Elasticsearch connection details from environment
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")

ELASTIC_INDEX_NAME = "failed_messages_archive"
BATCH_SIZE = 50
BATCH_TIMEOUT_SECONDS = 5.0

class DLQArchiver:
    def __init__(self):
        self.es_client = None
        self.rabbit_conn = None
        self.channel = None
        self.documents_buffer = []
        self.last_archive_time = time.time()
        self.dlq_queues = [q.strip() for q in DLQ_QUEUES_STR.split(',')]

    def connect(self):
        """Establishes and re-establishes connections to RabbitMQ and Elasticsearch."""
        # Connect to RabbitMQ
        for i in range(10):
            try:
                self.rabbit_conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
                self.channel = self.rabbit_conn.channel()
                print("✅ DLQ Archiver: Connecté à RabbitMQ.")
                break
            except pika.exceptions.AMQPConnectionError:
                print(f"⏳ DLQ Archiver: En attente de RabbitMQ... {i+1}s")
                time.sleep(i + 1)
        if not self.rabbit_conn or self.rabbit_conn.is_closed:
            raise ConnectionError("❌ DLQ Archiver: Impossible de se connecter à RabbitMQ après plusieurs tentatives.")

        # Connect to Elasticsearch
        for i in range(10):
            try:
                # TIER 2: Use credentials for Elasticsearch connection if provided
                if ES_USERNAME and ES_PASSWORD:
                    self.es_client = Elasticsearch(
                        ELASTICSEARCH_URL,
                        basic_auth=(ES_USERNAME, ES_PASSWORD)
                    )
                else:
                    self.es_client = Elasticsearch(ELASTICSEARCH_URL)

                if self.es_client.ping():
                    print("✅ DLQ Archiver: Connecté à Elasticsearch.")
                    break
                else:
                    raise ConnectionError("Ping Elasticsearch a échoué.")
            except Exception as e:
                print(f"⏳ DLQ Archiver: En attente d'Elasticsearch... {i+1}s ({e})")
                time.sleep(i + 1)
        if not self.es_client:
            raise ConnectionError("❌ DLQ Archiver: Impossible de se connecter à Elasticsearch.")

    def setup_queues(self):
        """Declares queues and sets up consumers."""
        print("   -> Configuration des files d'attente DLQ...")
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("Le canal RabbitMQ n'est pas ouvert pour la configuration.")
            
        # Ensure index exists in Elasticsearch
        if not self.es_client.indices.exists(index=ELASTIC_INDEX_NAME):
            print(f"Index '{ELASTIC_INDEX_NAME}' non trouvé. Création avec le mapping correct...")
            self.es_client.indices.create(index=ELASTIC_INDEX_NAME, body=INDEX_MAPPING)

        for queue_name in self.dlq_queues:
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.channel.basic_consume(queue=queue_name, on_message_callback=self._callback, auto_ack=False)
        print("   -> Consommation démarrée sur les files d'attente.")

    def _callback(self, ch, method, properties, body):
        """Callback to buffer incoming messages."""
        print(f"📥 DLQ Archiver: Message reçu de la queue '{method.routing_key}' (tag: {method.delivery_tag})")
        doc = self._process_message_to_doc(body, properties)
        self.documents_buffer.append((method.delivery_tag, doc))

    def _remove_embedding_recursively(self, obj):
        """Recursively finds and removes/replaces 'embedding' keys from an object."""
        if isinstance(obj, dict):
            for key in list(obj.keys()):
                if key == 'embedding':
                    # Replace the large vector with a placeholder for context
                    vector_len = len(obj[key]) if isinstance(obj[key], list) else 'N/A'
                    obj[key] = f"Vector of size {vector_len} (removed for archiving)"
                else:
                    self._remove_embedding_recursively(obj[key])
        elif isinstance(obj, list):
            for item in obj:
                self._remove_embedding_recursively(item)
        return obj

    def _process_message_to_doc(self, body, properties):
        """Transforms a RabbitMQ message into an Elasticsearch document with robust parsing."""
        message_hash = hashlib.sha256(body).hexdigest()

        original_payload = None
        try:
            parsed_body = json.loads(body)
            if isinstance(parsed_body, dict):
                original_payload = parsed_body
            else:
                original_payload = {"value": parsed_body}
        except json.JSONDecodeError:
            original_payload = {"raw_body": body.decode('utf-8', errors='ignore')}
        
        sanitized_payload = self._remove_embedding_recursively(original_payload)
        
        headers = properties.headers or {}
        
        if 'x-service-name' in headers:
            service_name = headers.get('x-service-name', 'N/A')
            error_reason = headers.get('x-error-reason', 'Raison inconnue')
            original_exchange = headers.get('x-original-exchange', 'N/A')
            original_routing_key = headers.get('x-original-routing-key', 'N/A')
            retry_count = headers.get('x-retry-count', self._get_retry_count(headers))
        else:
            error_reason, original_exchange, original_routing_key, original_queue = "Raison inconnue", "N/A", "N/A", "N/A"
            if 'x-death' in headers and headers['x-death']:
                death_info = headers['x-death'][0]
                error_reason = death_info.get('reason', 'N/A')
                original_exchange = death_info.get('exchange', 'N/A')
                original_routing_key = death_info.get('routing-keys', ['N/A'])[0]
                original_queue = death_info.get('queue', 'N/A')
            retry_count = self._get_retry_count(headers)
            service_name = original_queue.replace('_queue', '').replace('_retry', '')

        try:
            safe_retry_count = int(retry_count) if retry_count is not None else 0
        except (ValueError, TypeError):
            safe_retry_count = 0
            
        source_doc = {
            "@timestamp": datetime.utcnow().isoformat(),
            "service_name": str(service_name or "N/A"), "error_reason": str(error_reason or "Raison inconnue"),
            "retry_count": safe_retry_count, "original_exchange": str(original_exchange or "N/A"),
            "original_routing_key": str(original_routing_key or "N/A"), "original_payload": sanitized_payload,
        }
        return {
            "_index": ELASTIC_INDEX_NAME,
            "_id": message_hash,
            "_source": source_doc
        }

    def _get_retry_count(self, headers):
        if headers and 'x-death' in headers:
            for death in headers['x-death']:
                if "retry" in death.get('queue', ''):
                    return death.get('count', 0)
        return 0

    def archive_and_ack_batch(self):
        """Archives a batch of messages and ACKs/NACKs them individually."""
        if not self.documents_buffer:
            return
            
        buffer_copy = list(self.documents_buffer)
        self.documents_buffer.clear()
        
        print(f"📦 DLQ Archiver: Tentative d'archivage d'un batch de {len(buffer_copy)} documents...")
        docs_to_es = [doc for _, doc in buffer_copy]
        
        try:
            # Use raise_on_error=False to get a report of failures instead of an exception
            success_count, errors = helpers.bulk(self.es_client, docs_to_es, raise_on_error=False)
            
            print(f"   -> Résultat du bulk: {success_count} succès, {len(errors)} échecs.")

            if not errors:
                # If everything succeeded, we can ack the whole batch at once for efficiency.
                last_delivery_tag = buffer_copy[-1][0]
                self.channel.basic_ack(delivery_tag=last_delivery_tag, multiple=True)
                print(f"   -> Batch entièrement archivé et acquitté avec succès (jusqu'au tag {last_delivery_tag}).")
            else:
                print(f"   -> ❌ Erreurs d'indexation détectées. Traitement individuel des acquittements.")
                # Create a set of failed document IDs for quick lookup
                failed_doc_ids = {err['index']['_id']: err['index']['error'] for err in errors}
                
                for delivery_tag, doc in buffer_copy:
                    doc_id = doc['_id']
                    if doc_id in failed_doc_ids:
                        error_details = failed_doc_ids[doc_id]
                        print(f"     -> NACK du message (tag: {delivery_tag}) car l'archivage a échoué.")
                        print(f"     -> Raison de l'échec pour ID {doc_id}: {error_details.get('type')}: {error_details.get('reason')[:500]}...")
                        self.channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
                    else:
                        self.channel.basic_ack(delivery_tag=delivery_tag)
                print("   -> Les messages échoués ont été routés vers l'infrastructure de retry/DLQ.")

        except Exception as e:
            print(f"❌ ERREUR CRITIQUE lors de la communication avec Elasticsearch: {e}. NACK de tout le batch (requeue=True).")
            last_delivery_tag = buffer_copy[-1][0]
            self.channel.basic_nack(delivery_tag=last_delivery_tag, multiple=True, requeue=True)
        finally:
            # The buffer is already cleared, but we ensure it's empty to avoid any reprocessing in memory.
            self.documents_buffer.clear()


    def start_consuming(self):
        """Main resilient loop to consume messages."""
        self.connect()
        self.setup_queues()

        while True:
            try:
                self.channel.connection.process_data_events(time_limit=1)
                
                batch_is_full = len(self.documents_buffer) >= BATCH_SIZE
                timeout_reached = (time.time() - self.last_archive_time) > BATCH_TIMEOUT_SECONDS
                
                if self.documents_buffer and (batch_is_full or timeout_reached):
                    self.archive_and_ack_batch()
                    self.last_archive_time = time.time()

            except (pika.exceptions.StreamLostError, pika.exceptions.AMQPConnectionError):
                print("🔴 Connexion RabbitMQ perdue. Tentative de reconnexion...")
                self.connect()
                self.setup_queues()
            except KeyboardInterrupt:
                print("\n🛑 DLQ Archiver: Arrêt demandé.")
                break
            except Exception as e:
                print(f"❌ Erreur inattendue dans la boucle principale: {e}. Tentative de reconnexion...")
                time.sleep(5)
                self.connect()
                self.setup_queues()

def main():
    print("🚀 DLQ Archiver: Démarrage du service...")
    try:
        archiver = DLQArchiver()
        archiver.start_consuming()
    except ConnectionError as e:
        print(f"❌ Le service n'a pas pu démarrer. Erreur de connexion initiale: {e}")
    except Exception as e:
        print(f"❌ Une erreur fatale est survenue: {e}")
    finally:
        print("✅ DLQ Archiver: Service arrêté.")

if __name__ == "__main__":
    main()