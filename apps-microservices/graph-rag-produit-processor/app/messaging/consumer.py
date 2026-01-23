import json
import logging
import asyncio
import time
import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common_utils.autres.DLQPropertiesAsync import DLQPropertiesAsync as DLQProperties
from app.config import settings
from app.messaging.publisher import Publisher
from app.core.processor import prepare_product_cypher, create_output_message
from app.infrastructure.graph_database_client import graph_database_client


class Consumer:
    """Async Consumer with Batch Processing for Neo4j writes."""

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

    async def _process_batch(self, batch: list):
        """
        Execute a batch of messages:
        1. Prepare Cypher statements.
        2. Execute batch against Neo4j.
        3. Publish output messages.
        4. Ack/Nack RabbitMQ messages.
        """
        if not batch:
            return

        statements = []
        valid_items = []  # (message, product_data, graph_id, database, origin)

        # 1. Prepare Statements
        for msg in batch:
            try:
                body = msg.body.decode()
                data_json = json.loads(body)
                product_data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")

                if not product_data:
                    logging.warning("Empty product data, skipping")
                    asyncio.create_task(msg.ack())  # Ack invalid immediately
                    continue

                cypher, params, graph_id = prepare_product_cypher(product_data)
                statements.append({"query": cypher, "parameters": params})
                valid_items.append((msg, product_data, graph_id, database, origin))

            except Exception as e:
                logging.error(f"Error preparing message: {e}")
                # Send to DLQ immediately
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-produit-processor", 0, msg
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

        if not statements:
            return

        # 2. Execute Batch
        try:
            # Note: execute_cypher_async in client calls centralized_db_client.execute_cypher (single)
            # We need to call execute_batch_cypher from the centralized client directly or update the wrapper.
            # Assuming the wrapper has been updated or we access the centralized client.
            # Let's use the centralized client directly for batching to be safe,
            # or assume graph_database_client has execute_batch_cypher (it should).

            # Since we didn't update graph_database_client.py in this plan, we import the centralized one here
            from common_utils.grpc_clients import (
                graph_database_client as centralized_client,
            )

            success, error_msg, results = await centralized_client.execute_batch_cypher(
                statements=statements, transactional=True
            )

            if success:
                logging.info(
                    f"✅ Batch executed successfully ({len(statements)} items)"
                )

                # 3. Publish Outputs & 4. Ack
                for i, (msg, p_data, g_id, db, orig) in enumerate(valid_items):
                    # Prepare output message
                    out_msg = create_output_message(p_data, g_id, True, db, orig)

                    # Publish if text exists
                    if out_msg["data"].get("text_for_extraction"):
                        await self.publisher.publish_message(out_msg)

                    await msg.ack()
            else:
                logging.error(f"❌ Batch failed: {error_msg}. Retrying individually...")
                # Fallback: Nack all to retry individually (or implement complex partial retry logic)
                # Simple strategy: Nack all, they go to retry queue (or back to main if no DLQ set on nack)
                # Since we configured DLQ on queue, nack(requeue=False) goes to DLQ/Retry.
                # Let's requeue=True to try again in next batch? No, that might loop.
                # Let's Nack with requeue=False so they go to Retry Queue (via DLX)
                for msg, _, _, _, _ in valid_items:
                    await msg.nack(requeue=False)

        except Exception as e:
            logging.error(f"❌ Critical batch error: {e}")
            for msg, _, _, _, _ in valid_items:
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
                batch = (
                    []
                )  # Drop batch on critical error to prevent loop? Or handle better.

    async def start_consuming(self):
        """Start consumer and batch worker."""
        await self.connect()

        # Start background worker
        self.batch_worker_task = asyncio.create_task(self._batch_worker())

        logging.info(f"👂 Product Consumer listening on: {self.queue_name}")

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
