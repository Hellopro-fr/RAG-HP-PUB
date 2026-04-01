import logging
import pika
import json
from product_processor_service.messaging.publisher import Publisher  # Importe notre publisher local
from product_processor_service.core.processor import process_product_data_for_embedding # Importe la logique métier
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.autres.DLQProperties import DLQProperties
from common_utils.metrics.prometheus import measure_processing_time

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        """
        Initialise le consumer.
        Il a besoin d'une connexion ET d'une instance du publisher.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'data_exchange_produits'
        self.routing_key = 'new_data.product'
        self.queue_name = 'product_processing_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        self.rabbitmq_connection = RabbitMQConnection()
        self.connect()
        logger.info("✅ Consumer initialisé.")

    def connect(self):
        """
        Établit la connexion et configure le consumer.
        """
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()

        # --- Infrastructure DLQ Finale ---
        self.channel.exchange_declare(exchange=self.dead_letter_exchange, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(exchange=self.dead_letter_exchange, queue=self.dead_letter_queue_name, routing_key=self.routing_key)

        # --- Infrastructure Retry ---
        self.channel.exchange_declare(exchange=self.retry_exchange, exchange_type='topic', durable=True)
        retry_queue_args = {
            'x-message-ttl': RETRY_TTL_MS,
            'x-dead-letter-exchange': self.exchange_name,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # --- Queue Principale ---
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        main_queue_args = {
            'x-dead-letter-exchange': self.retry_exchange,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.queue_name, durable=True, arguments=main_queue_args)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)

    def _get_retry_count(self, properties: pika.BasicProperties) -> int:
        if properties.headers and 'x-death' in properties.headers:
            for death in properties.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0

    @measure_processing_time(service_name="product-processor-service")
    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        try:
            logger.info("📥 Product-Processor: Message reçu.")
            data = json.loads(body)
            product_data = data.get('data', {})
            bdd = data.get('database', "qdrant")
            origin = data.get('origin', 'bo')
            mode = data.get('mode', 'default')

            if not product_data:
                raise ValueError("Aucune donnée de produit trouvée dans le message.")
            
            product_id = product_data.get('id_produit', 'ID inconnu')
            logger.info(f"📥 Product-Processor: Message reçu pour '{product_id}'.")

            # 1. Appelle la logique métier PURE
            output_message = process_product_data_for_embedding(product_data,bdd,origin,mode)
            
            # 2. Utilise le publisher pour envoyer le résultat
            self.publisher.publish_message(output_message)

            # 3. Acquitte le message original
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message est invalide.
            logger.error(f"❌ Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}")
            dlq_props = DLQProperties.create_dlq_properties(e, 'product-processor-service', 0, method)
            ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            # Erreur potentiellement transitoire.
            retry_count = self._get_retry_count(properties)
            if retry_count < MAX_RETRIES:
                logger.warning(f"❌ Erreur inattendue (essai {retry_count + 1}/{MAX_RETRIES + 1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            else:
                logger.error(f"❌ Échec après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale. Erreur: {e}")
                dlq_props = DLQProperties.create_dlq_properties(e, 'product-processor-service', MAX_RETRIES, method)
                ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        for i in range(3):
            try: 
                """
                Démarre la boucle d'écoute des messages.
                """
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                logger.info("👂 Product-Processor: En attente de messages...")
                self.channel.start_consuming()
                break  # Si start_consuming se termine normalement, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                logger.warning(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connect()