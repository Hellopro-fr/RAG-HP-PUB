from fastapi import APIRouter, HTTPException, status
from app.schemas.comparator import CompareRequest, JobResponse, JobStatus, ComparisonResult
from app.core.job_manager import job_manager

router = APIRouter()

@router.post("/start", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_comparison(request: CompareRequest):
    """
    Starts a new image comparison job.
    Accepts a list of URLs. Returns a Job ID immediately.
    Processing happens in the background.
    """
    existing_status = await job_manager.get_job_status(request.job_id)
    if existing_status:
        raise HTTPException(
            status_code=409, 
            detail=f"Job {request.job_id} already exists with status: {existing_status.status}"
        )

    await job_manager.submit_job(request.job_id, request.images, request.threshold)
    
    return JobResponse(
        message="Comparison job accepted and started.",
        job_id=request.job_id
    )

@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    status_data = await job_manager.get_job_status(job_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Job not found")
    return status_data

@router.get("/results/{job_id}", response_model=ComparisonResult)
async def get_results(job_id: str):
    result = await job_manager.get_job_result(job_id)
    if not result:
        status_data = await job_manager.get_job_status(job_id)
        if status_data:
             raise HTTPException(status_code=202, detail=f"Job is still {status_data.status}")
        raise HTTPException(status_code=404, detail="Job results not found")
    return result