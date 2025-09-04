import pika
import json
from categories_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from categories_processor_service.core.processor import process_categories_data_for_embedding # Importe la logique métier

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        self.exchange_name = 'data_exchange_categories'
        self.routing_key = 'new_data.category'
        self.queue_name = 'categories_processing_queue'

        # Déclare l'exchange où il consomme
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        print("✅ Consumer initialisé.")

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        print("📥 Categories-Processor: Message reçu.")
        data = json.loads(body)
        categories_data = data.get('data', {})
        bdd = data.get('database', "qdrant")

        if not categories_data:
            print("❌ Categories-Processor: Aucune donnée trouvée dans le message.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        id_categorie = categories_data.get('id_categorie', 'ID inconnu')
        print(f"\n📥 Categories-Processor: Message reçu pour '{id_categorie}'.")

        # 1. Appelle la logique métier PURE
        output_message = process_categories_data_for_embedding(categories_data,bdd)
        
        # 2. Utilise le publisher pour envoyer le résultat
        self.publisher.publish_message(output_message)

        # 3. Acquitte le message original
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        """
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
        print("👂 Categories-Processor: En attente de messages...")
        self.channel.start_consuming()