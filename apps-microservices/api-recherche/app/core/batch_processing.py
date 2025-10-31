import asyncio
import time
from typing import List, Any, Coroutine
import logging

logger = logging.getLogger(__name__)

class BatchProcessor:
    def __init__(self, process_batch_callback: Coroutine, batch_size: int = 16, max_latency: float = 0.1):
        self.batch_size = batch_size
        self.max_latency = max_latency
        self.process_batch_callback = process_batch_callback
        self.queue = asyncio.Queue()
        self.worker_task = asyncio.create_task(self._worker())

    async def _worker(self):
        while True:
            try:
                await self._process_batch()
            except Exception as e:
                logger.error(f"Error in batch processing worker: {e}", exc_info=True)
            await asyncio.sleep(self.max_latency / 2)

    async def _process_batch(self):
        batch = []
        futures = []
        start_time = time.time()

        while (time.time() - start_time < self.max_latency) and (len(batch) < self.batch_size):
            try:
                request, future = await asyncio.wait_for(self.queue.get(), timeout=self.max_latency / 10)
                batch.append(request)
                futures.append(future)
            except asyncio.TimeoutError:
                break
        
        if not batch:
            return

        try:
            results = await self.process_batch_callback(batch)
            for i, result in enumerate(results):
                if i < len(futures):
                    futures[i].set_result(result)
        except Exception as e:
            logger.error(f"Error processing batch: {e}", exc_info=True)
            for future in futures:
                if not future.done():
                    future.set_exception(e)

    async def process(self, request: Any):
        future = asyncio.Future()
        await self.queue.put((request, future))
        return await future

    def shutdown(self):
        self.worker_task.cancel()

