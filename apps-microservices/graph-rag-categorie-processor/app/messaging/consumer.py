import logging
import asyncio
import json
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from app.config import settings
from app.core.processor import CategorieProcessor

# Use the Async version of DLQProperties if available
try:
    from common_utils.autres.DLQPropertiesAsync import (
        DLQPropertiesAsync as DLQProperties,
    )
except ImportError:
    from common_utils.autres.DLQProperties import DLQProperties


class RabbitMQConsumer:
    """Async Consumer with Semaphore-based concurrency for categorie processing."""

    def __init__(self):
        self.processor = CategorieProcessor()
        self.connection = None
        self.channel = None
        self.queue = None

        # Concurrency control
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)

        # Queue configuration
        self.exchange_name = settings.INPUT_EXCHANGE
        self.routing_key = settings.INPUT_ROUTING_KEY
        self.queue_name = settings.INPUT_QUEUE
        self.retry_exchange = "graph-retry_exchange"
        self.retry_queue_name = f"{self.queue_name}_retry"
        self.dead_letter_exchange = "graph-dead_letter_exchange"
        self.dead_letter_queue_name = f"{self.queue_name}_dlq"

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
                "x-message-ttl": 30000,
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

    async def process_message(self, message: AbstractIncomingMessage):
        """Process a single message with semaphore control."""
        async with message.process(ignore_processed=True):
            try:
                data = json.loads(message.body.decode())
                await self.processor.process_message(data)
                await message.ack()
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"❌ Permanent error processing categorie message: {e}")
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-categorie-processor", 0, message
                )
                headers["x-original-exchange"] = self.exchange_name
                headers["x-original-routing-key"] = self.routing_key
                headers["x-original-queue"] = self.queue_name
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
                logging.error(f"Error processing message: {e}")
                await message.nack(requeue=False)

    async def start(self):
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Set prefetch count to match concurrency limit
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)

        # Declare exchange (passive=False to ensure it exists or create)
        # Setup full DLQ/retry infrastructure
        await self._setup_infrastructure()

        logging.info(
            f"👂 Listening on {settings.INPUT_QUEUE} with concurrency {settings.MAX_CONCURRENCY}..."
        )

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                # Acquire semaphore before spawning task
                await self.semaphore.acquire()

                # Create background task
                task = asyncio.create_task(self.process_message(message))

                # Release semaphore when task is done
                task.add_done_callback(lambda t: self.semaphore.release())

    def close(self):
        self.processor.close()
