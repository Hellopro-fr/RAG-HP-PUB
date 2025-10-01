import pika
import os
import json
import time
import argparse
from datetime import datetime, timezone
from elasticsearch import Elasticsearch

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = "failed_messages_archive_v3" # Point to the new, correctly mapped index
PAGE_SIZE = 100  # Number of documents to process per Elasticsearch query

def get_rabbitmq_connection():
    """Tente de se connecter à RabbitMQ avec des retries."""
    for i in range(5):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("✅ Re-queuer: Connecté à RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ Re-queuer: En attente de RabbitMQ... {i+1}s")
            time.sleep(i + 1)
    raise ConnectionError("❌ Re-queuer: Impossible de se connecter à RabbitMQ.")

def get_elasticsearch_client():
    """Tente de se connecter à Elasticsearch avec des retries."""
    for i in range(5):
        try:
            es_client = Elasticsearch(ELASTICSEARCH_URL, request_timeout=30)
            if es_client.ping():
                print("✅ Re-queuer: Connecté à Elasticsearch.")
                return es_client
            else:
                raise ConnectionError("Ping Elasticsearch a échoué.")
        except Exception as e:
            print(f"⏳ Re-queuer: En attente d'Elasticsearch... {i+1}s ({e})")
            time.sleep(i + 1)
    raise ConnectionError("❌ Re-queuer: Impossible de se connecter à Elasticsearch.")

def requeue_messages(es_client, rabbit_channel, args):
    """
    Interroge Elasticsearch en utilisant la pagination `search_after` et republie les messages.
    """
    query = {
        "bool": {
            "must": [],
            "must_not": [
                {"exists": {"field": "requeued_at"}}
            ]
        }
    }

    # Dynamically build the query from --filter arguments
    if args.filter:
        for f in args.filter:
            if ':' not in f:
                print(f"⚠️ Filtre invalide ignoré: '{f}'. Le format doit être 'champ:valeur'.")
                continue
            
            key, value = f.split(':', 1)
            if '*' in value:
                # For wildcard, always append .keyword if not already present.
                field_name = key if key.endswith('.keyword') else f"{key}.keyword"
                query["bool"]["must"].append({"wildcard": {field_name: {"value": value}}})
            else:
                # Use term query for exact matches (user should provide .keyword if needed)
                query["bool"]["must"].append({"term": {key: value}})

    time_range = {}
    if args.start_date:
        time_range["gte"] = args.start_date
    if args.end_date:
        time_range["lte"] = args.end_date
    
    if time_range:
        query["bool"]["must"].append({"range": {"@timestamp": time_range}})
    
    print("\n--- Requête Elasticsearch ---")
    print(json.dumps({"query": query}, indent=2))
    print("-----------------------------\n")

    total_requeued = 0
    search_after_value = None
    
    while True:
        try:
            body = {
                "size": PAGE_SIZE,
                "query": query,
                "sort": [
                    {"@timestamp": "asc"}, # Primary sort key
                    {"_doc": "asc"}       # Efficient tie-breaker for documents with the same timestamp
                ]
            }
            if search_after_value:
                body["search_after"] = search_after_value

            response = es_client.search(
                index=ELASTIC_INDEX_NAME,
                body=body
            )

            hits = response['hits']['hits']
            if not hits:
                break # Fin de la pagination

            for doc in hits:
                source = doc["_source"]
                doc_id = doc["_id"]
                original_payload = source.get("original_payload", {})
                original_exchange = source.get("original_exchange")
                original_routing_key = source.get("original_routing_key")

                if not original_exchange or not original_routing_key:
                    if args.verbose:
                        print(f"⚠️ Message ignoré (ID: {doc_id}) car il manque l'exchange ou la routing key d'origine.")
                    continue

                if args.verbose:
                    print(f" Reprocessing message from service '{source.get('service_name')}' with original key '{original_routing_key}'...")

                if not args.dry_run:
                    rabbit_channel.basic_publish(
                        exchange=original_exchange,
                        routing_key=original_routing_key,
                        body=json.dumps(original_payload).encode('utf-8'),
                        properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent)
                    )
                    
                    update_body = {"doc": {"requeued_at": datetime.utcnow().isoformat()}}
                    es_client.update(index=ELASTIC_INDEX_NAME, id=doc_id, body=update_body)
                    
                    if args.verbose:
                        print(f"   -> Marqué comme re-publié dans Elasticsearch (ID: {doc_id})")

                total_requeued += 1
            
            search_after_value = hits[-1]['sort']

        except Exception as e:
            print(f"❌ Erreur lors de la récupération ou de la republication des messages : {e}")
            break

    print("\n--- Résumé de l'Opération ---")
    if args.dry_run:
        print(f"DRY RUN: {total_requeued} message(s) correspondent aux critères et seraient re-publiés.")
    else:
        print(f"SUCCÈS: {total_requeued} message(s) ont été re-publiés et marqués dans l'archive.")
    print("-----------------------------\n")

def run_requeue_cycle(args):
    """Encapsulates a single run of connecting, requeueing, and disconnecting."""
    rabbit_conn = None
    try:
        es_client = get_elasticsearch_client()
        rabbit_conn = get_rabbitmq_connection()
        rabbit_channel = rabbit_conn.channel()

        requeue_messages(es_client, rabbit_channel, args)

    except ConnectionError as e:
        print(f"❌ Impossible d'établir les connexions pour ce cycle: {e}")
    finally:
        if rabbit_conn and rabbit_conn.is_open:
            rabbit_conn.close()
            print("✅ Connexion RabbitMQ fermée pour ce cycle.")

def main():
    parser = argparse.ArgumentParser(
        description="Outil pour re-publier des messages depuis la DLQ archivée dans Elasticsearch.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    filter_help = """
Filtrer les messages à re-publier. Peut être utilisé plusieurs fois.
Format: 'champ:valeur'. Supporte les wildcards (*).
Pour les recherches exactes sur du texte, utilisez le suffixe '.keyword'.

Exemples:
  --filter "service_name.keyword:template-llm-service"
  --filter "error_reason:*timeout*"
  --filter "original_payload.data.url.keyword:*example.com/product/123*"
"""
    parser.add_argument("--filter", type=str, action='append', help=filter_help)
    parser.add_argument("--start-date", type=str, help="Date de début (format ISO: YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--end-date", type=str, help="Date de fin (format ISO: YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--dry-run", action="store_true", help="Simule l'opération et affiche le nombre de messages correspondants sans les publier.")
    parser.add_argument("--verbose", action="store_true", help="Affiche les détails de chaque message traité.")
    parser.add_argument("--watch", action="store_true", help="Exécute le script en boucle pour republier automatiquement les nouveaux messages.")
    parser.add_argument("--interval", type=int, default=60, help="Intervalle d'attente en secondes entre les cycles en mode --watch. Défaut: 60.")
    
    args = parser.parse_args()

    if args.dry_run:
        print("🟡 MODE DRY RUN ACTIVÉ. Aucun message ne sera réellement publié.")

    if args.watch:
        print(f"👁️  Entrée en mode 'watch'. Vérification toutes les {args.interval} secondes. Appuyez sur Ctrl+C pour arrêter.")
        try:
            while True:
                run_requeue_cycle(args)
                print(f"--- Cycle terminé. En attente pendant {args.interval} secondes... ---")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n🛑 Mode 'watch' arrêté par l'utilisateur.")
    else:
        # Single run mode
        run_requeue_cycle(args)

if __name__ == "__main__":
    main()