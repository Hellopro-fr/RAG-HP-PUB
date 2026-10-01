import logging
import time
import json
import asyncio
from typing import Optional, List, Union
from datetime import datetime
import anyio
from common_utils.redis import cache_service

from app.core.config import settings
from app.schemas.comparator import ComparisonResult, SimilarityPair, JobStatus, CapacityResponse, JobInput
from app.core.image_processor import ImageProcessor
from app.core import feature_cache

logger = logging.getLogger(__name__)

# Key for tracking global running jobs across all replicas
GLOBAL_RUNNING_COUNT_KEY = "comparator:running_count"

class JobManager:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        # Track local active jobs manually since semaphore._value is internal/implementation specific
        self.local_active_jobs = 0
        # Strong refs to fire-and-forget tasks — without this the event loop only keeps
        # a weak ref and a job can be garbage-collected mid-flight.
        self._background_tasks: set = set()

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

    async def _write_inputs(self, job_id: str, images: list, source_by_id: Optional[dict] = None) -> None:
        """Persist submitted inputs (id, url, feature source) so /status and /results
        can echo them. Written at submit (source='pending') and overwritten after the
        cache-aside resolution with cached | fresh | failed."""
        if not cache_service.redis_client:
            return
        src = source_by_id or {}
        payload = [
            {"id": inp.id, "url": str(inp.url) if inp.url else None, "source": src.get(inp.id, "pending")}
            for inp in images
        ]
        await cache_service.redis_client.set(
            f"job:{job_id}:inputs", json.dumps(payload), ex=settings.JOB_RESULT_TTL
        )

    async def _read_inputs(self, job_id: str) -> Optional[List[JobInput]]:
        data = await cache_service.redis_client.get(f"job:{job_id}:inputs")
        if not data:
            return None
        try:
            return [JobInput(**x) for x in json.loads(data)]
        except Exception:
            return None

    async def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:status")
        if not data: return None
        status_obj = JobStatus(**json.loads(data))
        status_obj.inputs = await self._read_inputs(job_id)
        return status_obj

    async def get_job_result(self, job_id: str) -> Optional[ComparisonResult]:
        if not cache_service.redis_client: return None
        data = await cache_service.redis_client.get(f"job:{job_id}:result")
        if not data: return None
        result_obj = ComparisonResult(**json.loads(data))
        result_obj.inputs = await self._read_inputs(job_id)
        return result_obj

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
                        ex=settings.PROCESSING_STATUS_TTL_S
                    )

                    logger.info(f"Job {job_id}: Loading {len(inputs)} images...")

                    # Cache-aside: read cached per-URL features first; only download+extract misses.
                    # Cacheable = pure URL inputs. Base64 `content` inputs (and any input with
                    # neither url nor content) are never cached and always go to load_images.
                    url_inputs = [inp for inp in inputs if inp.url and not inp.content]
                    other_inputs = [inp for inp in inputs if not (inp.url and not inp.content)]

                    cached_by_url = await feature_cache.get_features([str(inp.url) for inp in url_inputs])
                    cached_features = {
                        inp.id: cached_by_url[str(inp.url)]
                        for inp in url_inputs if str(inp.url) in cached_by_url
                    }
                    miss_url_inputs = [inp for inp in url_inputs if str(inp.url) not in cached_by_url]

                    # Download only the misses + the uncacheable inputs.
                    to_load = miss_url_inputs + other_inputs
                    images_map, failed_ids = await ImageProcessor.load_images(to_load)

                    # Extract features for the freshly downloaded images (off the event loop).
                    fresh_features = await anyio.to_thread.run_sync(
                        ImageProcessor.extract_features_for,
                        images_map
                    )

                    # Cache the freshly extracted URL-miss features (content inputs are not cached).
                    await feature_cache.set_features({
                        str(inp.url): fresh_features[inp.id]
                        for inp in miss_url_inputs if inp.id in fresh_features
                    })

                    all_features = {**cached_features, **fresh_features}
                    logger.info(
                        f"Job {job_id}: features ready | cached={len(cached_features)} "
                        f"fresh={len(fresh_features)} failed={len(failed_ids)}"
                    )

                    # Persist per-input feature source (cached|fresh|failed) for /status + /results.
                    source_by_id = {iid: "cached" for iid in cached_features}
                    source_by_id.update({iid: "fresh" for iid in fresh_features})
                    source_by_id.update({f.id: "failed" for f in failed_ids})
                    await self._write_inputs(job_id, inputs, source_by_id)

                    if not all_features:
                        raise Exception("No valid images could be loaded/downloaded.")

                    await cache_service.redis_client.set(
                        f"job:{job_id}:status",
                        JobStatus(job_id=job_id, status="processing", progress=40.0).json(),
                        ex=settings.PROCESSING_STATUS_TTL_S
                    )

                    logger.info(f"Job {job_id}: Processing comparisons...")

                    raw_results = await anyio.to_thread.run_sync(
                        ImageProcessor.compare_features,
                        all_features,
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

    async def _mark_failed_timeout(self, job_id: str) -> None:
        """Write a terminal 'failed' status for a job that exceeded PROCESSING_DEADLINE_S."""
        logger.error(f"Job {job_id}: exceeded PROCESSING_DEADLINE_S={settings.PROCESSING_DEADLINE_S}s — marking failed")
        if cache_service.redis_client:
            st = JobStatus(
                job_id=job_id,
                status="failed",
                error=f"timeout: exceeded {settings.PROCESSING_DEADLINE_S}s",
                progress=0.0,
            )
            await cache_service.redis_client.set(f"job:{job_id}:status", st.json(), ex=settings.JOB_RESULT_TTL)

    async def submit_job_async(self, job_id: str, images: list, threshold: float):
        """
        Fire-and-forget execution. Acquires a local slot before queuing the task,
        which is released in the wrapper's finally.
        """
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await cache_service.redis_client.set(f"job:{job_id}:status", initial_status.json(), ex=settings.JOB_RESULT_TTL)
        await self._write_inputs(job_id, images)

        # Async submissions are never rejected — they queue past MAX via the semaphore
        # inside process_job_logic. Reserve the slot here so capacity reporting is accurate.
        self.local_active_jobs += 1

        async def _run_and_release():
            try:
                await asyncio.wait_for(
                    self.process_job_logic(job_id, images, threshold),
                    timeout=settings.PROCESSING_DEADLINE_S,
                )
            except asyncio.TimeoutError:
                # process_job_logic got CancelledError -> its semaphore + finally
                # (safe_decrement_key) already ran; here we record the terminal failure.
                await self._mark_failed_timeout(job_id)
            finally:
                self.release_local_slot()

        task = asyncio.create_task(_run_and_release())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def submit_job_sync(self, job_id: str, images: list, threshold: float) -> ComparisonResult:
        """
        Wait for execution and return result.
        Caller (router) owns the local slot lifecycle.
        """
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await cache_service.redis_client.set(f"job:{job_id}:status", initial_status.json(), ex=settings.JOB_RESULT_TTL)
        await self._write_inputs(job_id, images)

        try:
            return await asyncio.wait_for(
                self.process_job_logic(job_id, images, threshold),
                timeout=settings.PROCESSING_DEADLINE_S,
            )
        except asyncio.TimeoutError:
            await self._mark_failed_timeout(job_id)
            raise

job_manager = JobManager()
