import pika
import json
from website_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from website_processor_service.core.processor import process_website_data_for_embedding # Importe la logique métier
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        self.exchange_name = 'data_exchange_siteweb'
        self.routing_key = 'new_data.website'
        self.queue_name = 'website_processing_queue'
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
        print("📥 Website-Processor: Message reçu.")
        data = json.loads(body)
        website_data = data.get('data', {})
        bdd = data.get('database', "qdrant")

        
        if not website_data:
            print("❌ Website-Processor: Aucune donnée trouvée dans le message.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        print(f"\n📥 Website-Processor: Message reçu")
        
        try:
            # 1. Appelle la logique métier PURE
            output_message = process_website_data_for_embedding(website_data,bdd)
            
            # 2. Vérification du message de sortie par rapport au type de page pour définir la prochaine étape
            if not output_message.get("data", {}).get("page_type",""):
                # Modifier la route de publication vers "data.ready_for_template_check"
                self.publisher.routing_key = 'data.ready_for_templating'
                print("🔄 Website-Processor: Redirection du message vers la vérification de template")
            else:
                # Remettre la route par défaut pour l'embedding
                self.publisher.routing_key = 'data.ready_for_embedding'
                print("➡️ Website-Processor: Message prêt pour l'embedding")
            
            try:
                # 2. Utilise le publisher pour envoyer le résultat
                self.publisher.publish_message(output_message)

                # 3. Acquitte le message original
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                print(f"   -> ❌ Erreur de publication pour message {method.delivery_tag}. NACK. Erreur: {e}")
                # Si la publication échoue, on NACK le message pour qu'il soit retraité.
                self.channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            
        except Exception as e:
            print(f"❌ Website-Processor: Erreur lors du traitement des données du site web: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)  # Ne pas remettre en queue pour éviter les boucles infinies
            return

    def start_consuming(self):
        for i in range(3):
            try: 
                """
                Démarre la boucle d'écoute des messages.
                """
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 Website-Processor: En attente de messages...")
                self.channel.start_consuming()
                break  # Si start_consuming se termine normalement, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connect()