import pika
import json
from vllm import LLM
from template_llm_service.messaging.publisher import Publisher
from template_llm_service.core.processor import classify_page_template
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher, llm: LLM, tokenizer, llm_config: dict):
        self.channel = connection.channel()
        self.publisher = publisher
        self.llm = llm
        self.tokenizer = tokenizer
        self.llm_config = llm_config
        
        self.exchange_name = 'cleaned_data_exchange'
        self.routing_key = 'data.website.ready_for_classification'
        self.queue_name = 'llm_classification_queue'

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
        try:
            message = json.loads(body)
            print(f"\n📥 template-llm-service: Message reçu pour classification.")

            output_message = classify_page_template(self.llm, self.tokenizer, self.llm_config, message)
            
            self.publisher.publish_message(output_message)

        except Exception as e:
            print(f"❌ Erreur lors du traitement du message : {e}")
        
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            print("   -> Message acquitté.")
            
    def start_consuming(self):
        for i in range(3):
            try:
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 template-llm-service: En attente de messages...")
                self.channel.start_consuming()
                break  # Si start_consuming se termine normalement, on sort de la boucle
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}, tentative de reconnexion...")
                self.connect()
