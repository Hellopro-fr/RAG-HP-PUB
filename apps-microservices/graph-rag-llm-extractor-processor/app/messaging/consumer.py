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
        self.retry_exchange = "graph-retry_exchange"
        self.retry_queue_name = f"{self.queue_name}_retry"
        self.dead_letter_exchange = "graph-dead_letter_exchange"
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

                # Check if this is a validation retry attempt
                headers = message.headers or {}
                validation_retry_count = headers.get("x-validation-retry", 0)

                # The heavy lifting (LLM call) happens here
                output_message = await extract_entities_and_relationships(
                    data, database, origin
                )

                # Check if validation failed (nodes missing id_source_caracteristique)
                validation_failed = output_message.get("validation_failed", False)
                missing_nodes = output_message.get("missing_nodes", [])

                if validation_failed:
                    if validation_retry_count < 1:
                        # First attempt failed validation - retry one more time
                        logging.warning(
                            f"⚠️ Validation retry for {graph_id}: {len(missing_nodes)} nodes missing id_source_caracteristique. Retrying..."
                        )

                        # Create new message with validation retry header
                        retry_headers = dict(headers)
                        retry_headers["x-validation-retry"] = 1

                        retry_exchange = await self.channel.get_exchange(
                            self.retry_exchange
                        )
                        await retry_exchange.publish(
                            aio_pika.Message(
                                body=message.body,
                                headers=retry_headers,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            ),
                            routing_key=self.routing_key,
                        )
                        await message.ack()
                        return
                    else:
                        # Already retried once, send to DLQ for manual retry
                        logging.error(
                            f"❌ Validation failed after retry for {graph_id}. Missing nodes: {missing_nodes}. Sending to DLQ for manual retry."
                        )

                        # Get all extracted nodes from the output message
                        extracted_nodes = output_message.get("data", {}).get(
                            "nodes", []
                        )

                        dlq_headers = DLQProperties.create_dlq_headers(
                            Exception(
                                f"Validation failed: nodes missing id_source_caracteristique: {missing_nodes}"
                            ),
                            "graph-rag-llm-extractor-processor",
                            1,
                            message,
                        )
                        dlq_headers["x-validation-failed"] = True
                        dlq_headers["x-missing-nodes"] = json.dumps(missing_nodes)
                        dlq_headers["x-extracted-nodes"] = extracted_nodes
                        dlq_headers["x-original-exchange"] = self.exchange_name
                        dlq_headers["x-original-routing-key"] = self.routing_key
                        dlq_headers["x-original-queue"] = self.queue_name

                        await self.channel.default_exchange.publish(
                            aio_pika.Message(
                                body=message.body,
                                headers=dlq_headers,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            ),
                            routing_key=self.dead_letter_queue_name,
                        )
                        await message.ack()
                        return

                # Validation passed - publish result to next service
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
