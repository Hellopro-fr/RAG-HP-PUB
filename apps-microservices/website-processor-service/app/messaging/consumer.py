import pika
import json
from website_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from website_processor_service.core.processor import process_website_data_for_embedding # Importe la logique métier
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3 # Nombre de tentatives avant d'envoyer à la DLQ finale
RETRY_TTL_MS = 30000 # 30 secondes d'attente avant une nouvelle tentative

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        # Noms des composants RabbitMQ
        self.exchange_name = 'data_exchange_siteweb'
        self.routing_key = 'new_data.website'
        self.queue_name = 'website_processing_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        self.rabbitmq_connection = RabbitMQConnection()
        self.connect()
        print("✅ Consumer initialisé.")

    def connect(self):
        """
        Établit la connexion et configure le consumer, y compris les queues de retry et de dead-letter.
        """
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()
        
        # --- 1. Infrastructure pour les échecs FINALS (Dead-Letter Queue) ---
        self.channel.exchange_declare(exchange=self.dead_letter_exchange, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(exchange=self.dead_letter_exchange, queue=self.dead_letter_queue_name, routing_key=self.routing_key)

        # --- 2. Infrastructure pour les tentatives (Retry Queue) ---
        self.channel.exchange_declare(exchange=self.retry_exchange, exchange_type='topic', durable=True)
        retry_queue_args = {
            'x-message-ttl': RETRY_TTL_MS,
            'x-dead-letter-exchange': self.exchange_name, # Renvoyer au main exchange après TTL
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # --- 3. Configuration de la Queue Principale ---
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        main_queue_args = {
            'x-dead-letter-exchange': self.retry_exchange, # Les échecs vont d'abord vers le retry
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.queue_name, durable=True, arguments=main_queue_args)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)

    def _get_retry_count(self, properties: pika.BasicProperties) -> int:
        """Inspecte les headers pour compter le nombre de tentatives."""
        if properties.headers and 'x-death' in properties.headers:
            for death in properties.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message avec logique de retry.
        """
        print("📥 Website-Processor: Message reçu.")
        try:
            data = json.loads(body)
            website_data = data.get('data', {})
            bdd = data.get('database', "qdrant")

            if not website_data or not website_data.get('text'):
                raise ValueError("Données invalides (contenu vide ou 'text' manquant).")

            print(f"\n📥 Website-Processor: Message reçu pour URL: {website_data.get('url', 'URL inconnue')}")
            
            # 1. Appelle la logique métier PURE
            output_message = process_website_data_for_embedding(website_data,bdd)
            
            if not output_message.get("data", {}).get("page_type",""):
                self.publisher.routing_key = 'data.ready_for_templating'
                print("🔄 Website-Processor: Redirection vers la vérification de template")
            else:
                self.publisher.routing_key = 'data.ready_for_embedding'
                print("➡️ Website-Processor: Message prêt pour l'embedding")
            
            # 2. Utilise le publisher pour envoyer le résultat
            self.publisher.publish_message(output_message)

            # 3. Acquitte le message original
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message ne sera jamais valide.
            print(f"❌ Website-Processor: Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}")
            dlq_props = DLQProperties.create_dlq_properties(e, 'website-processor-service', 0, method)
            ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            # Erreur potentiellement transitoire (ex: service externe indisponible).
            retry_count = self._get_retry_count(properties)
            if retry_count < MAX_RETRIES:
                print(f"❌ Website-Processor: Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES+1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            else:
                print(f"❌ Website-Processor: Échec après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale. Erreur: {e}")
                dlq_props = DLQProperties.create_dlq_properties(e, 'website-processor-service', MAX_RETRIES, method)
                ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                ch.basic_ack(delivery_tag=method.delivery_tag)

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