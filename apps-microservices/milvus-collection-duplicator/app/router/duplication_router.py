import uuid
import logging
import threading
from typing import Dict

from fastapi import APIRouter, HTTPException

from app.schemas.duplication_schemas import (
    DuplicationRequest,
    DuplicationResponse,
    JobStatusResponse,
    JobStatus,
    RetryRequest,
    RetryResponse,
)
from app.core.milvus_connection import duplicate_collection, retry_failed_rows

logger = logging.getLogger(__name__)

duplication_router = APIRouter(prefix="/duplicate", tags=["Duplication"])

# In-memory job store (sufficient for single-instance use)
_jobs: Dict[str, dict] = {}


def _run_duplication_job(job_id: str, request: DuplicationRequest):
    """Background thread function that runs the actual duplication."""
    job = _jobs[job_id]
    job["status"] = JobStatus.RUNNING
    job["message"] = (
        f"Duplicating '{request.source_collection}' → '{request.target_collection}'…"
    )

    try:
        result = duplicate_collection(
            source_name=request.source_collection,
            target_name=request.target_collection,
            text_field=request.text_field,
            batch_size=request.batch_size,
            analyzer_language=request.analyzer_language,
            limit=request.limit,
            parallel_workers=request.parallel_workers,
            job_id=job_id,
            job_state=job,
            float_vector_index_type=request.float_vector_index_type,
            float_vector_index_params=request.float_vector_index_params,
        )
        job["status"] = JobStatus.COMPLETED
        job["error_file"] = result.get("error_file")
        job["message"] = (
            f"✅ Duplication complete. {result['total_inserted']} records "
            f"copied in {result['elapsed_seconds']}s. "
            f"Skipped: {result.get('total_skipped', 0)}. "
            f"Fields: {result['fields']}"
        )
        if result.get("error_file"):
            job["message"] += f"\n📄 Error log: {result['error_file']}"
    except Exception as e:
        logger.error(f"❌ Duplication job {job_id} failed: {e}", exc_info=True)
        job["status"] = JobStatus.FAILED
        job["error"] = str(e)
        job["message"] = f"❌ Duplication failed: {e}"


@duplication_router.post(
    "",
    response_model=DuplicationResponse,
    summary="Trigger a collection duplication",
    description=(
        "Starts a background job to duplicate a Milvus collection with all its data, "
        "adding a `sparse_embedding` field powered by Milvus 2.6 built-in BM25 Function. "
        "Returns immediately with a job ID to poll for progress."
    ),
)
def start_duplication(request: DuplicationRequest):
    # Prevent duplicating to the same name
    if request.source_collection == request.target_collection:
        raise HTTPException(
            status_code=400,
            detail="source_collection and target_collection must be different.",
        )

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": JobStatus.PENDING,
        "total_source_entities": None,
        "records_copied": 0,
        "message": "Job queued, starting soon…",
        "error": None,
        "error_file": None,
    }

    # Run duplication in a background thread (not blocking the event loop)
    thread = threading.Thread(
        target=_run_duplication_job,
        args=(job_id, request),
        daemon=True,
    )
    thread.start()

    return DuplicationResponse(
        job_id=job_id,
        message=f"Duplication job started: '{request.source_collection}' → '{request.target_collection}'",
        status=JobStatus.PENDING,
    )


@duplication_router.get(
    "/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Check duplication job progress",
    description="Returns the current status and progress of a duplication job.",
)
def get_job_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    job = _jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        total_source_entities=job.get("total_source_entities"),
        records_copied=job.get("records_copied", 0),
        message=job.get("message", ""),
        error=job.get("error"),
        error_file=job.get("error_file"),
    )


@duplication_router.get(
    "/jobs",
    summary="List all duplication jobs",
    description="Returns all known duplication jobs and their current status.",
)
def list_jobs():
    return {
        job_id: {
            "status": job["status"],
            "records_copied": job.get("records_copied", 0),
            "total_source_entities": job.get("total_source_entities"),
            "message": job.get("message", ""),
            "error_file": job.get("error_file"),
        }
        for job_id, job in _jobs.items()
    }


@duplication_router.post(
    "/retry",
    response_model=RetryResponse,
    summary="Retry failed rows from an error log",
    description=(
        "Reads a duplication error log file and attempts to re-insert "
        "the failed rows into the target collection. Returns the count of "
        "successfully retried rows and any rows that still fail."
    ),
)
def retry_duplication(request: RetryRequest):
    try:
        result = retry_failed_rows(
            source_name=request.source_collection,
            target_name=request.target_collection,
            error_file_name=request.error_file,
            text_field=request.text_field,
            batch_size=request.batch_size,
        )
        return RetryResponse(
            total_retried=result["total_retried"],
            total_succeeded=result["total_succeeded"],
            total_still_failed=result["total_still_failed"],
            new_error_file=result.get("new_error_file"),
            message=result["message"],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Retry failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retry failed: {e}")
