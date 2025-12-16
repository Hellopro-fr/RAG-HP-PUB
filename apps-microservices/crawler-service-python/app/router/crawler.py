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

CRAWL_MAX_GLOBAL_KEY = "crawl_jobs:max_global_crawls"

# --- SANDBOX LOGIC ---
def _sandbox_id_in(crawl_id: str) -> str:
    """Redirects 4776 input to 4776_python internally."""
    if crawl_id == "4776":
        return "4776_python"
    return crawl_id

def _sandbox_id_out(data: any) -> any:
    """
    Recursively replaces '4776_python' with '4776' in the output data 
    to hide the implementation detail from the client.
    """
    if isinstance(data, str):
        if data == "4776_python":
            return "4776"
        # Also clean up paths/URLs if they leak the ID
        return data.replace("4776_python", "4776")
    elif isinstance(data, dict):
        return {k: _sandbox_id_out(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sandbox_id_out(item) for item in data]
    return data
# ---------------------

async def get_job_or_recover(crawl_id: str) -> dict:
    # 1. Input Rewrite
    crawl_id = _sandbox_id_in(crawl_id)
    
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
    final_status = "failed" 

    try:
        if os.path.exists(marker_path):
            async with aiofiles.open(marker_path, 'r') as f:
                content = await f.read()
                marker_data = json.loads(content)
            final_status = marker_data.get("final_status", "failed")
    except Exception:
        logger.error(f"Could not parse completion marker for '{crawl_id}'. Defaulting to 'failed'.")

    # Reconstruct metadata by parsing the log file (best effort)
    domain, start_url = "unknown", "http://unknown.com"
    log_path = os.path.join(job_storage_path, 'crawler.log')
    if os.path.exists(log_path):
        try:
            async with aiofiles.open(log_path, 'r', errors='ignore') as f:
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

# ... reindex_storage and get_capacity omitted (unchanged) ...

@router.post("/reindex-storage", response_model=ReindexResponse)
async def reindex_storage():
    try:
        summary = await crawler_manager.reindex_storage()
        return summary
    except Exception as e:
        logger.error(f"Failed during storage re-indexing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during re-indexing.")

@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity():
    try:
        if not cache_service.redis_client:
            raise HTTPException(status_code=503, detail="Redis connection not available.")

        running_jobs_raw = await cache_service.get_key(CRAWL_RUNNING_COUNT_KEY)
        running_jobs = int(running_jobs_raw) if running_jobs_raw else 0
        
        max_global_raw = await cache_service.get_key(CRAWL_MAX_GLOBAL_KEY)
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
    try:
        # 1. Input Rewrite
        actual_crawl_id = _sandbox_id_in(payload.id)

        params = {
            "typecrawling": payload.type_crawling,
            "method": payload.method,
            "dropdata": payload.drop_data,
            "skipquestionmark": payload.skip_question_mark,
            "skipdiez": payload.skip_diez,
            "tokeep": ";".join(payload.to_keep) if payload.to_keep else None,
            "toremove": ";".join(payload.to_remove) if payload.to_remove else None,
            "proxyapify": payload.proxy_apify,
            "bypassquestionmark": payload.bypass_question_mark,
            "bypassdiez": payload.bypass_diez,
            "breaklimit": payload.break_limit,
            "percrawl": payload.per_crawl,
            "perminute": payload.per_minute,
        }
        
        crawl_id = await crawler_manager.start_crawl(
            domain=payload.domain,
            start_url=str(payload.start_url),
            crawl_id=actual_crawl_id, # Use REWRITTEN ID
            callback_url=str(payload.callback_url),
            failure_callback_url=str(payload.failure_callback_url) if payload.failure_callback_url else None,
            params=params
        )
        
        # 2. Output Sanitize
        response_model = CrawlResponse(
            message="Crawl job accepted and started.",
            crawl_id=crawl_id
        )
        return _sandbox_id_out(response_model.dict()) # Return as dict to bypass Pydantic re-validation or use construct
        
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Failed to start crawl for domain {payload.domain}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while starting the crawl.")

@router.post("/stop/{crawl_id}", response_model=StopResponse)
async def stop_existing_crawl(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    # Input is already handled by dependency
    input_id = crawl_id # Original ID from URL
    success = await crawler_manager.stop_crawl(job_info)
    if not success:
        raise HTTPException(status_code=409, detail=f"Crawl job with ID '{input_id}' not found or not in a running state.")
    
    # 2. Output Sanitize
    return _sandbox_id_out(StopResponse(message="Stop signal sent to crawl job.", crawl_id=input_id).dict())

@router.get("/status", response_model=Dict[str, CrawlStatus])
async def get_all_crawl_statuses():
    all_statuses = await crawler_manager.get_all_statuses()
    # 2. Output Sanitize all
    return _sandbox_id_out(all_statuses) # Pydantic will serialize this dict map

@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(job_info: dict = Depends(get_job_or_recover)):
    # Input ID is handled by Depends
    status_data = await crawler_manager.get_status(job_info)
    # 2. Output Sanitize
    return _sandbox_id_out(status_data) # Returns dict, Pydantic compatible

@router.get("/results/{crawl_id}")
async def download_crawl_results(
    background_tasks: BackgroundTasks,
    include: List[IncludeInArchive] = Query(..., description="Specify components"),
    job_info: dict = Depends(get_job_or_recover)
):
    try:
        crawl_id = job_info['crawl_id'] # This is the REAL (rewritten) ID
        archive_path = await crawler_manager.get_results_archive(job_info, include)
        
        if not os.path.exists(archive_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Could not generate results archive for crawl '{crawl_id}'."
            )

        # We return the file. The filename should probably be sanitized to the original ID ?
        original_id = _sandbox_id_out(crawl_id)
        return FileResponse(path=archive_path, media_type='application/gzip', filename=f"{original_id}-results.tar.gz")
    except HTTPException as e:
        raise e
    except Exception as e:
        crawl_id = job_info.get('crawl_id', 'unknown')
        logger.error(f"Error generating results for crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate results archive.")

@router.post("/archive/{crawl_id}", response_model=ArchiveResponse)
async def archive_crawl_to_gcs(crawl_id: str, job_info: dict = Depends(get_job_or_recover)):
    try:
        gcs_url = await crawler_manager.archive_crawl(job_info)
        # Note: GCS URL might contain the REAL ID. We sanitize it too.
        sanitized_url = _sandbox_id_out(gcs_url)
        return ArchiveResponse(
            message="Crawl archived successfully.",
            gcs_url=sanitized_url
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error archiving crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred during archiving.")

@router.get("/archive/{crawl_id}")
async def get_archived_crawl(crawl_id: str):
    # Retrieve logic might need rewrite
    # Assuming retrieve_archived_crawl takes ID.
    real_id = _sandbox_id_in(crawl_id)
    result = await crawler_manager.retrieve_archived_crawl(real_id)
    return _sandbox_id_out(result)
