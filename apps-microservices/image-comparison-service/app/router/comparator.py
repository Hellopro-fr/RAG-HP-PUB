import logging
from fastapi import APIRouter, HTTPException, status
from typing import Union
import uuid
from app.schemas.comparator import CompareRequest, JobResponse, JobStatus, ComparisonResult, JobListResponse, CapacityResponse
from app.core.job_manager import job_manager
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/start", response_model=Union[JobResponse, ComparisonResult], status_code=status.HTTP_202_ACCEPTED)
async def start_comparison(request: CompareRequest):
    """
    Starts a new image comparison job.

    - If `sync` is True:
        - Returns 503 Service Unavailable if local capacity is full (triggering Nginx retry).
        - Otherwise, waits for completion and returns result.
    - If `sync` is False:
        - Always accepts (queues) the job. Returns Job ID.
    """
    # Generate ID if missing
    job_id = request.job_id or str(uuid.uuid4())

    existing_status = await job_manager.get_job_status(job_id)
    if existing_status:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} already exists with status: {existing_status.status}"
        )

    if request.sync:
        # Check Local Capacity for Sync requests
        if job_manager.is_local_full():
            logger.warning(
                f"Returning 503: local_active={job_manager.local_active_jobs}/"
                f"{settings.MAX_CONCURRENT_JOBS}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Instance at max capacity. Please retry (triggers Nginx failover)."
            )

        try:
            result = await job_manager.submit_job_sync(job_id, request.images, request.threshold)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Job failed: {str(e)}")
    else:
        # Async requests can be queued even if full
        await job_manager.submit_job_async(job_id, request.images, request.threshold)
        return JobResponse(
            message="Comparison job accepted and started.",
            job_id=job_id
        )

@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Check the running status of a job."""
    status_data = await job_manager.get_job_status(job_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")
    return status_data

@router.get("/jobs", response_model=JobListResponse)
async def list_all_jobs(limit: int = 100):
    """List all known jobs and their current status."""
    jobs = await job_manager.list_jobs(limit)
    return JobListResponse(total_jobs=len(jobs), jobs=jobs)

@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity():
    """Check global and local capacity."""
    return await job_manager.get_capacity()

@router.get("/results/{job_id}", response_model=ComparisonResult)
async def get_results(job_id: str):
    """Retrieve the final output of a completed job."""
    result = await job_manager.get_job_result(job_id)
    if not result:
        status_data = await job_manager.get_job_status(job_id)
        if status_data:
             raise HTTPException(status_code=202, detail=f"Job is still {status_data.status}")
        raise HTTPException(status_code=404, detail="Job results not found")
    return result
