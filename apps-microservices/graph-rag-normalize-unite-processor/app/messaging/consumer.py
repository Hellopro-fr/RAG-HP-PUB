import json
import logging
import asyncio
import time
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import process_normalization


class Consumer:
    """Async Consumer with Batch Processing for normalization."""

    def __init__(self, publisher: Publisher):
        self.publisher = publisher
        self.connection = None
        self.channel = None
        self.queue = None

        # Batching state
        self.batch_queue = asyncio.Queue()
        self.batch_worker_task = None

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

        # Prefetch slightly more than batch size to keep buffer full
        await self.channel.set_qos(prefetch_count=settings.BATCH_SIZE * 2)

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

    async def _process_batch(self, batch: list):
        """
        Execute a batch of messages:
        1. Process each message through normalization.
        2. Publish successful nodes to semantic check queue.
        3. Publish failed nodes to retry DLQ.
        4. Ack/Nack RabbitMQ messages.
        """
        if not batch:
            return

        valid_items = []  # (message, data, database, origin)

        # 1. Parse and validate messages
        for msg in batch:
            try:
                body = msg.body.decode()
                data_json = json.loads(body)
                data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")

                if not data:
                    logging.warning("Empty data, skipping")
                    asyncio.create_task(msg.ack())
                    continue

                valid_items.append((msg, data, database, origin))

            except Exception as e:
                logging.error(f"Error preparing message: {e}")
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-normalize-unite-processor", 0, msg
                )
                await self.channel.default_exchange.publish(
                    aio_pika.Message(
                        body=msg.body,
                        headers=headers,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=self.dead_letter_queue_name,
                )
                asyncio.create_task(msg.ack())

        if not valid_items:
            return

        # 2. Process batch
        try:
            for msg, data, database, origin in valid_items:
                try:
                    # Process normalization for each item
                    result = process_normalization(data, database, origin)

                    # Publish successful nodes to next stage
                    output_message = result["output_message"]
                    if output_message["data"].get("nodes"):
                        await self.publisher.publish_message(output_message)

                    # Publish failed nodes to retry DLQ
                    for failed_node_entry in result.get("failed_nodes", []):
                        await self._publish_to_retry_dlq(failed_node_entry)

                    await msg.ack()

                except Exception as e:
                    logging.error(f"Error processing message: {e}")
                    await msg.nack(requeue=False)

            logging.info(f"✅ Batch processed successfully ({len(valid_items)} items)")

        except Exception as e:
            logging.error(f"❌ Critical batch error: {e}")
            for msg, _, _, _ in valid_items:
                await msg.nack(requeue=False)

    async def _batch_worker(self):
        """Background task to flush batches."""
        batch = []
        while True:
            try:
                # Wait for first item
                item = await self.batch_queue.get()
                batch.append(item)

                # Collect more items up to batch size or timeout
                start_time = time.time()
                while len(batch) < settings.BATCH_SIZE:
                    timeout = settings.BATCH_TIMEOUT_SECONDS - (
                        time.time() - start_time
                    )
                    if timeout <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(
                            self.batch_queue.get(), timeout=timeout
                        )
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break

                # Process the collected batch
                await self._process_batch(batch)

                # Mark tasks as done
                for _ in batch:
                    self.batch_queue.task_done()
                batch = []

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Batch worker error: {e}")
                batch = []

    async def start_consuming(self):
        """Start consumer and batch worker."""
        await self.connect()

        # Start background worker
        self.batch_worker_task = asyncio.create_task(self._batch_worker())

        logging.info(f"👂 Normalization Consumer listening on: {self.queue_name}")

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                # Put message in queue. The iterator handles flow control via prefetch.
                await self.batch_queue.put(message)

    async def close(self):
        if self.batch_worker_task:
            self.batch_worker_task.cancel()
            try:
                await self.batch_worker_task
            except asyncio.CancelledError:
                pass
        if self.connection:
            await self.connection.close()
