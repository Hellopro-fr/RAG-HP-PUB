import pika, os, time, json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from common_utils.autres.CollectionName import CollectionName

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
EXCHANGE_NAME = 'data_exchange'
ROUTING_KEY_PRODUCT = 'new_data.product'
WATCH_DIRECTORY = './data'

def publish_file_content(filepath, channel):
    try:
        print(f"📖 Ingestion-Service: Lecture du fichier '{filepath}'...")
        with open(filepath, 'r') as f:
            for line in f:
                if line.strip():
                    data = {}
                    data_json = json.loads(line.strip())
                    data["data"] = data_json
                    data["collection"] = CollectionName.PRODUIT
                    body = json.dumps(data)
                    print(f"📥 Ingestion-Service: Publication du message pour '{body.encode('utf-8')}'...")
                    channel.basic_publish(exchange=EXCHANGE_NAME, routing_key=ROUTING_KEY_PRODUCT, body=body.encode('utf-8'), properties=pika.BasicProperties(delivery_mode=2))
                    product_data = json.loads(body)
                    print(f"  ✉️  Produit '{product_data['data']['id_produit']}' publié.")
        print(f"✅ Ingestion-Service: Fichier '{filepath}' traité avec succès.")
    except Exception as e:
        print(f"❌ Ingestion-Service: Erreur lors du traitement du fichier '{filepath}': {e}")

class FileCreatedHandler(FileSystemEventHandler):
    def __init__(self, channel): self.channel = channel
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.jsonl'):
            print(f"\n🔎 Ingestion-Service: Nouveau fichier détecté: {event.src_path}")
            time.sleep(1); publish_file_content(event.src_path, self.channel)

def main():
    """Point d'entrée principal pour le service d'ingestion."""
    print("🚀 Ingestion-Service: Démarrage...")
    connection = None
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("✅ Ingestion-Service: Connecté à RabbitMQ."); break
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ Ingestion-Service: RabbitMQ n'est pas prêt. Nouvelle tentative dans {i+1}s..."); time.sleep(1)
    if not connection: print("❌ Ingestion-Service: Arrêt."); exit(1)
    channel = connection.channel()
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='topic', durable=True)
    observer = Observer()
    observer.schedule(FileCreatedHandler(channel), WATCH_DIRECTORY, recursive=False)
    observer.start()
    print(f"👂 Ingestion-Service: Surveillance du dossier '{WATCH_DIRECTORY}' démarrée...")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Ingestion-Service: Arrêt demandé."); observer.stop()
    finally:
        observer.join(); connection.close()
        print("✅ Ingestion-Service: Connexion et observateur fermés.")

if __name__ == "__main__":
    main()