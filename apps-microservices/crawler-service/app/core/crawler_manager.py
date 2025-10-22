import asyncio
import logging
import os
import uuid
import shutil
from datetime import datetime
from typing import Dict, Optional, Any

import aiofiles
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.crawler import CrawlStatus

logger = logging.getLogger(__name__)

class CrawlerManager:
    """
    Manages the lifecycle of crawler subprocesses.
    This class is designed as a singleton to maintain state across the application.
    It follows the Single Responsibility Principle by focusing solely on managing crawl jobs.
    """
    def __init__(self):
        self.active_crawls: Dict[str, Dict[str, Any]] = {}

    async def start_crawl(self, domain: str, start_url: str, crawl_id: str, callback_url: str, params: Dict[str, Any]) -> str:
        # Check if a crawl with this ID is already running on this instance
        if crawl_id in self.active_crawls:
            proc = self.active_crawls[crawl_id].get("process")
            # If the process object exists and its return code is None, it's still running.
            if proc and proc.returncode is None:
                logger.warning(f"Crawl job '{crawl_id}' is already running on this instance. Request rejected.")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A crawl job with ID '{crawl_id}' is already in progress on this service instance."
                )
            else:
                # The job was in the active list, but the process has finished. It's safe to clear it and restart.
                logger.info(f"Crawl job '{crawl_id}' found in active list but process is finished. Clearing for restart.")
                del self.active_crawls[crawl_id]

        if len(self.active_crawls) >= settings.MAX_CONCURRENT_CRAWLS:
            logger.warning("Max concurrent crawls reached. Request rejected.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Service is at maximum capacity with {settings.MAX_CONCURRENT_CRAWLS} active crawls. Please try again later."
            )

        # The crawl_id is now the stable, user-provided ID. No more UUIDs.
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
        
        try:
            os.makedirs(job_storage_path, exist_ok=True)
            logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
        except OSError as e:
            logger.error(f"Failed to create/access storage directory for crawl '{crawl_id}': {e}")
            raise HTTPException(status_code=500, detail="Could not initialize crawl environment.")

        command = [
            "node",
            settings.CRAWLER_EXECUTABLE_PATH,
            f"--domain={domain}",
            f"--site={start_url}",
            f"--id={crawl_id}",
            f"--storagePath={job_storage_path}",
            f"--callbackUrl={callback_url}",
        ]
        # Add optional parameters
        for key, value in params.items():
            if value is not None:
                command.append(f"--{key}={value}")

        logger.info(f"Starting crawl '{crawl_id}' with command: {' '.join(command)}")

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        self.active_crawls[crawl_id] = {
            "process": process,
            "domain": domain,
            "start_url": start_url,
            "start_time": datetime.utcnow(),
            "storage_path": job_storage_path,
            "status": "running"
        }
        
        # Start a background task to log stdout/stderr
        asyncio.create_task(self._log_output(crawl_id, process))

        return crawl_id

    async def _log_output(self, crawl_id: str, process: asyncio.subprocess.Process):
        """Logs stdout and stderr of a crawler subprocess."""
        log_path = os.path.join(self.active_crawls[crawl_id]['storage_path'], 'crawler.log')
        try:
            async with aiofiles.open(log_path, 'a') as log_file:
                # We can read both streams concurrently
                async def log_stream(stream, prefix):
                    async for line in stream:
                        decoded_line = line.decode('utf-8', errors='ignore').strip()
                        await log_file.write(f"[{prefix}] {decoded_line}\n")
                
                await asyncio.gather(
                    log_stream(process.stdout, "stdout"),
                    log_stream(process.stderr, "stderr")
                )
        except Exception as e:
            # If the crawl job was removed (e.g., shutdown), this might fail.
            if crawl_id not in self.active_crawls:
                logger.warning(f"Logging for crawl '{crawl_id}' stopped as job was removed.")
            else:
                logger.error(f"Error logging output for crawl '{crawl_id}': {e}")
        
        # Once process finishes, update its status
        await process.wait()
        if crawl_id in self.active_crawls:
             self.active_crawls[crawl_id]["status"] = "finished" if process.returncode == 2 else "failed"
             logger.info(f"Crawl '{crawl_id}' finished with exit code {process.returncode}.")


    async def stop_crawl(self, crawl_id: str) -> bool:
        if crawl_id not in self.active_crawls:
            return False
        
        job_info = self.active_crawls[crawl_id]
        storage_path = job_info["storage_path"]
        domain = job_info["domain"]

        # Use the crawler's built-in stop mechanism
        stopper_dir = os.path.join(storage_path, 'storage', 'stopper')
        os.makedirs(stopper_dir, exist_ok=True)
        stopper_file = os.path.join(stopper_dir, f"{domain}.txt")

        async with aiofiles.open(stopper_file, 'w') as f:
            await f.write(f"Stopped by API at {datetime.utcnow().isoformat()}")

        job_info["status"] = "stopping"
        logger.info(f"Stop signal sent to crawl '{crawl_id}' for domain '{domain}'.")
        return True

    async def get_all_statuses(self) -> Dict[str, CrawlStatus]:
        # Clean up finished/failed jobs before reporting
        finished_jobs = [cid for cid, info in self.active_crawls.items() if info["status"] in ["finished", "failed"]]
        for cid in finished_jobs:
            # In a real scenario, you might move finished jobs to a history DB
            # For simplicity, we just remove them after a while or upon query
            pass

        return {cid: await self.get_status(cid) for cid in self.active_crawls}

    async def get_status(self, crawl_id: str) -> Optional[CrawlStatus]:
        job_info = self.active_crawls.get(crawl_id)
        
        # If not in memory, check storage for a completed job
        if not job_info:
            job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)
            if not os.path.exists(job_storage_path):
                return None
            # This is a placeholder for a more robust status tracking system (e.g., a DB)
            # For now, we just know it exists but isn't "running"
            return CrawlStatus(
                crawl_id=crawl_id,
                status="unknown (not active on this instance)",
                domain="N/A", start_url="N/A", start_time=datetime.min, # type: ignore
                urls_crawled=0, last_activity=None
            )

        storage_path = job_info["storage_path"]
        domain = job_info["domain"]
        
        # Check if process is still running
        if job_info["process"].returncode is not None and job_info["status"] == "running":
            job_info["status"] = "finished" if job_info["process"].returncode == 2 else "failed"

        # Gather stats from the filesystem
        urls_crawled = 0
        last_url_time = None
        
        dataset_path = os.path.join(storage_path, 'storage', 'datasets', domain)
        if os.path.exists(dataset_path):
            try:
                # Count files which represent crawled pages
                files = [os.path.join(dataset_path, f) for f in os.listdir(dataset_path)]
                urls_crawled = len(files)
                if files:
                    latest_file = max(files, key=os.path.getmtime)
                    last_url_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
            except Exception as e:
                logger.warning(f"Could not read dataset info for '{crawl_id}': {e}")


        return CrawlStatus(
            crawl_id=crawl_id,
            status=job_info["status"],
            domain=domain,
            start_url=job_info["start_url"],
            start_time=job_info["start_time"],
            urls_crawled=urls_crawled,
            last_activity=last_url_time
        )
        
    async def get_results_archive(self, crawl_id: str) -> Optional[str]:
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)

        # If job is active, check its status.
        if crawl_id in self.active_crawls:
            job_info = self.active_crawls[crawl_id]
            if job_info["status"] == "running":
                 raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")
        
        if not os.path.exists(job_storage_path):
             raise HTTPException(status_code=404, detail="Crawl ID not found.")

        # Path to the data we want to zip, accounting for Crawlee's default 'storage' subdirectory
        datasets_root_path = os.path.join(job_storage_path, 'storage', 'datasets')
        if not os.path.exists(datasets_root_path) or not os.listdir(datasets_root_path):
            raise HTTPException(status_code=404, detail="No dataset found for this crawl.")

        domain_folder = [d for d in os.listdir(datasets_root_path) if os.path.isdir(os.path.join(datasets_root_path, d))][0]
        data_path = os.path.join(datasets_root_path, domain_folder)

        if not os.path.exists(data_path):
            raise HTTPException(status_code=404, detail="No result data found for this crawl.")

        # Create a zip file
        archive_path = os.path.join(settings.CRAWLER_STORAGE_PATH, "archives")
        os.makedirs(archive_path, exist_ok=True)
        archive_name = os.path.join(archive_path, f"{crawl_id}-results")
        
        shutil.make_archive(archive_name, 'zip', data_path)
        
        return f"{archive_name}.zip"

    async def shutdown(self):
        """Gracefully stop all running crawlers."""
        if not self.active_crawls:
            return
        
        logger.info(f"Sending stop signal to {len(self.active_crawls)} active crawls.")
        # Create stop tasks
        stop_tasks = [self.stop_crawl(crawl_id) for crawl_id in list(self.active_crawls.keys())]
        await asyncio.gather(*stop_tasks)
        
        # Allow some grace time for crawlers to stop
        await asyncio.sleep(5)

        # Terminate any remaining processes
        for crawl_id, job_info in list(self.active_crawls.items()):
            process = job_info["process"]
            if process.returncode is None:
                logger.warning(f"Crawl '{crawl_id}' did not stop gracefully. Terminating process.")
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.error(f"Failed to terminate process for crawl '{crawl_id}'. Killing.")
                    process.kill()
                except Exception as e:
                    logger.error(f"Error terminating process for '{crawl_id}': {e}")
        
        self.active_crawls.clear()


# Create a single instance to be used throughout the application
crawler_manager = CrawlerManager()