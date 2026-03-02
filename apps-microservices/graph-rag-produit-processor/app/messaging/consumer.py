import json
import logging
import asyncio
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import prepare_product_cypher, create_output_message

# Import centralized client for Neo4j operations
from common_utils.grpc_clients import graph_database_client


class Consumer:
    """Async Consumer with Semaphore-based concurrency for product processing."""

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

        # Set prefetch count to match concurrency limit
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)

        # Setup Publisher
        await self.publisher.setup(self.channel)

        await self._setup_infrastructure()
        logging.info("✅ Product Consumer initialized")

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

    async def process_message(self, message: AbstractIncomingMessage):
        """Process a single product message with semaphore control."""
        async with message.process(ignore_processed=True):
            try:
                body = message.body.decode()
                data_json = json.loads(body)
                product_data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")

                if not product_data:
                    logging.warning("Empty product data, skipping")
                    await message.ack()
                    return

                # Prepare Cypher statement
                cypher, params, graph_id = prepare_product_cypher(product_data)

                # Execute against Neo4j (single statement)
                success, results, records_affected = (
                    await graph_database_client.execute_cypher(
                        query=cypher, parameters=params
                    )
                )

                if success:
                    logging.debug(f"✅ Product {graph_id} written to Neo4j")

                    # Prepare and publish output message
                    out_msg = create_output_message(
                        product_data, graph_id, True, database, origin
                    )
                    if out_msg["data"].get("text_for_extraction"):
                        await self.publisher.publish_message(out_msg)

                    await message.ack()
                else:
                    logging.error(f"❌ Neo4j write failed for {graph_id}")
                    await message.nack(requeue=False)

            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"❌ Permanent error: {e}")
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-produit-processor", 0, message
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
                logging.error(f"❌ Error processing message: {e}")
                await message.nack(requeue=False)

    async def start_consuming(self):
        """Start the consumer loop with concurrency control."""
        await self.connect()
        logging.info(
            f"👂 Product Consumer listening on: {self.queue_name} with concurrency {settings.MAX_CONCURRENCY}"
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
