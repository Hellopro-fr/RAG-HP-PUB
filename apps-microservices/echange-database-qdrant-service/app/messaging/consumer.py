import pika
import json
from echange_database_qdrant_service.messaging.publisher import Publisher  # Importe notre publisher local
from echange_database_qdrant_service.core.processor import insertion_data # Importe la logique métier

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        self.exchange_name = 'echanges_embedded_data_exchange'

        # à modifier selon le flow de l'application
        self.routing_key = 'data.echanges.ready_for_insertion'

        # Todo: à vérifier si le nom de la queue est correct
        self.queue_name = 'insertion_echanges_queue'

        # Déclare l'exchange où il consomme
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        print("✅ Consumer initialisé.")

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        echange_data = json.loads(body)
        print(f"\n📥 Database-Echange-Processor: Message reçu.")

        # 1. Appelle la logique métier PURE
        output_message = insertion_data(echange_data)
        
        # 2. Utilise le publisher pour envoyer le résultat
        self.publisher.publish_message(output_message)

        # 3. Acquitte le message original
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        """
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
        print("👂 Database-Echange-Processor: En attente de messages...")
        self.channel.start_consuming()