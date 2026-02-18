import logging
import json
import asyncio
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
import anyio

from app.core.config import settings
from app.schemas.comparator import ComparisonResult, SimilarityPair, JobStatus
from app.core.image_processor import ImageProcessor

logger = logging.getLogger(__name__)

class JobManager:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)

    async def connect_redis(self):
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        logger.info(f"Connected to Redis at {settings.REDIS_URL}")

    async def close_redis(self):
        if self.redis:
            await self.redis.close()

    async def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        if not self.redis: return None
        data = await self.redis.get(f"job:{job_id}:status")
        if not data: return None
        return JobStatus(**json.loads(data))

    async def get_job_result(self, job_id: str) -> Optional[ComparisonResult]:
        if not self.redis: return None
        data = await self.redis.get(f"job:{job_id}:result")
        if not data: return None
        return ComparisonResult(**json.loads(data))

    async def submit_job(self, job_id: str, images: list, threshold: float):
        """Initializes job in Redis and starts background task."""
        initial_status = JobStatus(job_id=job_id, status="queued", progress=0.0)
        await self.redis.set(f"job:{job_id}:status", initial_status.json(), ex=3600*24)
        
        asyncio.create_task(self._process_job(job_id, images, threshold))

    async def _process_job(self, job_id: str, inputs: list, threshold: float):
        async with self.semaphore:
            try:
                await self.redis.set(
                    f"job:{job_id}:status", 
                    JobStatus(job_id=job_id, status="processing", progress=10.0).json()
                )

                logger.info(f"Job {job_id}: Downloading {len(inputs)} images...")
                images_map, failed_ids = await ImageProcessor.download_images(inputs)
                
                if not images_map:
                    raise Exception("No images could be downloaded successfully.")

                await self.redis.set(
                    f"job:{job_id}:status", 
                    JobStatus(job_id=job_id, status="processing", progress=40.0).json()
                )

                logger.info(f"Job {job_id}: Processing comparisons...")
                raw_results = await anyio.to_thread.run_sync(
                    ImageProcessor.compare_batch, 
                    images_map
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
                
                await self.redis.set(f"job:{job_id}:result", result.json(), ex=3600*24)
                await self.redis.set(
                    f"job:{job_id}:status", 
                    JobStatus(job_id=job_id, status="finished", progress=100.0).json(),
                    ex=3600*24
                )
                logger.info(f"Job {job_id} finished successfully.")

            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                error_status = JobStatus(
                    job_id=job_id, 
                    status="failed", 
                    error=str(e),
                    progress=0.0
                )
                await self.redis.set(f"job:{job_id}:status", error_status.json(), ex=3600*24)

job_manager = JobManager()