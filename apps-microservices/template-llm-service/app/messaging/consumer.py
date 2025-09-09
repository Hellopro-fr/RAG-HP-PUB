import pika
import json
import time
import threading
from vllm import LLM, SamplingParams
from template_llm_service.messaging.publisher import Publisher
from template_llm_service.core.processor import classify_page_template
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher, llm: LLM, tokenizer, llm_config: dict):
        self.publisher = publisher
        self.llm = llm
        self.tokenizer = tokenizer
        self.llm_config = llm_config
        self.rabbitmq_connection = RabbitMQConnection()

        # RabbitMQ
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_templating'
        self.queue_name = 'llm_templating_queue'
        self.connection = connection
        self.channel = connection.channel()
        self.connect()

        # Buffer batch
        self.batch_buffer = []
        self.batch_lock = threading.Lock()
        self.BATCH_SIZE = 8           # nombre max de messages par batch
        self.BATCH_TIMEOUT = 2.0      # secondes max d’attente

        print("✅ Consumer initialisé en mode batch.")

        # Thread flush périodique
        threading.Thread(target=self._batch_flusher, daemon=True).start()

    def connect(self):
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)

    def _on_message_callback(self, ch, method, properties, body):
        message = json.loads(body)
        print(f"📥 Message reçu (buffer size={len(self.batch_buffer)+1}).")

        with self.batch_lock:
            self.batch_buffer.append((ch, method, message))

        # pas de ack ici, on attend le traitement batch

    def _batch_flusher(self):
        """
        Thread qui envoie périodiquement les batchs
        """
        while True:
            time.sleep(self.BATCH_TIMEOUT)
            with self.batch_lock:
                if len(self.batch_buffer) == 0:
                    continue

                if len(self.batch_buffer) >= self.BATCH_SIZE or True:
                    # On flush le batch
                    batch = self.batch_buffer
                    self.batch_buffer = []

            if batch:
                self._process_batch(batch)

    def _process_batch(self, batch):
        try:
            print(f"⚡ Traitement d’un batch de {len(batch)} messages.")
            prompts = [msg for (_, _, msg) in batch]

            # Exemple : adapter classify_page_template pour batch
            outputs = [classify_page_template(self.llm, self.tokenizer, self.llm_config, p) for p in prompts]

            # Publier chaque output
            for output in outputs:
                self.publisher.publish_message(output)

            # Ack de tous les messages
            for ch, method, _ in batch:
                ch.basic_ack(delivery_tag=method.delivery_tag)

            print(f"✅ Batch traité et {len(batch)} messages acquittés.")

        except Exception as e:
            print(f"❌ Erreur batch: {e}")
            # On peut nack pour réessayer
            for ch, method, _ in batch:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start_consuming(self):
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback, auto_ack=False)
        print("👂 En attente de messages (mode batch)...")
        self.channel.start_consuming()
