import json
import logging
import asyncio
import time
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.core.processor import process_retry_normalization


class Consumer:
    """Async Consumer with Batch Processing for normalization retry."""

    def __init__(self):
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

        # Manual DLQ for permanently failed normalizations
        self.manual_dlq_exchange_name = settings.MANUAL_DLQ_EXCHANGE
        self.manual_dlq_routing_key = settings.MANUAL_DLQ_ROUTING_KEY
        self.manual_dlq_queue_name = settings.MANUAL_DLQ_QUEUE
        self.manual_dlq_exchange = None

    async def connect(self):
        """Establish connection and setup topology."""
        logging.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
        self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Prefetch slightly more than batch size to keep buffer full
        await self.channel.set_qos(prefetch_count=settings.BATCH_SIZE * 2)

        await self._setup_infrastructure()
        logging.info("✅ Normalization Retry Consumer initialized")

    async def _setup_infrastructure(self):
        """Setup exchanges, queues, and bindings."""
        # Main input exchange (retry DLQ)
        main_exchange = await self.channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True)
        await self.queue.bind(main_exchange, routing_key=self.routing_key)

        # Manual DLQ for permanently failed normalizations
        self.manual_dlq_exchange = await self.channel.declare_exchange(
            self.manual_dlq_exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        manual_dlq_queue = await self.channel.declare_queue(
            self.manual_dlq_queue_name, durable=True
        )
        await manual_dlq_queue.bind(
            self.manual_dlq_exchange,
            routing_key=self.manual_dlq_routing_key,
        )
        logging.info(f"✅ Manual DLQ configured: {self.manual_dlq_queue_name}")

    async def _publish_to_manual_dlq(self, failed_node_entry: dict, error: dict):
        """Publish a permanently failed node to the manual DLQ."""
        try:
            message_data = {
                "failed_node_entry": failed_node_entry,
                "error": error,
                "processor": "graph-rag-normalize-unite-retry-processor",
            }
            message_body = json.dumps(message_data).encode("utf-8")
            message = aio_pika.Message(
                body=message_body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self.manual_dlq_exchange.publish(
                message, routing_key=self.manual_dlq_routing_key
            )
            logging.info(
                f"📤 Published to manual DLQ: {failed_node_entry.get('node', {}).get('id')}"
            )
        except Exception as e:
            logging.error(f"Failed to publish to manual DLQ: {e}")

    async def _process_batch(self, batch: list):
        """
        Execute a batch of messages:
        1. Process each failed node through retry normalization.
        2. If successful: node is written to Neo4j.
        3. If failed: publish to manual DLQ.
        4. Ack RabbitMQ messages.
        """
        if not batch:
            return

        valid_items = []  # (message, failed_node_entry)

        # 1. Parse and validate messages
        for msg in batch:
            try:
                body = msg.body.decode()
                payload = json.loads(body)

                # Check if this is a requeued message from Manual DLQ (wrapped)
                if "failed_node_entry" in payload:
                    failed_node_entry = payload["failed_node_entry"]
                else:
                    failed_node_entry = payload

                if not failed_node_entry.get("node"):
                    logging.warning("Empty node data, skipping")
                    asyncio.create_task(msg.ack())
                    continue

                valid_items.append((msg, failed_node_entry))

            except Exception as e:
                logging.error(f"Error parsing message: {e}")
                asyncio.create_task(msg.ack())

        if not valid_items:
            return

        # 2. Process batch
        success_count = 0
        failure_count = 0

        for msg, failed_node_entry in valid_items:
            try:
                # Process retry normalization
                result = process_retry_normalization(failed_node_entry)

                if result["success"]:
                    success_count += 1
                else:
                    # Normalization still failed - send to manual DLQ
                    await self._publish_to_manual_dlq(
                        failed_node_entry, result.get("error", {})
                    )
                    failure_count += 1

                await msg.ack()

            except Exception as e:
                logging.error(f"Error processing message: {e}")
                # On exception, send to manual DLQ
                await self._publish_to_manual_dlq(
                    failed_node_entry,
                    {"reason": "processing_exception", "message": str(e)},
                )
                await msg.ack()
                failure_count += 1

        logging.info(
            f"✅ Batch processed: {success_count} success, {failure_count} to manual DLQ"
        )

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

        logging.info(f"👂 Normalization Retry Consumer listening on: {self.queue_name}")

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
