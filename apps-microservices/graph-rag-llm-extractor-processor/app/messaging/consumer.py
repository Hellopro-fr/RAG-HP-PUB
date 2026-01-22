import pika
import json
import logging
import asyncio

from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.autres.DLQProperties import DLQProperties
from common_utils.metrics.prometheus import measure_processing_time

from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import extract_entities_and_relationships


class Consumer:
    """Consumer for processing products for LLM extraction."""

    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        self.channel = connection.channel()
        self.publisher = publisher

        self.exchange_name = settings.INPUT_EXCHANGE
        self.routing_key = settings.INPUT_ROUTING_KEY
        self.queue_name = settings.INPUT_QUEUE
        self.retry_exchange = "retry_exchange"
        self.retry_queue_name = f"{self.queue_name}_retry"
        self.dead_letter_exchange = "dead_letter_exchange"
        self.dead_letter_queue_name = f"{self.queue_name}_dlq"

        self.rabbitmq_connection = RabbitMQConnection()
        self._setup_infrastructure()
        logging.info("✅ LLM Extractor Consumer initialized")

    def _setup_infrastructure(self):
        """Setup exchanges, queues, and bindings."""
        self.channel.exchange_declare(
            exchange=self.dead_letter_exchange, exchange_type="topic", durable=True
        )
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(
            exchange=self.dead_letter_exchange,
            queue=self.dead_letter_queue_name,
            routing_key=self.routing_key,
        )

        self.channel.exchange_declare(
            exchange=self.retry_exchange, exchange_type="topic", durable=True
        )
        retry_queue_args = {
            "x-message-ttl": settings.RETRY_TTL_MS,
            "x-dead-letter-exchange": self.exchange_name,
            "x-dead-letter-routing-key": self.routing_key,
        }
        self.channel.queue_declare(
            queue=self.retry_queue_name, durable=True, arguments=retry_queue_args
        )
        self.channel.queue_bind(
            exchange=self.retry_exchange,
            queue=self.retry_queue_name,
            routing_key=self.routing_key,
        )

        self.channel.exchange_declare(
            exchange=self.exchange_name, exchange_type="topic", durable=True
        )
        main_queue_args = {
            "x-dead-letter-exchange": self.retry_exchange,
            "x-dead-letter-routing-key": self.routing_key,
        }
        self.channel.queue_declare(
            queue=self.queue_name, durable=True, arguments=main_queue_args
        )
        self.channel.queue_bind(
            exchange=self.exchange_name,
            queue=self.queue_name,
            routing_key=self.routing_key,
        )

    def _get_retry_count(self, properties: pika.BasicProperties) -> int:
        if properties.headers and "x-death" in properties.headers:
            for death in properties.headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    def connect(self):
        self.connection = self.rabbitmq_connection.create_connection(
            max_retries=10, retry_delay=5
        )
        self.channel = self.connection.channel()
        self._setup_infrastructure()

    # @measure_processing_time(service_name="graph-rag-llm-extractor-processor")
    def _on_message_callback(self, ch, method, properties, body):
        try:
            logging.info("📥 LLM Extractor: Message received")
            message = json.loads(body)
            data = message.get("data", {})
            database = message.get("database", "neo4j")
            origin = message.get("origin", "bo")

            graph_id = data.get("graph_id", "unknown")
            logging.info(f"Processing LLM extraction for: {graph_id}")

            # Run async extraction
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                output_message = loop.run_until_complete(
                    extract_entities_and_relationships(data, database, origin)
                )
            finally:
                loop.close()

            logging.info(f"Message published : {output_message}")
            logging.info(f"📤 LLM Extractor: Message published")

            if output_message.get('data').get('nodes') != [] and output_message.get('data').get('relationships') != []:
                self.publisher.publish_message(output_message)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"❌ Permanent error: {e}")
            dlq_props = DLQProperties.create_dlq_properties(
                e, "graph-rag-llm-extractor-processor", 0, method
            )
            ch.basic_publish(
                exchange=self.dead_letter_exchange,
                routing_key=self.routing_key,
                body=body,
                properties=dlq_props,
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            retry_count = self._get_retry_count(properties)
            if retry_count < settings.MAX_RETRIES:
                logging.warning(f"⚠️ Error (attempt {retry_count + 1}), retrying: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            else:
                logging.error(f"❌ Failed after retries: {e}")
                dlq_props = DLQProperties.create_dlq_properties(
                    e, "graph-rag-llm-extractor-processor", settings.MAX_RETRIES, method
                )
                ch.basic_publish(
                    exchange=self.dead_letter_exchange,
                    routing_key=self.routing_key,
                    body=body,
                    properties=dlq_props,
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        for i in range(3):
            try:
                self.channel.basic_consume(
                    queue=self.queue_name, on_message_callback=self._on_message_callback
                )
                logging.info(f"👂 LLM Extractor listening on: {self.queue_name}")
                self.channel.start_consuming()
                break
            except (
                pika.exceptions.AMQPConnectionError,
                pika.exceptions.ChannelClosedByBroker,
            ) as e:
                logging.warning(f"⚠️ Connection lost: {e}, reconnecting...")
                self.connect()