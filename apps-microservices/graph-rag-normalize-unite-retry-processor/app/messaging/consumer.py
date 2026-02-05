import json
import logging
import asyncio
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.core.processor import process_retry_normalization


class Consumer:
    """Async Consumer with Semaphore-based concurrency for normalization retry."""

    def __init__(self):
        self.connection = None
        self.channel = None
        self.queue = None

        # Concurrency control
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)

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

        # Set prefetch count to match concurrency limit
        await self.channel.set_qos(prefetch_count=settings.MAX_CONCURRENCY)

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

    async def process_message(self, message: AbstractIncomingMessage):
        """Process a single message with semaphore control."""
        async with message.process(ignore_processed=True):
            try:
                body = message.body.decode()
                payload = json.loads(body)

                # Check if this is a requeued message from Manual DLQ (wrapped)
                if "failed_node_entry" in payload:
                    failed_node_entry = payload["failed_node_entry"]
                else:
                    failed_node_entry = payload

                if not failed_node_entry.get("node"):
                    logging.warning("Empty node data, skipping")
                    await message.ack()
                    return

                # Process retry normalization
                result = process_retry_normalization(failed_node_entry)

                if result["success"]:
                    logging.info(
                        f"✅ Retry normalization success: {failed_node_entry.get('node', {}).get('id')}"
                    )
                else:
                    # Normalization still failed - send to manual DLQ
                    await self._publish_to_manual_dlq(
                        failed_node_entry, result.get("error", {})
                    )

                await message.ack()

            except Exception as e:
                logging.error(f"❌ Error processing message: {e}")
                # On exception, send to manual DLQ
                try:
                    await self._publish_to_manual_dlq(
                        failed_node_entry if "failed_node_entry" in locals() else {},
                        {"reason": "processing_exception", "message": str(e)},
                    )
                except Exception:
                    pass
                await message.ack()

    async def start_consuming(self):
        """Start the consumer loop with concurrency control."""
        await self.connect()
        logging.info(
            f"👂 Normalization Retry Consumer listening on: {self.queue_name} with concurrency {settings.MAX_CONCURRENCY}"
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
