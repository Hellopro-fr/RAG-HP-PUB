import pika
import json
import logging
import os
from app.messaging.publisher import Publisher
from app.core.downloader import Downloader

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_TTL_MS = 30000

class Consumer:
    def __init__(self, publisher: Publisher):
        self.publisher = publisher
        self.downloader = Downloader()
        
        # RabbitMQ components
        self.exchange_name = 'data_exchange_produits'
        self.routing_key = 'new_data.product'
        self.queue_name = 'image_download_tasks_queue'
        self.retry_exchange = 'retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        self.connection = None
        self.channel = None

    def connect(self):
        """Establish connection and declare all queues/exchanges."""
        rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")
        
        max_retries = 10
        retry_delay = 5
        
        import time
        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Attempt {attempt+1}/{max_retries} connecting to RabbitMQ...")
                self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                self.channel = self.connection.channel()
                logger.info("✅ Connected to RabbitMQ.")
                break
            except Exception as e:
                logger.warning(f"❌ Connection failed ({e}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        else:
            raise Exception(f"❌ Could not connect to RabbitMQ after {max_retries} attempts.")

        # --- Main Queue (Simple, no DLQ for now) ---
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        
        # --- DLQ Infrastructure ---
        self.channel.exchange_declare(exchange=self.dead_letter_exchange, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(exchange=self.dead_letter_exchange, queue=self.dead_letter_queue_name, routing_key=self.routing_key)

        # --- Retry Infrastructure ---
        self.channel.exchange_declare(exchange=self.retry_exchange, exchange_type='topic', durable=True)
        retry_queue_args = {
            'x-message-ttl': RETRY_TTL_MS,
            'x-dead-letter-exchange': self.exchange_name,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # --- Main Queue with DLQ ---
        main_queue_args = {
            'x-dead-letter-exchange': self.retry_exchange,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.queue_name, durable=True, arguments=main_queue_args)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        
        logger.info(f"✅ Queue '{self.queue_name}' declared and bound to '{self.exchange_name}'.")

    def start_consuming(self):
        """Start consuming messages."""
        self.connect()
        
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message)
        
        logger.info(f"[*] Waiting for messages in {self.queue_name}")
        self.channel.start_consuming()

    def _on_message(self, channel, method, properties, body):
        """Process incoming message."""
        try:
            data = json.loads(body.decode())
            product_data = data.get("data", data)
            
            logger.info(f"Received task for product {product_data.get('id_produit')}")
            
            # Synchronous wrapper for async download
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result_data = loop.run_until_complete(self.downloader.process_product(product_data))
            finally:
                loop.close()
            
            if result_data.get("local_image_paths"):
                self.publisher.publish_update(result_data)
            
            channel.basic_ack(delivery_tag=method.delivery_tag)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
