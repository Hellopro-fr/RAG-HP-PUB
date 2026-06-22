import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.async_jobs import (
    poll_status, _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded,
)
from app.schemas.async_jobs import (
    CleanAsyncRequest, HeaderFooterAsyncRequest,
    AsyncSubmitResponse, AsyncJobStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _poll_hint() -> int:
    return min(max(settings.HEARTBEAT_INTERVAL_S, 2), settings.ASYNC_POLL_HINT_MAX_S)


async def _submit(job_type: str, request, http_request: Request):
    jm = http_request.app.state.job_manager
    try:
        job_id, status_code = await jm.submit(job_type, request)
    except _JobsDisabled:
        raise HTTPException(status_code=503,
                            detail={"detail": "Async jobs disabled", "retryable": False})
    except _JobsUnavailable:
        raise HTTPException(status_code=503,
                            detail={"detail": "Job store unavailable", "retryable": False})
    except _JobCapacityExceeded:
        ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
        raise HTTPException(
            status_code=503,
            detail={"detail": "Max active jobs reached", "retryable": True,
                    "retry_after_seconds": int(ra)},
            headers={"Retry-After": ra},
        )
    body = AsyncSubmitResponse(job_id=job_id, status="pending",
                               total=len(request.items), poll_after_seconds=_poll_hint())
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.post("/clean-async")
async def submit_clean_async(request: CleanAsyncRequest, http_request: Request):
    return await _submit("clean", request, http_request)


@router.post("/extract/header-footer-async")
async def submit_header_footer_async(request: HeaderFooterAsyncRequest, http_request: Request):
    return await _submit("header_footer", request, http_request)


@router.get("/jobs/{job_id}", response_model=AsyncJobStatusResponse)
async def poll_job(job_id: str, http_request: Request) -> AsyncJobStatusResponse:
    jm = http_request.app.state.job_manager
    rec = await jm.get_record(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    status = poll_status(rec, time.time(), settings.STALE_THRESHOLD_S)
    results = rec.get("results") if status in ("completed", "failed", "stale") else None
    return AsyncJobStatusResponse(
        job_id=rec["job_id"], job_type=rec.get("job_type", ""), status=status,
        total=rec["total"], done=rec.get("done", 0), results=results,
        error=rec.get("error"), poll_after_seconds=_poll_hint(),
    )
