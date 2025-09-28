import pika
import os
import json
import time
import argparse
from datetime import datetime, timezone
from elasticsearch import Elasticsearch, helpers

# --- Configuration ---
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = "failed_messages_archive"

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
            es_client = Elasticsearch(ELASTICSEARCH_URL)
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
    Interroge Elasticsearch et republie les messages correspondants dans RabbitMQ.
    """
    query = {
        "bool": {
            "must": []
        }
    }

    if args.service_name:
        # Utiliser une requête 'term' sur le champ '.keyword' pour une correspondance exacte.
        query["bool"]["must"].append({"term": {"service_name.keyword": args.service_name}})
    
    if args.error_reason:
        query["bool"]["must"].append({"wildcard": {"error_reason": f"*{args.error_reason}*"}})

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
    
    # Utilisation de helpers.scan pour récupérer efficacement tous les résultats
    try:
        for doc in helpers.scan(es_client, index=ELASTIC_INDEX_NAME, query={"query": query}):
            source = doc["_source"]
            original_payload = source.get("original_payload", {})
            original_exchange = source.get("original_exchange")
            original_routing_key = source.get("original_routing_key")

            if not original_exchange or not original_routing_key:
                if args.verbose:
                    print(f"⚠️ Message ignoré (ID: {doc['_id']}) car il manque l'exchange ou la routing key d'origine.")
                continue

            if args.verbose:
                print(f" reprocessing message from service '{source.get('service_name')}' with original key '{original_routing_key}'...")

            if not args.dry_run:
                rabbit_channel.basic_publish(
                    exchange=original_exchange,
                    routing_key=original_routing_key,
                    body=json.dumps(original_payload).encode('utf-8'),
                    properties=pika.BasicProperties(
                        delivery_mode=pika.DeliveryMode.Persistent,
                        # Les headers sont intentionnellement omis pour réinitialiser le statut
                    )
                )
            total_requeued += 1

    except Exception as e:
        print(f"❌ Erreur lors de la récupération ou de la republication des messages : {e}")
        return

    print("\n--- Résumé de l'Opération ---")
    if args.dry_run:
        print(f"DRY RUN: {total_requeued} message(s) correspondent aux critères et seraient re-publiés.")
    else:
        print(f"SUCCÈS: {total_requeued} message(s) ont été re-publiés avec succès.")
    print("-----------------------------\n")

def main():
    parser = argparse.ArgumentParser(description="Outil pour re-publier des messages depuis la DLQ archivée dans Elasticsearch.")
    parser.add_argument("--service-name", type=str, help="Filtrer par nom de service exact (ex: template-llm-service).")
    parser.add_argument("--error-reason", type=str, help="Filtrer par raison de l'erreur (supporte les wildcards, ex: *timeout*).")
    parser.add_argument("--start-date", type=str, help="Date de début (format ISO: YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--end-date", type=str, help="Date de fin (format ISO: YYYY-MM-DDTHH:MM:SS).")
    parser.add_argument("--dry-run", action="store_true", help="Simule l'opération et affiche le nombre de messages correspondants sans les publier.")
    parser.add_argument("--verbose", action="store_true", help="Affiche les détails de chaque message traité.")
    
    args = parser.parse_args()

    if args.dry_run:
        print("🟡 MODE DRY RUN ACTIVÉ. Aucun message ne sera réellement publié.")

    try:
        es_client = get_elasticsearch_client()
        rabbit_conn = get_rabbitmq_connection()
        rabbit_channel = rabbit_conn.channel()

        requeue_messages(es_client, rabbit_channel, args)

    except ConnectionError as e:
        print(f"❌ Impossible d'établir les connexions nécessaires: {e}")
    finally:
        if 'rabbit_conn' in locals() and rabbit_conn.is_open:
            rabbit_conn.close()
            print("✅ Connexion RabbitMQ fermée.")

if __name__ == "__main__":
    main()