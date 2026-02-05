import logging
import asyncio
import json
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from app.config import settings
from app.core.processor import CategorieProcessor


class RabbitMQConsumer:
    """Async Consumer with Semaphore-based concurrency for categorie processing."""

    def __init__(self):
        self.processor = CategorieProcessor()
        self.connection = None
        self.channel = None
        self.queue = None

        # Concurrency control
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)

    async def process_message(self, message: AbstractIncomingMessage):
        """Process a single message with semaphore control."""
        async with message.process(ignore_processed=True):
            try:
                data = json.loads(message.body.decode())
                await self.processor.process_message(data)
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
        # Using type='topic' as it's likely a topic exchange
        exchange = await self.channel.declare_exchange(
            settings.INPUT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.queue = await self.channel.declare_queue(
            settings.INPUT_QUEUE, durable=True
        )
        await self.queue.bind(exchange, routing_key=settings.INPUT_ROUTING_KEY)

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
