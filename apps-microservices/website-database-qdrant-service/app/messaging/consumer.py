import pika
import json
from website_database_qdrant_service.messaging.publisher import Publisher  # Importe notre publisher local
from website_database_qdrant_service.core.processor import insertion_data # Importe la logique métier
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        self.exchange_name = 'siteweb_embedded_data_exchange'

        # à modifier selon le flow de l'application
        self.routing_key = 'data.siteweb.ready_for_insertion'

        # Todo: à vérifier si le nom de la queue est correct
        self.queue_name = 'insertion_siteweb_queue'
        self.rabbitmq_connection = RabbitMQConnection()
        self.connect()
        print("✅ Consumer initialisé.")

    def connect(self):
        """
        Établit une connexion RabbitMQ via la fonction utilitaire.
        """
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()
        # Déclare l'exchange où il consomme
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        website_data = json.loads(body)
        print(f"\n📥 Database-Website-Processor: Message reçu.")

        # 1. Appelle la logique métier PURE
        output_message = insertion_data(website_data)
        
        # 2. Utilise le publisher pour envoyer le résultat
        self.publisher.publish_message(output_message)

        # 3. Acquitte le message original
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        for i in range(3):
            try: 
                """
                Démarre la boucle d'écoute des messages.
                """
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 Database-Website-Processor: En attente de messages...")
                self.channel.start_consuming()
                break  # Si start_consuming se termine normalement, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connect()