import json
import logging
import asyncio
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import extract_entities_and_relationships


class Consumer:
    """Async Consumer for processing products for LLM extraction with Semaphore concurrency."""

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

    async def connect(self):
        """Establish connection and setup topology."""
        logging.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Set prefetch count to match concurrency limit + buffer
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)

        # Setup Publisher on the same channel/connection
        await self.publisher.setup(self.channel)

        await self._setup_infrastructure()
        logging.info("✅ LLM Extractor Consumer initialized")

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

    def _get_retry_count(self, message: AbstractIncomingMessage) -> int:
        headers = message.headers
        if headers and "x-death" in headers:
            for death in headers["x-death"]:
                if death.get("queue") == self.retry_queue_name:
                    return death.get("count", 0)
        return 0

    async def process_message(self, message: AbstractIncomingMessage):
        """
        Process a single message.
        This method is called inside a Task, guarded by the semaphore in start_consuming.
        """
        async with message.process(ignore_processed=True):
            try:
                body = message.body.decode()
                data_json = json.loads(body)

                data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")
                graph_id = data.get("graph_id", "unknown")

                logging.info(f"Processing LLM extraction for: {graph_id}")

                # The heavy lifting (LLM call) happens here
                output_message = await extract_entities_and_relationships(
                    data, database, origin
                )

                # Publish result if valid
                if output_message.get("data", {}).get("nodes") or output_message.get(
                    "data", {}
                ).get("relationships"):
                    await self.publisher.publish_message(output_message)
                    logging.info(f"📤 Published extraction result for {graph_id}")
                else:
                    logging.warning(f"Empty extraction result for {graph_id}")

                await message.ack()

            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"❌ Permanent error: {e}")
                # Create DLQ headers manually since we are using aio_pika
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-llm-extractor-processor", 0, message
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
                retry_count = self._get_retry_count(message)
                if retry_count < settings.MAX_RETRIES:
                    logging.warning(
                        f"⚠️ Error (attempt {retry_count + 1}), retrying: {e}"
                    )
                    await message.nack(
                        requeue=False
                    )  # Dead letter will route to retry queue
                else:
                    logging.error(f"❌ Failed after retries: {e}")
                    headers = DLQProperties.create_dlq_headers(
                        e,
                        "graph-rag-llm-extractor-processor",
                        settings.MAX_RETRIES,
                        message,
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

    async def start_consuming(self):
        """Start the consumer loop with concurrency control."""
        await self.connect()
        logging.info(
            f"👂 LLM Extractor listening on: {self.queue_name} with concurrency {settings.MAX_CONCURRENCY}"
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
