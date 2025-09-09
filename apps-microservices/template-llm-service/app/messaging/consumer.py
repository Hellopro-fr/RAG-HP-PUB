import concurrent
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
        
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'

        self.rabbitmq_connection = RabbitMQConnection()
        self.connection = connection
        self.channel = self.connection.channel()

        self.prefetch_count = 16
        self.channel.basic_qos(prefetch_count=self.prefetch_count)

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

        self._setup_channel()
        print(f"✅ Consumer initialisé en mode haute performance (prefetch={self.prefetch_count}, workers={self.max_workers}).")

    def _setup_channel(self):
        """Déclare l'exchange, la queue et le binding."""
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        print(f"   -> En écoute de '{self.routing_key}'.")

    def _reconnect(self):
        """Tente de se reconnecter à RabbitMQ."""
        print("⚠️ Connexion perdue, tentative de reconnexion...")
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=self.prefetch_count) # Ré-appliquer le QOS
        self.publisher.set_connection(self.connection)
        self._setup_channel()

    def _process_message_task(self, ch, method, properties, body):
        """
        Cette fonction est la tâche exécutée par chaque worker du pool de threads.
        Elle contient la logique de traitement d'un seul message.
        """
        try:
            message = json.loads(body)
            url = message.get("data", {}).get("url", "URL Inconnue")
            print(f"\n📥 Worker thread: Début du traitement pour {url}")

            output_message = classify_page_template(self.llm, self.tokenizer, self.llm_config, message)
            
            # La publication du résultat est également faite par le worker.
            self.publisher.publish_message(output_message)

        except Exception as e:
            print(f"❌ Erreur dans le worker thread pour {url} : {e}")
        
        finally:
            # L'acquittement DOIT être renvoyé au thread principal de Pika
            # pour éviter les problèmes de concurrence.
            self.connection.add_callback_threadsafe(lambda: ch.basic_ack(delivery_tag=method.delivery_tag))
            print(f"   -> Message acquitté pour {url}")
            
    def _on_message_callback(self, ch, method, properties, body):
        """
        Ce callback est maintenant ultra-léger. Son seul rôle est de
        soumettre la tâche de traitement au pool de threads et de retourner
        immédiatement, pour pouvoir accepter le message suivant.
        """
        self.executor.submit(self._process_message_task, ch, method, properties, body)
            
    def start_consuming(self):
        """
        Démarre la boucle d'écoute des messages et gère la reconnexion.
        """
        while True:
            try:
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 template-llm-service: En attente de messages...")
                self.channel.start_consuming()
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                self._reconnect()
            except KeyboardInterrupt:
                print("Arrêt demandé.")
                self.executor.shutdown(wait=True)
                break
