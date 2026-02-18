from fastapi import APIRouter, HTTPException, status
from typing import Union
from app.schemas.comparator import CompareRequest, JobResponse, JobStatus, ComparisonResult, JobListResponse
from app.core.job_manager import job_manager

router = APIRouter()

@router.post("/start", response_model=Union[JobResponse, ComparisonResult], status_code=status.HTTP_202_ACCEPTED)
async def start_comparison(request: CompareRequest):
    """
    Starts a new image comparison job.
    
    - If `sync` is False (default): Returns a Job ID immediately. Processing runs in background.
    - If `sync` is True: Waits for the job to complete and returns the full result.
    """
    existing_status = await job_manager.get_job_status(request.job_id)
    if existing_status:
        raise HTTPException(
            status_code=409, 
            detail=f"Job {request.job_id} already exists with status: {existing_status.status}"
        )

    if request.sync:
        # Synchronous execution
        try:
            result = await job_manager.submit_job_sync(request.job_id, request.images, request.threshold)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Job failed: {str(e)}")
    else:
        # Asynchronous execution
        await job_manager.submit_job_async(request.job_id, request.images, request.threshold)
        return JobResponse(
            message="Comparison job accepted and started.",
            job_id=request.job_id
        )

@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """
    Check the running status of a job.
    """
    status_data = await job_manager.get_job_status(job_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")
    return status_data

@router.get("/jobs", response_model=JobListResponse)
async def list_all_jobs(limit: int = 100):
    """
    List all known jobs and their current status.
    Limited to the most recent/found keys in Redis.
    """
    jobs = await job_manager.list_jobs(limit)
    return JobListResponse(total_jobs=len(jobs), jobs=jobs)

@router.get("/results/{job_id}", response_model=ComparisonResult)
async def get_results(job_id: str):
    """
    Retrieve the final output of a completed job.
    """
    result = await job_manager.get_job_result(job_id)
    if not result:
        status_data = await job_manager.get_job_status(job_id)
        if status_data:
             raise HTTPException(status_code=202, detail=f"Job is still {status_data.status}")
        raise HTTPException(status_code=404, detail="Job results not found")
    return result