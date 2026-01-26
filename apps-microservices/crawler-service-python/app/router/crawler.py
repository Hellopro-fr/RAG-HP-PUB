import os
import logging
import re
import json
from datetime import datetime
from typing import Dict, Optional, List

import aiofiles
from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Query, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.crawler_manager import crawler_manager, CRAWL_RUNNING_COUNT_KEY, CRAWL_JOB_PREFIX
from app.core.redis import cache_service
from app.core.config import settings
from app.schemas.crawler import CrawlRequest, CrawlResponse, CrawlStatus, StopResponse, IncludeInArchive, CapacityResponse, ReindexResponse, ArchiveResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Centralized key for storing the dynamic global max crawls value in Redis
CRAWL_MAX_GLOBAL_KEY = "crawl_jobs:max_global_crawls"


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
        # Heuristic: if storage was modified recently (< 2 hours), assume running
        try:
            storage_mtime = os.path.getmtime(job_storage_path)
            age_hours = (datetime.now().timestamp() - storage_mtime) / 3600
            if age_hours < 2:
                final_status = "running"
                logger.info(f"No completion marker for '{crawl_id}', but storage modified {age_hours:.1f}h ago. Assuming RUNNING.")
            else:
                final_status = "failed"
                logger.warning(f"No completion marker for '{crawl_id}', storage stale ({age_hours:.1f}h). Assuming FAILED.")
        except Exception:
            final_status = "failed"

    # Reconstruct metadata by parsing the log file (best effort)
    domain, start_url = "unknown", "http://unknown.com"
    log_path = os.path.join(job_storage_path, 'crawler.log')
    if os.path.exists(log_path):
        try:
            async with aiofiles.open(log_path, 'r', errors='ignore') as f:
                # Read a limited number of lines to avoid loading huge logs
                line_count = 0
                async for line in f:
                    if '"domain":' in line:
                        match = re.search(r'"domain":\s*"([^"]+)"', line)
                        if match: domain = match.group(1)
                    if '"site":' in line:
                        match = re.search(r'"site":\s*"([^"]+)"', line)
                        if match: start_url = match.group(1)
                    if (domain != "unknown" and start_url != "http://unknown.com") or line_count > 200:
                        break
                    line_count += 1
        except Exception as e:
            logger.error(f"Error reading log file for '{crawl_id}' during recovery: {e}")

    recovered_data = {
        "crawl_id": crawl_id, "status": final_status, "domain": domain,
        "start_url": start_url, "start_time": datetime.fromtimestamp(os.path.getctime(job_storage_path)),
        "storage_path": job_storage_path,
        "failure_callback_url": None, "pid": None
    }

    logger.info(f"Successfully recovered job '{crawl_id}' from storage with status '{final_status}'. Re-indexing in Redis.")
    await cache_service.set_json(job_key, recovered_data)

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
        running_jobs = int(running_jobs_raw) if running_jobs_raw else 0
        
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
             if payload.update_thresholds.max_errors:
                 params["maxErrors"] = payload.update_thresholds.max_errors
             if payload.update_thresholds.max_redirects:
                 params["maxRedirects"] = payload.update_thresholds.max_redirects
             if payload.update_thresholds.max_new_urls:
                 params["maxNewUrls"] = payload.update_thresholds.max_new_urls
        
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
async def get_all_crawl_statuses():
    """
    Gets the status of all active crawl jobs on this instance.
    """
    return await crawler_manager.get_all_statuses()

@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(job_info: dict = Depends(get_job_or_recover)):
    """
    Gets the detailed status of a specific crawl job. Recovers from storage if missing from Redis.
    """
    return await crawler_manager.get_status(job_info)

@router.get("/results/{crawl_id}")
async def download_crawl_results(
    background_tasks: BackgroundTasks,
    include: List[IncludeInArchive] = Query(..., description="Specify which components to include in the archive. Can be provided multiple times (e.g., ?include=dataset&include=request_queues)."),
    job_info: dict = Depends(get_job_or_recover)
):
    """
    Downloads a custom archive of a completed crawl job, including only the specified components.
    Recovers from storage if missing from Redis.
    """
    try:
        crawl_id = job_info['crawl_id']
        archive_path = await crawler_manager.get_results_archive(job_info, include)
        
        # Validate that the archive file was actually created before returning
        if not os.path.exists(archive_path):
            logger.error(
                f"Archive file was not created at expected path: {archive_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not generate results archive for crawl '{crawl_id}'. "
                f"The crawl data may have been cleaned up after archiving to GCS."
            )

        # Archive is now cached for performance, so we do NOT delete it immediately.
        # Cleanup should be handled by a separate retention policy/cron if needed.
        # background_tasks.add_task(lambda path: os.remove(path), archive_path)
        
        return FileResponse(path=archive_path, media_type='application/gzip', filename=f"{crawl_id}-results.tar.gz")
    except HTTPException as e:
        raise e
    except Exception as e:
        crawl_id = job_info.get('crawl_id', 'unknown')
        logger.error(f"Error generating results for crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate results archive.")

@router.post("/archive/{crawl_id}", response_model=ArchiveResponse)
async def archive_crawl_to_gcs(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    """
    Archives a finished crawl job to Google Cloud Storage.
    The job must be in 'finished' state.
    After successful upload, local files are cleaned up (except logs).
    """
    try:
        gcs_url = await crawler_manager.archive_crawl(job_info)
        return ArchiveResponse(
            message="Crawl archived successfully.",
            gcs_url=gcs_url
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error archiving crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during archiving.")

@router.get("/archive/{crawl_id}")
async def get_archived_crawl(crawl_id: str):
    """
    Placeholder for retrieving an archived crawl from GCS.
    Currently returns 501 Not Implemented.
    """
    return await crawler_manager.retrieve_archived_crawl(crawl_id)

@router.post("/reconcile-jobs")
async def reconcile_jobs():
    """
    Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
    marks them as failed, and corrects the global running jobs counter.
    Use this to fix counter drift where running_jobs > actual running jobs.
    """
    await crawler_manager.reconcile_jobs()
    return {"status": "reconciliation_complete"}
