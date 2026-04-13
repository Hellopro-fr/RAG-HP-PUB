import pika
import json
import logging
import time
from di_database_qdrant_service.messaging.publisher import Publisher  # Importe notre publisher local
from di_database_qdrant_service.core.processor import insertion_data # Importe la logique métier
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
        self.publisher = publisher

        # Noms des composants RabbitMQ
        self.exchange_name = 'devis_embedded_data_exchange'
        self.routing_key = 'data.devis.ready_for_insertion'
        self.queue_name = 'insertion_devis_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'

        self.rabbitmq_connection = RabbitMQConnection()
        self.connect()
        logger.info("Consumer initialise.")

    def connect(self):
        """
        Établit une connexion RabbitMQ via la fonction utilitaire.
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

    @measure_processing_time(service_name="di-database-qdrant-service")
    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback privé qui orchestre le traitement d'un message.
        """
        try:
            devis_data = json.loads(body)
            logger.info("Processing devis lead_id=%s", devis_data.get("data", [{}])[0].get("lead_id", "unknown"))

            # 1. Appelle la logique métier PURE
            output_message = insertion_data(devis_data)
            
            # 2. Utilise le publisher pour envoyer le résultat
            if output_message:
                self.publisher.publish_message(output_message)

            # 3. Acquitte le message original
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message est invalide.
            logger.error("Erreur permanente. Message envoye a la DLQ finale. Erreur: %s", e, exc_info=True)
            try:
                dlq_props = DLQProperties.create_dlq_properties(e, 'di-database-qdrant-service', 0, method)
                ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                logger.warning("Channel closed during error handling, message will be redelivered")

        except Exception as e:
            # Erreur potentiellement transitoire (ex: BDD indisponible).
            retry_count = self._get_retry_count(properties)
            try:
                if retry_count < MAX_RETRIES:
                    logger.warning(f"Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES + 1}). Message renvoye pour une nouvelle tentative. Erreur: %s", e, exc_info=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                else:
                    logger.error(f"Echec apres {MAX_RETRIES + 1} tentatives. Message envoye a la DLQ finale. Erreur: %s", e, exc_info=True)
                    dlq_props = DLQProperties.create_dlq_properties(e, 'di-database-qdrant-service', MAX_RETRIES, method)
                    ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body, properties=dlq_props)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                logger.warning("Channel closed during error handling, message will be redelivered")

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        """
        attempt = 0
        while True:
            try:
                self.channel.basic_qos(prefetch_count=10)
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                logger.info("Database-Devis-Processor: En attente de messages...")
                self.channel.start_consuming()
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker, pika.exceptions.StreamLostError, pika.exceptions.ChannelWrongStateError) as e:
                attempt += 1
                wait_time = min(5 * attempt, 30)
                logger.warning(f"Connexion perdue: {e}, tentative de reconnexion dans {wait_time}s...")
                time.sleep(wait_time)
                self.connect()
                attempt = 0