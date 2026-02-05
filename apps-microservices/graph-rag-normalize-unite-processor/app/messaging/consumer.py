import json
import logging
import asyncio
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import process_normalization


class Consumer:
    """Async Consumer with Semaphore-based concurrency for normalization."""

    def __init__(self, publisher: Publisher):
        self.publisher = publisher
        self.connection = None
        self.channel = None
        self.queue = None

        # Concurrency control
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)

        # Queue configuration
        self.exchange_name = settings.INPUT_EXCHANGE
        self.routing_key = settings.INPUT_ROUTING_KEY
        self.queue_name = settings.INPUT_QUEUE
        self.retry_exchange = "retry_exchange"
        self.retry_queue_name = f"{self.queue_name}_retry"
        self.dead_letter_exchange = "dead_letter_exchange"
        self.dead_letter_queue_name = f"{self.queue_name}_dlq"

        # Retry DLQ for failed normalizations (goes to retry processor)
        self.normalization_retry_exchange_name = settings.RETRY_DLQ_EXCHANGE
        self.normalization_retry_routing_key = settings.RETRY_DLQ_ROUTING_KEY
        self.normalization_retry_queue_name = settings.RETRY_DLQ_QUEUE
        self.normalization_retry_exchange = None

    async def connect(self):
        """Establish connection and setup topology."""
        logging.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Set prefetch count to match concurrency limit
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)

        # Setup Publisher
        await self.publisher.setup(self.channel)

        await self._setup_infrastructure()
        logging.info("✅ Normalization Consumer initialized")

    async def _setup_infrastructure(self):
        """Setup exchanges, queues, and bindings."""
        # DLQ
        dlq_exchange = await self.channel.declare_exchange(
            self.dead_letter_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        dlq_queue = await self.channel.declare_queue(
            self.dead_letter_queue_name, durable=True
        )
        await dlq_queue.bind(dlq_exchange, routing_key=self.routing_key)

        # Retry
        retry_exchange = await self.channel.declare_exchange(
            self.retry_exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        retry_queue = await self.channel.declare_queue(
            self.retry_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": settings.RETRY_TTL_MS,
                "x-dead-letter-exchange": self.exchange_name,
                "x-dead-letter-routing-key": self.routing_key,
            },
        )
        await retry_queue.bind(retry_exchange, routing_key=self.routing_key)

        # Main
        main_exchange = await self.channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.queue = await self.channel.declare_queue(
            self.queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": self.retry_exchange,
                "x-dead-letter-routing-key": self.routing_key,
            },
        )
        await self.queue.bind(main_exchange, routing_key=self.routing_key)

        # Normalization Retry DLQ (for failed normalizations -> retry processor)
        self.normalization_retry_exchange = await self.channel.declare_exchange(
            self.normalization_retry_exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        normalization_retry_queue = await self.channel.declare_queue(
            self.normalization_retry_queue_name, durable=True
        )
        await normalization_retry_queue.bind(
            self.normalization_retry_exchange,
            routing_key=self.normalization_retry_routing_key,
        )
        logging.info(
            f"✅ Normalization Retry DLQ configured: {self.normalization_retry_queue_name}"
        )

    async def _publish_to_retry_dlq(self, failed_node_entry: dict):
        """Publish a failed node to the normalization retry queue."""
        try:
            message_body = json.dumps(failed_node_entry).encode("utf-8")
            message = aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self.normalization_retry_exchange.publish(
                message, routing_key=self.normalization_retry_routing_key
            )
            logging.info(
                f"📤 Published failed node to retry DLQ: {failed_node_entry.get('node', {}).get('id')}"
            )
        except Exception as e:
            logging.error(f"Failed to publish to retry DLQ: {e}")

    async def process_message(self, message: AbstractIncomingMessage):
        """Process a single message with semaphore control."""
        async with message.process(ignore_processed=True):
            try:
                body = message.body.decode()
                data_json = json.loads(body)
                data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")

                if not data:
                    logging.warning("Empty data, skipping")
                    await message.ack()
                    return

                # Process normalization
                result = process_normalization(data, database, origin)

                # Publish successful nodes to next stage
                output_message = result["output_message"]
                if output_message["data"].get("nodes"):
                    await self.publisher.publish_message(output_message)

                # Publish failed nodes to retry DLQ
                for failed_node_entry in result.get("failed_nodes", []):
                    await self._publish_to_retry_dlq(failed_node_entry)

                await message.ack()

            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"❌ Permanent error: {e}")
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-normalize-unite-processor", 0, message
                )
                await self.channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        headers=headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=self.dead_letter_queue_name,
                )
                await message.ack()

            except Exception as e:
                logging.error(f"❌ Error processing message: {e}")
                await message.nack(requeue=False)

    async def start_consuming(self):
        """Start the consumer loop with concurrency control."""
        await self.connect()
        logging.info(
            f"👂 Normalization Consumer listening on: {self.queue_name} with concurrency {settings.MAX_CONCURRENCY}"
        )

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                # Acquire semaphore before spawning task
                await self.semaphore.acquire()

                # Create background task
                task = asyncio.create_task(self.process_message(message))

                # Release semaphore when task is done
                task.add_done_callback(lambda t: self.semaphore.release())

    async def close(self):
        if self.connection:
            await self.connection.close()
