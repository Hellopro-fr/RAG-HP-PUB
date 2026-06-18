import logging
import time
import json
import asyncio
from typing import Optional, List, Union
from datetime import datetime
import anyio
from common_utils.redis import cache_service

from app.core.config import settings
from app.schemas.comparator import ComparisonResult, SimilarityPair, JobStatus, CapacityResponse
from app.core.image_processor import ImageProcessor

logger = logging.getLogger(__name__)

# Key for tracking global running jobs across all replicas
GLOBAL_RUNNING_COUNT_KEY = "comparator:running_count"

class JobManager:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        # Track local active jobs manually since semaphore._value is internal/implementation specific
        self.local_active_jobs = 0

    def is_local_full(self) -> bool:
        """Check if this specific instance has reached max concurrency."""
        return self.local_active_jobs >= settings.MAX_CONCURRENT_JOBS

    def try_acquire_local_slot(self) -> bool:
        """
        Atomic check-and-reserve. No await => no yield point => no race
        between the check and the reservation.

        Returns True if a slot was reserved (caller must release).
        """
        if self.local_active_jobs >= settings.MAX_CONCURRENT_JOBS:
            return False
        self.local_active_jobs += 1
        return True

    def release_local_slot(self) -> None:
        """Release a previously-acquired slot. Idempotent against double-release."""
        self.local_active_jobs = max(0, self.local_active_jobs - 1)

    async def get_capacity(self) -> CapacityResponse:
        """Get current capacity metrics."""
        global_count = 0
        if cache_service.redis_client:
            val = await cache_service.redis_client.get(GLOBAL_RUNNING_COUNT_KEY)
            global_count = int(val) if val else 0

        return CapacityResponse(
            global_running_jobs=global_count,
            local_running_jobs=self.local_active_jobs,
            local_max_jobs=settings.MAX_CONCURRENT_JOBS,
            is_local_full=self.is_local_full()
        )

    async def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:status")
        if not data: return None
        return JobStatus(**json.loads(data))

    async def get_job_result(self, job_id: str) -> Optional[ComparisonResult]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:result")
        if not data: return None
        return ComparisonResult(**json.loads(data))

    async def list_jobs(self, limit: int = 100) -> List[JobStatus]:
        """Scans Redis for all job statuses."""
        if not cache_service.redis_client: return []

        job_keys = []
        async for key in cache_service.redis_client.scan_iter("job:*:status", count=limit):
            job_keys.append(key)
            if len(job_keys) >= limit:
                break

        if not job_keys:
            return []

        jobs_data = await cache_service.redis_client.mget(job_keys)

        results = []
        for data in jobs_data:
            if data:
                try:
                    results.append(JobStatus(**json.loads(data)))
                except Exception:
                    continue
        return results

    async def process_job_logic(self, job_id: str, inputs: list, threshold: float) -> ComparisonResult:
        """
        The core processing logic. Caller owns the local slot lifecycle:
          - Sync path: router calls try_acquire_local_slot() / release_local_slot()
          - Async path: submit_job_async() increments and the wrapper releases
        This function only manages the global Redis counter and the actual work.
        """
        start = time.monotonic()
        logger.info(
            f"Job {job_id}: starting | inputs={len(inputs)} | "
            f"local_active={self.local_active_jobs}/{settings.MAX_CONCURRENT_JOBS}"
        )

        # Increment Global Counter
        if cache_service.redis_client:
            await cache_service.redis_client.incr(GLOBAL_RUNNING_COUNT_KEY)

        try:
            async with self.semaphore:
                try:
                    # Update status to processing
                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=10.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )

                    logger.info(f"Job {job_id}: Loading {len(inputs)} images...")

                    images_map, failed_ids = await ImageProcessor.load_images(inputs)

                    if not images_map:
                        raise Exception("No valid images could be loaded/downloaded.")

                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=40.0).json(),
                        ex=settings.JOB_RESULT_TTL
                    )

                    logger.info(f"Job {job_id}: Processing comparisons...")

                    raw_results = await anyio.to_thread.run_sync(
                        ImageProcessor.compare_batch,
                        images_map,
                        inputs
                    )

                    similar_pairs = []
                    for res in raw_results:
                        if res['score'] >= threshold:
                            similar_pairs.append(SimilarityPair(**res))

                    result = ComparisonResult(
                        job_id=job_id,
                        status="finished",
                        created_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                        total_images=len(inputs),
                        matches_found=len(similar_pairs),
                        similar_pairs=similar_pairs,
                        failed_images=failed_ids
                    )

                    ttl = settings.JOB_RESULT_TTL
                    await cache_service.redis_client.set(f"job:{job_id}:result", result.json(), ex=ttl)
                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="finished", progress=100.0).json(),
                        ex=ttl
                    )
                    duration = time.monotonic() - start
                    logger.info(f"Job {job_id}: finished in {duration:.1f}s")

                    return result

                except Exception as e:
                    logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                    error_status = JobStatus(
                        job_id=job_id,
                        status="failed",
                        error=str(e),
                        progress=0.0
                    )
                    await cache_service.redis_client.set(f"job:{job_id}:status", error_status.json(), ex=settings.JOB_RESULT_TTL)
                    raise e
        finally:
            if cache_service.redis_client:
                await cache_service.safe_decrement_key(GLOBAL_RUNNING_COUNT_KEY)

    async def submit_job_async(self, job_id: str, images: list, threshold: float):
        """
        Fire-and-forget execution. Acquires a local slot before queuing the task,
        which is released in the wrapper's finally.
        """
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await cache_service.redis_client.set(f"job:{job_id}:status", initial_status.json(), ex=settings.JOB_RESULT_TTL)

        # Async submissions are never rejected — they queue past MAX via the semaphore
        # inside process_job_logic. Reserve the slot here so capacity reporting is accurate.
        self.local_active_jobs += 1

        async def _run_and_release():
            try:
                await self.process_job_logic(job_id, images, threshold)
            finally:
                self.release_local_slot()

        asyncio.create_task(_run_and_release())

    async def submit_job_sync(self, job_id: str, images: list, threshold: float) -> ComparisonResult:
        """
        Wait for execution and return result.
        Caller (router) owns the local slot lifecycle.
        """
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await cache_service.redis_client.set(f"job:{job_id}:status", initial_status.json(), ex=settings.JOB_RESULT_TTL)

        return await self.process_job_logic(job_id, images, threshold)

job_manager = JobManager()
