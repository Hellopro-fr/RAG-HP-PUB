import pika
import json
from product_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from product_processor_service.core.processor import process_product_data_for_embedding # Importe la logique métier

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        self.exchange_name = 'data_exchange_produits'
        self.routing_key = 'new_data.product'
        self.queue_name = 'product_processing_queue'

        # Déclare l'exchange où il consomme
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        print("✅ Consumer initialisé.")

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        print("📥 Product-Processor: Message reçu.")
        data = json.loads(body)
        product_data = data.get('data', {})
        bdd = data.get('database', "qdrant")

        if not product_data:
            print("❌ Product-Processor: Aucune donnée de produit trouvée dans le message.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        product_id = product_data.get('id_produit', 'ID inconnu')
        print(f"\n📥 Product-Processor: Message reçu pour '{product_id}'.")

        # 1. Appelle la logique métier PURE
        output_message = process_product_data_for_embedding(product_data,bdd)
        
        # 2. Utilise le publisher pour envoyer le résultat
        self.publisher.publish_message(output_message)

        # 3. Acquitte le message original
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        """
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
        print("👂 Product-Processor: En attente de messages...")
        self.channel.start_consuming()