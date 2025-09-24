import pika
import json
import asyncio
from embedding_service.messaging.publisher import Publisher
from embedding_service.core.processor import embed_input_data
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

MAX_RETRIES = 3
RETRY_TTL_MS = 30000

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher, **kwargs):
        """
        Initialise le consumer avec une logique de retry et DLQ.
        """
        self.channel = connection.channel()
        self.publisher = publisher
        
        # Noms des composants RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        self.queue_name = 'embedding_queue'
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
            'x-dead-letter-exchange': self.exchange_name,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # --- 3. Configuration de la Queue Principale ---
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

    def _on_message_callback(self, ch, method, properties, body):
        """
        Callback qui orchestre le traitement d'un message avec logique de retry/DLQ.
        """
        try:
            input_data = json.loads(body)
            print(f"\n📥 Embedding-Service: Message reçu pour la collection '{input_data.get('collection', 'inconnue')}'.")

            # 1. Appelle la logique métier PURE
            output_message = asyncio.run(embed_input_data(input_data))
            
            # 2. Utilise le publisher pour envoyer le résultat
            self.publisher.publish_message(output_message)

            # 3. Acquitte le message original
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except (json.JSONDecodeError, ValueError) as e:
            # Erreur permanente: le message est invalide.
            print(f"❌ Erreur permanente. Message envoyé à la DLQ finale. Erreur: {e}")
            ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            # Erreur potentiellement transitoire (ex: service d'embedding indisponible).
            retry_count = self._get_retry_count(properties)
            if retry_count < MAX_RETRIES:
                print(f"❌ Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES + 1}). Message renvoyé pour une nouvelle tentative. Erreur: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # NACK pour retry via DLX
            else:
                print(f"❌ Échec après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale. Erreur: {e}")
                ch.basic_publish(exchange=self.dead_letter_exchange, routing_key=self.routing_key, body=body)
                ch.basic_ack(delivery_tag=method.delivery_tag) # ACK pour confirmer le déplacement

    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages.
        """
        for i in range(3):
            try:
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 Embedding-Service: En attente de messages...")
                self.channel.start_consuming()
                break  # Si start_consuming se termine normalement, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connect()