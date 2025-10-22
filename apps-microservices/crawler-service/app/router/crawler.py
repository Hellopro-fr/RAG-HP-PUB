import os
import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from fastapi.responses import FileResponse

from app.core.crawler_manager import crawler_manager
from app.schemas.crawler import CrawlRequest, CrawlResponse, CrawlStatus, StopResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/start", response_model=CrawlResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_new_crawl(payload: CrawlRequest):
    """
    Starts or resumes a web crawling job. A job is uniquely identified by the `id` field.
    If a job with the same `id` is already running, an error will be returned.
    """
    try:
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
        
        # The user-provided `id` is now the stable and unique identifier for the crawl job.
        crawl_id = await crawler_manager.start_crawl(
            domain=payload.domain,
            start_url=str(payload.start_url),
            crawl_id=payload.id,
            callback_url=str(payload.callback_url),
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
async def stop_existing_crawl(crawl_id: str):
    """
    Stops a currently running crawl job.
    """
    success = await crawler_manager.stop_crawl(crawl_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Crawl job with ID '{crawl_id}' not found or already stopped.")
    return StopResponse(message="Stop signal sent to crawl job.", crawl_id=crawl_id)

@router.get("/status", response_model=Dict[str, CrawlStatus])
async def get_all_crawl_statuses():
    """
    Gets the status of all active crawl jobs on this instance.
    """
    return await crawler_manager.get_all_statuses()

@router.get("/status/{crawl_id}", response_model=CrawlStatus)
async def get_crawl_status(crawl_id: str):
    """
    Gets the detailed status of a specific crawl job.
    """
    status = await crawler_manager.get_status(crawl_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Crawl job not found.")
    return status

@router.get("/results/{crawl_id}")
async def download_crawl_results(crawl_id: str, background_tasks: BackgroundTasks):
    """
    Downloads the results of a completed crawl job as a ZIP archive.
    """
    try:
        archive_path = await crawler_manager.get_results_archive(crawl_id)
        if not archive_path:
            raise HTTPException(status_code=404, detail="Results not found or crawl is still in progress.")
        
        # Delete the temporary archive file after the response is sent
        background_tasks.add_task(lambda path: os.remove(path), archive_path)
        
        return FileResponse(path=archive_path, media_type='application/zip', filename=f"{crawl_id}-results.zip")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error generating results for crawl '{crawl_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not generate results archive.")