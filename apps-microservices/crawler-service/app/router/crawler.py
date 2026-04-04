import os
import logging
import re
import json
from datetime import datetime
from typing import Dict, Optional, List

import aiofiles
from fastapi import APIRouter, HTTPException, status, Query, Depends
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse
from pydantic import BaseModel

from app.core.crawler_manager import crawler_manager, CRAWL_RUNNING_COUNT_KEY, CRAWL_JOB_PREFIX, CRAWL_MAX_GLOBAL_KEY
from common_utils.redis import cache_service
from app.core.config import settings
from app.schemas.crawler import CrawlRequest, CrawlResponse, CrawlStatus, StopResponse, IncludeInArchive, CapacityResponse, ReindexResponse, ArchiveResponse, PruneResponse, PendingCallbacksResponse

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_job_or_recover(crawl_id: str) -> dict:
    """
    FastAPI dependency to retrieve a crawl job from Redis.
    If the job is not found in Redis, it attempts to recover it from
    the persistent storage and re-index it.
    Raises a 404 HTTPException if the job cannot be found in Redis or on disk.
    """
    job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
    job_info = await cache_service.get_json(job_key)

    if job_info:
        return job_info

    # --- Job not in Redis, attempt recovery from disk ---
    logger.warning(f"Job '{crawl_id}' not found in Redis. Attempting recovery from storage.")
    job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)

    if not os.path.isdir(job_storage_path):
        logger.error(f"Recovery failed: Storage directory not found for job '{crawl_id}'.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl job not found.")

    marker_path = os.path.join(job_storage_path, '_completion_marker.json')
    final_status = None  # Will be determined below

    # Check completion marker for finished/failed jobs
    if os.path.exists(marker_path):
        try:
            async with aiofiles.open(marker_path, 'r') as f:
                content = await f.read()
                marker_data = json.loads(content)
            final_status = marker_data.get("final_status", "failed")
        except Exception:
            logger.error(f"Could not parse completion marker for '{crawl_id}'.")
            final_status = "failed"
    else:
        # No completion marker: job may still be running OR crashed without cleanup
        # Check if this instance is actively running the crawl process
        is_running_locally = (
            crawl_id in crawler_manager.local_processes
            and crawler_manager.local_processes[crawl_id].returncode is None
        )
        if is_running_locally:
            final_status = "running"
            logger.info(f"No completion marker for '{crawl_id}', but process is alive locally. Status: RUNNING.")
        else:
            # Process not running on this instance — check age as secondary heuristic
            # (another replica may be running it, but we can't verify cross-instance)
            try:
                storage_mtime = os.path.getmtime(job_storage_path)
                age_hours = (datetime.utcnow().timestamp() - storage_mtime) / 3600
                if age_hours < 2:
                    final_status = "running"
                    logger.info(f"No completion marker for '{crawl_id}', storage modified {age_hours:.1f}h ago. Possibly running on another replica.")
                else:
                    final_status = "failed"
                    logger.warning(f"No completion marker for '{crawl_id}', storage stale ({age_hours:.1f}h), no local process. Assuming FAILED.")
            except Exception:
                final_status = "failed"

    # Reconstruct metadata by parsing the log file (best effort).
    # Uses --domain= and --site= CLI arg patterns from the Node.js crawler command line.
    domain, start_url = "unknown", "http://unknown.com"
    log_path = os.path.join(job_storage_path, 'crawler.log')
    if os.path.exists(log_path):
        try:
            async with aiofiles.open(log_path, 'r', errors='ignore') as f:
                line_count = 0
                async for line in f:
                    # Match CLI args: --domain=value or --site=value
                    if domain == "unknown":
                        m = re.search(r'--domain=(\S+)', line)
                        if m: domain = m.group(1)
                    if start_url == "http://unknown.com":
                        m = re.search(r'--site=(\S+)', line)
                        if m: start_url = m.group(1)

                    if (domain != "unknown" and start_url != "http://unknown.com") or line_count > 300:
                        break
                    line_count += 1
        except Exception as e:
            logger.error(f"Error reading log file for '{crawl_id}' during recovery: {e}")

    recovered_data = {
        "crawl_id": crawl_id, "status": final_status, "domain": domain,
        "start_url": start_url, "start_time": datetime.fromtimestamp(os.path.getctime(job_storage_path)).isoformat(),
        "storage_path": job_storage_path,
        "failure_callback_url": None, "pid": None
    }

    # State keys can persist safely — the distributed lock (crawl_lock:{id}) is separate.
    # TTL 7 days: recovered orphan jobs should not persist in Redis indefinitely.
    logger.info(f"Successfully recovered job '{crawl_id}' from storage with status '{final_status}'. Re-indexing in Redis.")
    await cache_service.set_json(job_key, recovered_data, ttl=604800)

    return recovered_data


@router.post("/reindex-storage", response_model=ReindexResponse)
async def reindex_storage():
    """
    Scans the storage volume for orphaned crawl jobs (present on disk but not in Redis)
    and re-indexes them. This is a recovery tool.
    """
    try:
        summary = await crawler_manager.reindex_storage()
        return summary
    except Exception as e:
        logger.error(f"Failed during storage re-indexing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during re-indexing.")

