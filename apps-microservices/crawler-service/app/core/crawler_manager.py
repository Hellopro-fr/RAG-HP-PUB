import asyncio
import json
import logging
import os
import re
import tempfile
import shutil
from datetime import datetime
from typing import Dict, Optional, Any, List

import aiofiles
import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from common_utils.redis import cache_service
from app.schemas.crawler import CrawlStatus, IncludeInArchive, ReindexResponse

logger = logging.getLogger(__name__)

# A prefix for all crawl-related keys in Redis
CRAWL_JOB_PREFIX = "crawl_job:"
# The global counter for running jobs
CRAWL_RUNNING_COUNT_KEY = "crawl_jobs:running_count"

def _count_files_in_dir(path: str) -> int:
    """Safely counts files in a directory."""
    if not os.path.isdir(path):
        return 0
    try:
        return len([name for name in os.listdir(path) if os.path.isfile(os.path.join(path, name))])
    except OSError:
        return 0

class CrawlerManager:
    """
    Manages the lifecycle of crawler subprocesses.
    This class is now stateless, using Redis as the source of truth for job status.
    It maintains a small in-memory dict of active process handles for this specific replica.
    """
    def __init__(self):
        # This dictionary ONLY tracks processes running on THIS replica.
        # The global state is in Redis.
        self.local_processes: Dict[str, asyncio.subprocess.Process] = {}

    async def start_crawl(self, domain: str, start_url: str, crawl_id: str, callback_url: str, failure_callback_url: Optional[str], params: Dict[str, Any]) -> str:
        # Check if a crawl with this ID is already running on this instance
        if crawl_id in self.local_processes:
            proc = self.local_processes[crawl_id]
            if proc.returncode is None:
                logger.warning(f"Crawl job '{crawl_id}' is already running on this instance. Request rejected.")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A crawl job with ID '{crawl_id}' is already in progress on this service instance."
                )
            else:
                logger.info(f"Crawl job '{crawl_id}' found in local processes but is finished. Clearing for restart.")
                del self.local_processes[crawl_id]
        
        # Global concurrency check against Redis
        existing_job = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if existing_job and existing_job.get("status") == "running":
            logger.warning(f"Crawl job '{crawl_id}' is already running globally. Request rejected.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A crawl job with ID '{crawl_id}' is already in progress."
            )

        # Local concurrency check for this replica
        if len(self.local_processes) >= settings.MAX_CONCURRENT_CRAWLS:
            logger.warning(f"Max concurrent crawls for this replica reached. Rejecting job '{crawl_id}'.")
            detail_payload = {
                "error_code": "REPLICA_CAPACITY_EXCEEDED",
                "message": "This service instance is at its maximum capacity.",
                "replica_capacity": settings.MAX_CONCURRENT_CRAWLS,
                "rejected_request": {
                    "crawl_id": crawl_id,
                    "domain": domain
                }
            }
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail_payload
            )

        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
        try:
            os.makedirs(job_storage_path, exist_ok=True)
            logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
        except OSError as e:
            logger.error(f"Failed to create/access storage directory for crawl '{crawl_id}': {e}")
            raise HTTPException(status_code=500, detail="Could not initialize crawl environment.")

        command = [
            "node", settings.CRAWLER_EXECUTABLE_PATH,
            f"--domain={domain}", f"--site={start_url}", f"--id={crawl_id}",
            f"--storagePath={job_storage_path}", f"--callbackUrl={callback_url}",
        ]
        for key, value in params.items():
            if value is not None:
                command.append(f"--{key}={value}")

        logger.info(f"Starting crawl '{crawl_id}' with command: {' '.join(command)}")
        
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        self.local_processes[crawl_id] = process

        # Create the initial job state in Redis
        job_data = {
            "crawl_id": crawl_id, "status": "running", "domain": domain,
            "start_url": start_url, "start_time": datetime.utcnow(),
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": process.pid
        }
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_data)
        
        # Atomically increment the global running count
        await cache_service.increment_key(CRAWL_RUNNING_COUNT_KEY)
        
        asyncio.create_task(self._monitor_process(crawl_id, process))
        return crawl_id

    async def _send_success_webhook(self, job_info: dict):
        callback_url = job_info.get("callback_url")
        if not callback_url:
            return

        crawl_id = job_info["crawl_id"]
        payload_path = os.path.join(job_info["storage_path"], '_callback_payload.json')

        params = {}
        if os.path.exists(payload_path):
            try:
                async with aiofiles.open(payload_path, 'r') as f:
                    content = await f.read()
                    params = json.loads(content)
            except Exception as e:
                logger.error(f"Failed to read callback payload for '{crawl_id}'. Error: {e}", exc_info=True)
                # Fallback to a minimal payload indicating an error
                params = {"id_domaine": crawl_id, "isError": "PAYLOAD_READ_ERROR"}
        else:
            logger.warning(f"Callback payload file not found for '{crawl_id}'. Sending minimal callback.")
            params = {"id_domaine": crawl_id}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(str(callback_url), params=params, timeout=30.0)
                logger.info(f"Successfully sent success notification for '{crawl_id}'. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to send success notification for '{crawl_id}'. Error: {e}")

    async def _send_failure_webhook(self, url: str, crawl_id: str, domain: str, exit_code: int):
        params = {"crawl_id": crawl_id, "domain": domain, "exit_code": exit_code, "timestamp": datetime.utcnow().isoformat()}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30.0)
                logger.info(f"Successfully sent failure notification for '{crawl_id}'. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to send failure notification for '{crawl_id}'. Error: {e}")

    async def _monitor_process(self, crawl_id: str, process: asyncio.subprocess.Process):
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        
        job_info_initial = await cache_service.get_json(job_key)
        if not job_info_initial:
            logger.error(f"Cannot monitor process for '{crawl_id}': job info vanished immediately after start.")
            return

        log_path = os.path.join(job_info_initial['storage_path'], 'crawler.log')
        log_file_handle = await aiofiles.open(log_path, 'a')

        async def log_stream(stream, prefix):
            try:
                async for line in stream:
                    await log_file_handle.write(f"[{prefix}] {line.decode('utf-8', errors='ignore')}")
            except Exception as e:
                logger.error(f"Error in log stream for crawl '{crawl_id}': {e}")

        stdout_task = asyncio.create_task(log_stream(process.stdout, "stdout"))
        stderr_task = asyncio.create_task(log_stream(process.stderr, "stderr"))

        try:
            # --- Heartbeat Loop ---
            while process.returncode is None:
                await asyncio.sleep(60)  # Heartbeat interval

                if process.returncode is not None:
                    break

                job_info = await cache_service.get_json(job_key)
                if job_info and job_info.get("status") == "running":
                    job_info["last_heartbeat"] = datetime.utcnow()
                    await cache_service.set_json(job_key, job_info)
                    logger.debug(f"Heartbeat sent for running crawl '{crawl_id}'.")
                elif not job_info:
                    logger.warning(f"Heartbeat for '{crawl_id}' skipped: job key disappeared from Redis mid-run. It may be recovered later.")

            await process.wait()
            await asyncio.gather(stdout_task, stderr_task)

        finally:
            await log_file_handle.close()

        # --- Finalization Logic (after process has finished) ---
        await cache_service.decrement_key(CRAWL_RUNNING_COUNT_KEY)
        
        job_info = await cache_service.get_json(job_key)
        if job_info:
            exit_code = process.returncode
            is_success = (exit_code == 2)
            
            final_status = "finished" if is_success else "failed"
            job_info["status"] = final_status
            job_info["pid"] = None
            if "last_heartbeat" in job_info:
                del job_info["last_heartbeat"]  # Clean up heartbeat field
            await cache_service.set_json(job_key, job_info)
            logger.info(f"Crawl '{crawl_id}' finished with exit code {exit_code}. Status updated in Redis and counter decremented.")
            
            # --- START: Create Completion Marker ---
            marker_path = os.path.join(job_info['storage_path'], '_completion_marker.json')
            marker_data = {
                "final_status": final_status,
                "exit_code": exit_code,
                "end_timestamp": datetime.utcnow().isoformat()
            }
            try:
                async with aiofiles.open(marker_path, 'w') as f:
                    await f.write(json.dumps(marker_data, indent=2))
                logger.info(f"Created completion marker for crawl '{crawl_id}'.")
            except Exception as e:
                logger.error(f"Failed to write completion marker for '{crawl_id}': {e}", exc_info=True)
            # --- END: Create Completion Marker ---

            # --- WEBHOOK LOGIC ---
            if is_success and job_info.get("callback_url"):
                logger.info(f"Crawl '{crawl_id}' succeeded. Triggering success webhook.")
                asyncio.create_task(self._send_success_webhook(job_info))
            elif not is_success and job_info.get("failure_callback_url"):
                logger.info(f"Crawl '{crawl_id}' failed. Triggering failure webhook.")
                asyncio.create_task(self._send_failure_webhook(str(job_info["failure_callback_url"]), crawl_id, job_info["domain"], exit_code))
        
        if crawl_id in self.local_processes:
            del self.local_processes[crawl_id]

    async def stop_crawl(self, job_info: dict) -> bool:
        crawl_id = job_info['crawl_id']
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        
        if job_info.get("status") != "running":
            logger.warning(f"Attempted to stop crawl '{crawl_id}' which is not in a 'running' state (status: {job_info.get('status')}).")
            return False
        
        stopper_dir = os.path.join(job_info["storage_path"], 'stopper')
        os.makedirs(stopper_dir, exist_ok=True)
        stopper_file = os.path.join(stopper_dir, f"{job_info['domain']}.txt")
        
        async with aiofiles.open(stopper_file, 'w') as f:
            await f.write(f"Stopped by API at {datetime.utcnow().isoformat()}")

        job_info["status"] = "stopping"
        await cache_service.set_json(job_key, job_info)
        logger.info(f"Stop signal sent to crawl '{crawl_id}'. Status updated in Redis.")
        return True

    async def get_all_statuses(self) -> Dict[str, CrawlStatus]:
        all_job_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
        statuses = {}
        for key in all_job_keys:
            crawl_id = key.replace(CRAWL_JOB_PREFIX, "")
            # This uses the public get_status which now needs job_info, so we get it first.
            job_info = await cache_service.get_json(key)
            if job_info:
                status_data = await self.get_status(job_info)
                if status_data:
                    statuses[crawl_id] = status_data
        return statuses

    async def get_status(self, job_info: dict) -> CrawlStatus:
        crawl_id = job_info['crawl_id']

        # --- START: ENHANCED STATS CALCULATION ---
        storage_path = job_info["storage_path"]
        domain = job_info["domain"]
        crawlee_storage_base = os.path.join(storage_path, 'storage', 'datasets')

        urls_crawled, last_url_time = 0, None
        dataset_path = os.path.join(crawlee_storage_base, domain)
        error_dataset_path = os.path.join(crawlee_storage_base, f"error-{domain}")
        nfr_dataset_path = os.path.join(crawlee_storage_base, f"nfr-{domain}")

        error_urls_crawled = _count_files_in_dir(error_dataset_path)
        nfr_urls_crawled = _count_files_in_dir(nfr_dataset_path)
        
        if os.path.isdir(dataset_path):
            try:
                files = [os.path.join(dataset_path, f) for f in os.listdir(dataset_path) if os.path.isfile(os.path.join(dataset_path, f))]
                urls_crawled = len(files)
                if files:
                    latest_file = max(files, key=os.path.getmtime)
                    last_url_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
            except Exception as e:
                logger.warning(f"Could not read dataset info for '{crawl_id}': {e}")
        
        return CrawlStatus(
            crawl_id=crawl_id,
            status=job_info["status"], 
            domain=job_info["domain"],
            start_url=job_info["start_url"], 
            start_time=job_info["start_time"],
            urls_crawled=urls_crawled,
            error_urls_crawled=error_urls_crawled,
            nfr_urls_crawled=nfr_urls_crawled,
            last_activity=last_url_time,
            last_heartbeat=job_info.get("last_heartbeat")
        )
        # --- END: ENHANCED STATS CALCULATION ---
        
    async def get_results_archive(self, job_info: dict, include: List[IncludeInArchive]) -> str:
        crawl_id = job_info['crawl_id']
        
        if job_info["status"] == "running":
             raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
        
        job_storage_path = job_info["storage_path"]
        domain = job_info["domain"]
        
        # Use a temporary directory to stage the files for archiving
        with tempfile.TemporaryDirectory() as staging_dir:
            # This is the root inside the staging area that will mirror the on-disk structure
            archive_content_root = os.path.join(staging_dir, "storage")
            os.makedirs(archive_content_root, exist_ok=True)
            
            # Map the user's request to the actual folder names
            path_mappings = {
                IncludeInArchive.DATASET: os.path.join("datasets", domain),
                IncludeInArchive.DATASET_NFR: os.path.join("datasets", f"nfr-{domain}"),
                IncludeInArchive.DATASET_ERROR: os.path.join("datasets", f"error-{domain}"),
                IncludeInArchive.REQUEST_QUEUES: os.path.join("request_queues", domain),
                IncludeInArchive.REQUEST_URLS: os.path.join("request_urls", domain),
                IncludeInArchive.MISCELLANEOUS: os.path.join("miscellaneous", domain),
            }

            crawlee_storage_base = os.path.join(job_storage_path, 'storage')
            
            copied_anything = False
            for item in set(include): # Use set to avoid processing duplicate requests
                relative_path = path_mappings.get(item)
                if not relative_path: continue
                
                source_path = os.path.join(crawlee_storage_base, relative_path)
                
                if os.path.exists(source_path):
                    destination_path = os.path.join(archive_content_root, relative_path)
                    # Ensure parent directories exist in the staging area
                    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                    shutil.copytree(source_path, destination_path)
                    copied_anything = True
            
            if not copied_anything:
                raise HTTPException(status_code=404, detail="None of the requested components were found for this crawl job.")

            # Create the final archive from the contents of the staging directory
            archive_base_path = os.path.join(settings.CRAWLER_STORAGE_PATH, "archives")
            os.makedirs(archive_base_path, exist_ok=True)
            archive_name = os.path.join(archive_base_path, f"{crawl_id}-results")
            
            # This will create an archive containing a single 'storage' folder at its root
            final_archive_path = shutil.make_archive(
                base_name=archive_name,
                format='gztar',
                root_dir=staging_dir
            )
            
            return final_archive_path
        
    async def reindex_storage(self) -> ReindexResponse:
        """Scans storage for orphaned jobs and re-indexes them in Redis."""
        logger.info("Starting storage re-indexing process.")
        
        summary = {"scanned_directories": 0, "reindexed_jobs": 0, "already_indexed": 0, "errors": 0}
        
        try:
            redis_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
            redis_key_set = set(redis_keys)
            
            storage_dirs = [d for d in os.listdir(settings.CRAWLER_STORAGE_PATH) if os.path.isdir(os.path.join(settings.CRAWLER_STORAGE_PATH, d))]
            summary["scanned_directories"] = len(storage_dirs)

            for crawl_id in storage_dirs:
                job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
                if job_key in redis_key_set:
                    summary["already_indexed"] += 1
                    continue

                # This is an orphaned job, let's re-index it.
                logger.warning(f"Found orphaned crawl job on disk: '{crawl_id}'. Re-indexing.")
                job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
                marker_path = os.path.join(job_storage_path, '_completion_marker.json')
                
                final_status = "failed" # Default status for orphans
                
                if os.path.exists(marker_path):
                    try:
                        with open(marker_path, 'r') as f:
                            marker_data = json.load(f)
                        final_status = marker_data.get("final_status", "failed")
                    except Exception:
                        logger.error(f"Could not parse completion marker for '{crawl_id}'. Defaulting to 'failed'.")
                else:
                    # No marker means the job was killed mid-run
                    final_status = "failed"
                
                # Reconstruct metadata by parsing the log file (best effort)
                domain, start_url = "unknown", "http://unknown.com"
                log_path = os.path.join(job_storage_path, 'crawler.log')
                if os.path.exists(log_path):
                    with open(log_path, 'r', errors='ignore') as f:
                        for line in f:
                            if '"domain":' in line:
                                match = re.search(r'"domain":\s*"([^"]+)"', line)
                                if match: domain = match.group(1)
                            if '"site":' in line:
                                match = re.search(r'"site":\s*"([^"]+)"', line)
                                if match: start_url = match.group(1)
                            if domain != "unknown" and start_url != "http://unknown.com":
                                break
                
                reindexed_data = {
                    "crawl_id": crawl_id, "status": final_status, "domain": domain,
                    "start_url": start_url, "start_time": datetime.fromtimestamp(os.path.getctime(job_storage_path)),
                    "storage_path": job_storage_path,
                    "failure_callback_url": None, "pid": None
                }
                
                await cache_service.set_json(job_key, reindexed_data)
                summary["reindexed_jobs"] += 1
        
        except Exception as e:
            summary["errors"] += 1
            logger.error(f"An error occurred during re-indexing: {e}", exc_info=True)

        logger.info(f"Re-indexing complete: {summary}")
        return ReindexResponse(**summary)

    async def _cleanup_running_job(self, crawl_id: str, process: asyncio.subprocess.Process):
        """Helper function to handle the cleanup of a single running job during shutdown."""
        logger.info(f"Cleaning up job '{crawl_id}' due to service shutdown.")
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"

        try:
            # 1. Terminate the subprocess
            process.terminate()
            
            # 2. Update state in Redis
            job_info = await cache_service.get_json(job_key)
            if job_info and job_info.get("status") == "running":
                job_info["status"] = "failed"
                job_info["shutdown_reason"] = "Service instance terminated"
                if "last_heartbeat" in job_info:
                    del job_info["last_heartbeat"]
                
                await cache_service.set_json(job_key, job_info)
                logger.info(f"Marked job '{crawl_id}' as 'failed' in Redis.")

                # 3. Decrement the global running counter
                await cache_service.decrement_key(CRAWL_RUNNING_COUNT_KEY)
                logger.info(f"Decremented global running counter for job '{crawl_id}'.")

                # 4. Send failure webhook
                if job_info.get("failure_callback_url"):
                    logger.info(f"Sending failure webhook for job '{crawl_id}'.")
                    # Use a special exit code like -1 for shutdown
                    await self._send_failure_webhook(
                        str(job_info["failure_callback_url"]),
                        crawl_id,
                        job_info["domain"],
                        -1  
                    )
            else:
                 logger.warning(f"Could not find job '{crawl_id}' in Redis during shutdown or it was not in 'running' state.")

        except Exception as e:
            logger.error(f"Error during graceful shutdown for job '{crawl_id}': {e}", exc_info=True)

    async def shutdown(self):
        """Gracefully shut down all locally running crawlers on this replica."""
        if not self.local_processes:
            return

        logger.info(f"Graceful shutdown initiated. Terminating {len(self.local_processes)} active local crawl(s) on this replica.")
        
        shutdown_tasks = [
            self._cleanup_running_job(crawl_id, process)
            for crawl_id, process in self.local_processes.items()
            if process.returncode is None
        ]

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks)

        self.local_processes.clear()
        logger.info("Graceful shutdown complete for this replica.")

crawler_manager = CrawlerManager()