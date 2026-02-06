import json
import logging
import asyncio
import time
import random
import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from collections import defaultdict

# Use the Async version of DLQProperties if available
try:
    from common_utils.autres.DLQPropertiesAsync import (
        DLQPropertiesAsync as DLQProperties,
    )
except ImportError:
    from common_utils.autres.DLQProperties import DLQProperties

from app.config import settings
from app.core.processor import prepare_etl_statements

# Import centralized client for batch execution
from common_utils.grpc_clients import graph_database_client as centralized_client
from datetime import datetime


class Consumer:
    """Async Consumer for Final ETL with Parallel Batch Workers and Deadlock Prevention."""

    def __init__(self, connection: aio_pika.RobustConnection):
        self.connection = connection
        self.channel = None
        self.queue = None

        # Batching state - shared queue for all workers
        self.batch_queue = asyncio.Queue()
        self.batch_worker_tasks = []

        # Queue configuration
        self.exchange_name = settings.INPUT_EXCHANGE
        self.routing_key = settings.INPUT_ROUTING_KEY
        self.queue_name = settings.INPUT_QUEUE
        self.retry_exchange = "retry_exchange"
        self.retry_queue_name = f"{self.queue_name}_retry"
        self.dead_letter_exchange = "dead_letter_exchange"
        self.dead_letter_queue_name = f"{self.queue_name}_dlq"

    async def setup(self):
        """Setup channel and topology."""
        self.channel = await self.connection.channel()

        # Prefetch enough for all workers
        await self.channel.set_qos(
            prefetch_count=settings.BATCH_SIZE * settings.MAX_CONCURRENCY * 2
        )

        await self._setup_infrastructure()
        logging.info("✅ ETL Consumer initialized")

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

    def _detect_deadlock_candidates(self, valid_items: list) -> tuple:
        """
        Analyze items and separate into:
        - no_deadlock_items: Items with unique graph_id (safe for batch)
        - deadlock_items: Items with duplicate graph_id (process sequentially)

        Returns: (no_deadlock_items, deadlock_items)
        """
        # Group items by graph_id
        graph_id_groups = defaultdict(list)
        for item in valid_items:
            msg, stmts, graph_id = item
            graph_id_groups[graph_id].append(item)

        no_deadlock_items = []
        deadlock_items = []

        for graph_id, items in graph_id_groups.items():
            if len(items) == 1:
                # Unique graph_id - safe for batch
                no_deadlock_items.append(items[0])
            else:
                # Multiple items with same graph_id - potential deadlock
                # Keep first one in no_deadlock, rest go to deadlock queue
                no_deadlock_items.append(items[0])
                deadlock_items.extend(items[1:])
                logging.debug(
                    f"⚠️ Detected {len(items)} items with same graph_id '{graph_id}' - {len(items)-1} will be processed sequentially"
                )

        if deadlock_items:
            logging.info(
                f"🔒 Deadlock prevention: {len(no_deadlock_items)} items for batch, {len(deadlock_items)} items for sequential"
            )

        return no_deadlock_items, deadlock_items

    async def _execute_batch_with_retry(
        self, statements: list, max_retries: int = 3
    ) -> bool:
        """Execute batch with deadlock retry logic. Returns True on success."""
        for attempt in range(max_retries):
            try:
                success, error_msg, results = (
                    await centralized_client.execute_batch_cypher(
                        statements=statements, transactional=True
                    )
                )

                if success:
                    return True

                # Check for Deadlock or Transient errors
                if (
                    "Deadlock" in error_msg
                    or "Transient" in error_msg
                    or "Lock" in error_msg
                ):
                    sleep_time = random.uniform(0.5, 2.0)
                    logging.warning(
                        f"⚠️ Deadlock detected (attempt {attempt+1}/{max_retries}). Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    continue
                else:
                    logging.error(f"❌ Non-transient batch error: {error_msg}")
                    return False

            except Exception as e:
                logging.error(f"❌ Critical batch exception: {e}")
                return False

        return False

    async def _process_items_sequentially(self, items: list):
        """Process items one by one (for potential deadlock candidates)."""
        for msg, stmts, g_id in items:
            try:
                success, err, _ = await centralized_client.execute_batch_cypher(
                    statements=stmts, transactional=True
                )

                if success:
                    await msg.ack()
                    logging.debug(f"✅ Sequential item {g_id} processed successfully")
                else:
                    logging.error(
                        f"❌ Sequential item failed for {g_id}: {err}. Requeueing."
                    )
                    await msg.nack(requeue=True)
                    await asyncio.sleep(0.2)

            except Exception as e:
                logging.error(f"❌ Error processing sequential item {g_id}: {e}")
                await msg.nack(requeue=True)

    async def _process_batch(self, batch: list, worker_id: int):
        """
        Execute a batch of ETL messages with Deadlock Prevention.

        Strategy:
        1. Parse and prepare all items
        2. Detect potential deadlock candidates (items with same graph_id)
        3. Batch process items with unique graph_ids
        4. Sequentially process potential deadlock items
        """
        if not batch:
            return

        all_statements = []
        valid_items = []  # (message, statements_for_this_msg, graph_id)

        # 1. Prepare Statements
        logging.info(f"Worker {worker_id}: Start processing batch")
        for msg in batch:
            try:
                body = msg.body.decode()
                data_json = json.loads(body)
                data = data_json.get("data", {})
                database = data_json.get("database", "neo4j")
                origin = data_json.get("origin", "bo")
                graph_id = data.get("graph_id", "")

                if not data:
                    logging.warning("Empty data in ETL message, skipping")
                    asyncio.create_task(msg.ack())
                    continue

                # Generate list of statements for this single message
                msg_statements = prepare_etl_statements(data, database, origin)

                if not msg_statements:
                    asyncio.create_task(msg.ack())
                    continue

                # Add to valid items
                valid_items.append((msg, msg_statements, graph_id or "unknown"))

            except Exception as e:
                logging.error(f"Error preparing ETL message: {e}")
                headers = DLQProperties.create_dlq_headers(
                    e, "graph-rag-etl-processor", 0, msg
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

        # 2. Detect and separate deadlock candidates
        no_deadlock_items, deadlock_items = self._detect_deadlock_candidates(
            valid_items
        )

        # 3. Batch process items with no deadlock risk
        if no_deadlock_items:
            # Sort by graph_id to minimize deadlock chance
            no_deadlock_items.sort(key=lambda x: x[2])

            # Build statements list for batch
            batch_statements = []
            for _, stmts, _ in no_deadlock_items:
                batch_statements.extend(stmts)

            # Execute batch
            batch_success = await self._execute_batch_with_retry(
                batch_statements, max_retries=3
            )

            if batch_success:
                logging.info(
                    f"✅ Worker {worker_id}: ETL Batch executed successfully ({len(batch_statements)} statements, {len(no_deadlock_items)} items)"
                )
                logging.info(
                    "🕒 Write time : " + datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                )
                # Ack all batch messages
                for msg, _, _ in no_deadlock_items:
                    await msg.ack()
            else:
                # Batch failed - fall back to sequential for all batch items
                logging.warning(
                    f"⚠️ Worker {worker_id}: Batch failed. Switching to sequential processing for batch items."
                )
                await self._process_items_sequentially(no_deadlock_items)

        # 4. Process potential deadlock items sequentially
        if deadlock_items:
            logging.info(
                f"🔄 Worker {worker_id}: Processing {len(deadlock_items)} potential deadlock items sequentially..."
            )
            await self._process_items_sequentially(deadlock_items)

    async def _batch_worker(self, worker_id: int):
        """Background task to flush batches. Each worker operates independently."""
        batch = []
        batch_size = getattr(settings, "BATCH_SIZE", 50)
        batch_timeout = getattr(settings, "BATCH_TIMEOUT_SECONDS", 2.0)

        logging.info(f"🚀 Batch worker {worker_id} started")

        while True:
            try:
                # Wait for first item with a timeout to allow graceful shutdown
                try:
                    item = await asyncio.wait_for(self.batch_queue.get(), timeout=5.0)
                    batch.append(item)
                except asyncio.TimeoutError:
                    # No items available, continue loop
                    continue

                # Collect more items
                start_time = time.time()
                while len(batch) < batch_size:
                    timeout = batch_timeout - (time.time() - start_time)
                    if timeout <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(
                            self.batch_queue.get(), timeout=timeout
                        )
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break

                # Process
                await self._process_batch(batch, worker_id)

                # Mark done
                for _ in batch:
                    self.batch_queue.task_done()
                batch = []

            except asyncio.CancelledError:
                logging.info(f"🛑 Batch worker {worker_id} cancelled")
                break
            except Exception as e:
                logging.error(f"Batch worker {worker_id} error: {e}")
                batch = []

    async def start_consuming(self):
        """Start consumer and batch workers."""
        await self.setup()

        # Start multiple background workers
        for i in range(settings.MAX_CONCURRENCY):
            task = asyncio.create_task(self._batch_worker(i))
            self.batch_worker_tasks.append(task)

        logging.info(
            f"👂 ETL Consumer listening on: {self.queue_name} with {settings.MAX_CONCURRENCY} parallel batch workers"
        )

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                await self.batch_queue.put(message)

    async def close(self):
        for task in self.batch_worker_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self.connection:
            await self.connection.close()