@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity():
    """
    Checks the current global capacity of the crawler service by reading
    shared values from Redis.
    """
    try:
        if not cache_service.redis_client:
            raise HTTPException(status_code=503, detail="Redis connection not available.")

        running_jobs_raw = await cache_service.get_key(CRAWL_RUNNING_COUNT_KEY)
        try:
            running_jobs = max(0, int(running_jobs_raw)) if running_jobs_raw else 0
        except (ValueError, TypeError):
            logger.warning(f"Invalid running_jobs counter value in Redis: '{running_jobs_raw}'. Defaulting to 0.")
            running_jobs = 0
        
        # Read the max global jobs value from the central Redis key.
        max_global_raw = await cache_service.get_key(CRAWL_MAX_GLOBAL_KEY)
        # If the key is missing, use the configurable fallback from settings.
        max_global = int(max_global_raw) if max_global_raw else settings.DEFAULT_MAX_GLOBAL_CRAWLS
        
        return CapacityResponse(
            running_jobs=running_jobs,
            max_global_jobs=max_global,
            is_full=running_jobs >= max_global
        )
    except Exception as e:
        logger.error(f"Failed to get crawler capacity from Redis: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Could not determine crawler service capacity.")


@router.post("/start", response_model=CrawlResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_new_crawl(payload: CrawlRequest):
    """
    Starts or resumes a web crawling job. A job is uniquely identified by the `id` field.
    If a job with the same `id` is already running, an error will be returned.
    """
    try:
        params = {
            "crawlMode": payload.crawl_mode.value,
            "typecrawling": payload.type_crawling,
            "method": payload.method,
            "dropdata": payload.drop_data,
            "skipquestionmark": payload.skip_question_mark,
            "skipdiez": payload.skip_diez,
            "tokeep": ";".join(payload.to_keep) if payload.to_keep else None,
            "toremove": ";".join(payload.to_remove) if payload.to_remove else None,
            "proxyapify": payload.proxy_apify or settings.APIFY_PROXY,
            "bypassquestionmark": payload.bypass_question_mark,
            "bypassdiez": payload.bypass_diez,
            "breaklimit": payload.break_limit,
            "percrawl": payload.per_crawl,
            "perminute": payload.per_minute,
            "camoufox": payload.camoufox, # Pass Camoufox flag
        }

        # Add update specific params
        if payload.previous_crawl_id:
             params["previousCrawlId"] = payload.previous_crawl_id
        
        if payload.update_thresholds:
             if payload.update_thresholds.max_errors is not None:
                 params["maxErrors"] = payload.update_thresholds.max_errors
             if payload.update_thresholds.max_redirects is not None:
                 params["maxRedirects"] = payload.update_thresholds.max_redirects
             if payload.update_thresholds.max_new_urls is not None:
                 params["maxNewUrls"] = payload.update_thresholds.max_new_urls
             
             # V1 Circuit Breaker Params (Mapped to CLI flags)
             if payload.update_thresholds.min_sample is not None:
                 params["minSample"] = payload.update_thresholds.min_sample
             if payload.update_thresholds.max_error_rate is not None:
                 params["maxErrorRate"] = payload.update_thresholds.max_error_rate
             if payload.update_thresholds.max_redirect_rate is not None:
                 params["maxRedirectRate"] = payload.update_thresholds.max_redirect_rate
             if payload.update_thresholds.max_growth_rate is not None:
                 params["maxGrowthRate"] = payload.update_thresholds.max_growth_rate
             
             if payload.update_thresholds.max_abs_errors is not None:
                 params["maxAbsErrors"] = payload.update_thresholds.max_abs_errors
             if payload.update_thresholds.max_abs_redirects is not None:
                 params["maxAbsRedirects"] = payload.update_thresholds.max_abs_redirects
             if payload.update_thresholds.max_abs_new is not None:
                 params["maxAbsNew"] = payload.update_thresholds.max_abs_new
        
        # The user-provided `id` is now the stable and unique identifier for the crawl job.
        crawl_id = await crawler_manager.start_crawl(
            domain=payload.domain,
            start_url=str(payload.start_url),
            crawl_id=payload.id,
            callback_url=str(payload.callback_url),
            failure_callback_url=str(payload.failure_callback_url) if payload.failure_callback_url else None,
            params=params
        )
        
        return CrawlResponse(
            message="Crawl job accepted and started.",
            crawl_id=crawl_id
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to start crawl for domain {payload.domain}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while starting the crawl.")

@router.post("/stop/{crawl_id}", response_model=StopResponse)
async def stop_existing_crawl(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Stops a currently running crawl job.
    """
    success = await crawler_manager.stop_crawl(job_info)
    if not success:
        raise HTTPException(status_code=409, detail=f"Crawl job with ID '{crawl_id}' not found or not in a running state.")
    return StopResponse(message="Stop signal sent to crawl job.", crawl_id=crawl_id)

@router.post("/force-finish/{crawl_id}")
async def force_finish_crawl(
    crawl_id: str, 
    target_status: str = Query("finished", description="Target status: 'finished' or 'failed'"),
    job_info: dict = Depends(get_job_or_recover)
):
    """
    Force a stuck job to a terminal status.
    Use this to clean up jobs stuck in 'stopping' or 'running' state without an active process.
    """
    result = await crawler_manager.force_finish_crawl(job_info, target_status)
    return result

@router.get("/status", response_model=Dict[str, CrawlStatus])
async def get_all_crawl_statuses(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status. Supports comma-separated values (e.g., running,stopping).")
):
    """
    Gets the status of all crawl jobs. Optionally filter by status.
    Examples: /status?status=running, /status?status=finished, /status?status=running,stopping
    """
    filter_list = [s.strip() for s in status_filter.split(",") if s.strip()] if status_filter else None
    return await crawler_manager.get_all_statuses(status_filter=filter_list)

@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.
    """
    return await crawler_manager.get_status(job_info)

@router.get("/results/{crawl_id}")
async def download_crawl_results(
    include: List[IncludeInArchive] = Query(..., description="Specify which components to include in the archive. Can be provided multiple times (e.g., ?include=dataset&include=request_queues)."),
    job_info: dict = Depends(get_job_or_recover)
):
    """
    Downloads a custom archive of a completed crawl job, including only the specified components.
    For archived crawls (data uploaded to GCS), automatically retrieves the full archive
    from GCS via the download daemon and streams it to the client.
    """
    try:
        crawl_id = job_info['crawl_id']
        archive_path, is_temporary = await crawler_manager.get_results_archive(job_info, include)

        if not os.path.exists(archive_path):
            logger.error(
                f"Archive file was not created at expected path: {archive_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not generate results archive for crawl '{crawl_id}'. "
                f"The crawl data may have been cleaned up after archiving to GCS."
            )

        if is_temporary:
            # Stream the file and clean up after streaming completes (prevents race with BackgroundTasks)
            def iterfile():
                with open(archive_path, 'rb') as f:
                    yield from f
                # Cleanup after streaming is complete
                crawler_manager.cleanup_temp_download(crawl_id)

            return StreamingResponse(
                iterfile(),
                media_type='application/gzip',
                headers={"Content-Disposition": f"attachment; filename={crawl_id}-results.tar.gz"}
            )
        else:
            return FileResponse(path=archive_path, media_type='application/gzip', filename=f"{crawl_id}-results.tar.gz")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error generating results for crawl '{job_info.get('crawl_id')}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate results archive.")

@router.post("/archive/{crawl_id}", response_model=ArchiveResponse)
async def archive_crawl_to_gcs(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Archives a finished crawl job to a shared volume for upload to Google Cloud Storage.
    The job must be in 'finished' state. After archiving, status becomes 'archived'
    to prevent double-archiving. Local data files are cleaned up (logs and markers are preserved).
    The upload daemon will pick up the archive and upload it to GCS asynchronously.
    """
    try:
        result = await crawler_manager.archive_crawl(job_info)
        return ArchiveResponse(
            message="Crawl archived successfully. Pending upload to GCS by daemon.",
            **result
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error archiving crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during archiving.")

@router.post("/reconcile-jobs")
async def reconcile_jobs():
    """
    Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
    marks them as failed, and corrects the global running jobs counter.
    Use this to fix counter drift where running_jobs > actual running jobs.
    """
    await crawler_manager.reconcile_jobs()
    return {"status": "reconciliation_complete"}

@router.get("/pending-callbacks", response_model=PendingCallbacksResponse)
async def get_pending_callbacks():
    """
    Returns all failed webhook callbacks stored in Redis after retry exhaustion.
    These can be reviewed and replayed manually or by an automated reconciliation process.
    """
    callbacks = await crawler_manager.get_pending_callbacks()
    return PendingCallbacksResponse(count=len(callbacks), callbacks=callbacks)

@router.delete("/pending-callbacks")
async def clear_pending_callbacks():
    """Clears all failed webhook callbacks from Redis."""
    deleted = await crawler_manager.clear_pending_callbacks()
    return {"status": "cleared", "keys_deleted": deleted}

@router.post("/prune-archives", response_model=PruneResponse)
async def prune_archives(
    max_age_hours: int = Query(24, description="Delete archives older than this many hours."),
    delete_all: bool = Query(False, description="If true, ignores max_age_hours and deletes ALL archives.")
):
    """
    Manually triggers the cleanup of old archive files from storage.
    Useful for freeing up disk space on demand.
    """
    try:
        deleted, retained, errors = await crawler_manager.cleanup_archives(max_age_hours, delete_all=delete_all)
        
        msg_suffix = "ALL archives deleted." if delete_all else f"Deleted {deleted} files older than {max_age_hours}h."
        
        return PruneResponse(
            deleted_count=deleted,
            retained_count=retained,
            errors=errors,
            message=f"Cleanup complete. {msg_suffix}"
        )
    except Exception as e:
        logger.error(f"Manual archive prune failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))