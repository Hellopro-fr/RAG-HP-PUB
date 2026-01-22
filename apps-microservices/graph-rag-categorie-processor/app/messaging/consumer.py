import logging
import asyncio
import json
import aio_pika
from app.config import settings
from app.core.processor import CategorieProcessor


class RabbitMQConsumer:
    def __init__(self):
        self.processor = CategorieProcessor()

    async def start(self):
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        channel = await connection.channel()

        # Declare exchange (passive=False to ensure it exists or create)
        # Using type='topic' as it's likely a topic exchange
        exchange = await channel.declare_exchange(
            settings.INPUT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(settings.INPUT_QUEUE, durable=True)
        await queue.bind(exchange, routing_key=settings.INPUT_ROUTING_KEY)

        logging.info(f"Listening on {settings.INPUT_QUEUE}...")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode())
                        await self.processor.process_message(data)
                    except Exception as e:
                        logging.error(f"Error processing message: {e}")

    def close(self):
        self.processor.close()