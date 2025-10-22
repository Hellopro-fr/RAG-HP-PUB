import asyncio
import logging
import os
import shutil
from datetime import datetime
from typing import Dict, Optional, Any

import aiofiles
import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis_service import redis_service
from app.schemas.crawler import CrawlStatus

logger = logging.getLogger(__name__)

# A prefix for all crawl-related keys in Redis
CRAWL_JOB_PREFIX = "crawl_job:"

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
        # Global concurrency check against Redis
        existing_job = await redis_service.get_data(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if existing_job and existing_job.get("status") == "running":
            logger.warning(f"Crawl job '{crawl_id}' is already running globally. Request rejected.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A crawl job with ID '{crawl_id}' is already in progress."
            )

        # Local concurrency check for this replica
        if len(self.local_processes) >= settings.MAX_CONCURRENT_CRAWLS:
            logger.warning("Max concurrent crawls for this replica reached. Request rejected.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"This service instance is at its maximum capacity with {settings.MAX_CONCURRENT_CRAWLS} active crawls."
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
            "failure_callback_url": failure_callback_url, "pid": process.pid
        }
        await redis_service.set_data(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_data)
        
        asyncio.create_task(self._monitor_process(crawl_id, process))
        return crawl_id

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
        job_info = await redis_service.get_data(job_key)
        if not job_info: return

        log_path = os.path.join(job_info['storage_path'], 'crawler.log')
        try:
            async with aiofiles.open(log_path, 'a') as log_file:
                async def log_stream(stream, prefix):
                    async for line in stream:
                        await log_file.write(f"[{prefix}] {line.decode('utf-8', errors='ignore')}")
                await asyncio.gather(log_stream(process.stdout, "stdout"), log_stream(process.stderr, "stderr"))
        except Exception as e:
            logger.error(f"Error logging output for crawl '{crawl_id}': {e}")
        
        await process.wait()
        
        job_info = await redis_service.get_data(job_key)
        if job_info:
            exit_code = process.returncode
            is_success = (exit_code == 2)
            
            job_info["status"] = "finished" if is_success else "failed"
            job_info["pid"] = None # Process is no longer running
            await redis_service.set_data(job_key, job_info)
            logger.info(f"Crawl '{crawl_id}' finished with exit code {exit_code}. Status updated in Redis.")

            if not is_success and job_info.get("failure_callback_url"):
                logger.info(f"Crawl '{crawl_id}' failed. Triggering failure webhook.")
                asyncio.create_task(self._send_failure_webhook(str(job_info["failure_callback_url"]), crawl_id, job_info["domain"], exit_code))
        
        if crawl_id in self.local_processes:
            del self.local_processes[crawl_id]

    async def stop_crawl(self, crawl_id: str) -> bool:
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        job_info = await redis_service.get_data(job_key)
        
        if not job_info or job_info.get("status") != "running":
            return False
        
        stopper_dir = os.path.join(job_info["storage_path"], 'storage', 'stopper')
        os.makedirs(stopper_dir, exist_ok=True)
        stopper_file = os.path.join(stopper_dir, f"{job_info['domain']}.txt")
        
        async with aiofiles.open(stopper_file, 'w') as f:
            await f.write(f"Stopped by API at {datetime.utcnow().isoformat()}")

        job_info["status"] = "stopping"
        await redis_service.set_data(job_key, job_info)
        logger.info(f"Stop signal sent to crawl '{crawl_id}'. Status updated in Redis.")
        return True

    async def get_all_statuses(self) -> Dict[str, CrawlStatus]:
        all_job_keys = await redis_service.get_all_keys_by_prefix(CRAWL_JOB_PREFIX)
        statuses = {}
        for key in all_job_keys:
            crawl_id = key.replace(CRAWL_JOB_PREFIX, "")
            status_data = await self.get_status(crawl_id)
            if status_data:
                statuses[crawl_id] = status_data
        return statuses

    async def get_status(self, crawl_id: str) -> Optional[CrawlStatus]:
        job_info = await redis_service.get_data(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if not job_info: return None

        urls_crawled, last_url_time = 0, None
        dataset_path = os.path.join(job_info["storage_path"], 'storage', 'datasets', job_info["domain"])
        if os.path.exists(dataset_path):
            try:
                files = [os.path.join(dataset_path, f) for f in os.listdir(dataset_path)]
                urls_crawled = len(files)
                if files:
                    latest_file = max(files, key=os.path.getmtime)
                    last_url_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
            except Exception as e:
                logger.warning(f"Could not read dataset info for '{crawl_id}': {e}")
        
        return CrawlStatus(
            crawl_id=crawl_id,
            status=job_info["status"], domain=job_info["domain"],
            start_url=job_info["start_url"], start_time=job_info["start_time"],
            urls_crawled=urls_crawled, last_activity=last_url_time
        )
        
    async def get_results_archive(self, crawl_id: str) -> Optional[str]:
        job_info = await redis_service.get_data(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if not job_info:
             raise HTTPException(status_code=404, detail="Crawl ID not found.")
        
        if job_info["status"] == "running":
             raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
        
        job_storage_path = job_info["storage_path"]
        datasets_root_path = os.path.join(job_storage_path, 'storage', 'datasets')
        if not os.path.exists(datasets_root_path) or not os.listdir(datasets_root_path):
            raise HTTPException(status_code=404, detail="No dataset found for this crawl.")

        domain_folder = [d for d in os.listdir(datasets_root_path) if os.path.isdir(os.path.join(datasets_root_path, d))][0]
        data_path = os.path.join(datasets_root_path, domain_folder)

        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail="No result data found for this crawl.")

        archive_path = os.path.join(settings.CRAWLER_STORAGE_PATH, "archives")
        os.makedirs(archive_path, exist_ok=True)
        archive_name = os.path.join(archive_path, f"{crawl_id}-results")
        
        shutil.make_archive(archive_name, 'gztar', data_path)
        return f"{archive_name}.tar.gz"

    async def shutdown(self):
        """Gracefully stop all locally running crawlers."""
        if not self.local_processes: return
        
        logger.info(f"Terminating {len(self.local_processes)} active local crawls on this replica.")
        for crawl_id, process in list(self.local_processes.items()):
            if process.returncode is None:
                try: process.terminate()
                except Exception as e: logger.error(f"Error terminating process for '{crawl_id}': {e}")
        
        self.local_processes.clear()

crawler_manager = CrawlerManager()