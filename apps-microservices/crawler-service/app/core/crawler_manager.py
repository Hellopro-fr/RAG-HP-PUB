import asyncio
import json
import logging
import os
import re
import signal
import tempfile
import shutil
import threading
import time
import anyio
import tarfile
import hashlib
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple

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
# The dynamic global max crawls key in Redis
CRAWL_MAX_GLOBAL_KEY = "crawl_jobs:max_global_crawls"

CRAWL_UPDATES_CHANNEL = "crawl_updates"
STALE_JOB_THRESHOLD_SECONDS = 180  # 3 minutes without heartbeat = dead

def _count_files_in_dir(path: str) -> int:
    """Safely counts files in a directory, excluding Crawlee metadata."""
    if not os.path.isdir(path):
        return 0
    try:
        count = 0
        for name in os.listdir(path):
            # Exclude Crawlee metadata files
            if name.startswith('__') and name.endswith('__.json'):
                continue
            if os.path.isfile(os.path.join(path, name)):
                count += 1
        return count
    except OSError:
        return 0

# Thread-safe locks for concurrent archive generation (keyed by archive path)
_archive_locks: Dict[str, threading.Lock] = {}
_archive_locks_guard = threading.Lock()

class CrawlerManager:
    """
    Manages the lifecycle of crawler subprocesses.
    This class is now stateless, using Redis as the source of truth for job status.
    It maintains a small in-memory dict of active process handles for this specific replica.
    """

    # Maps internal error codes to human-readable French messages
    # for storage in the database column `message_erreur_crawling` (VARCHAR 250).
    ERROR_MESSAGE_MAP = {
        "OOM_MAX_RESTARTS": "Out Of Memory",
        "OOM_RELAUNCH": "Out Of Memory",
        "limitQuestionMark": "Arrêt sur paramètre (?)",
        "limitDiez": "Arrêt sur ancre (#)",
        "circuitBreaker": "Circuit breaker déclenché",
        "limitErrors": "Trop d'erreurs HTTP rencontrées",
        "limitCrawl": "Limite de 5000 URLs atteinte",
        "limitNewUrls": "Trop de nouvelles URLs détectées",
        "stoppedManually": "Arrêté manuellement",
        "insufficientData": "Données insuffisantes",
        "PAYLOAD_READ_ERROR": "Erreur lecture payload",
    }

    @staticmethod
    def _map_error_to_message(is_error: str, exit_code: int = 0) -> str:
        """Maps internal error codes to human-readable French messages for DB storage."""
        if not is_error:
            return ""
        msg = CrawlerManager.ERROR_MESSAGE_MAP.get(is_error, "")
        if not msg:
            msg = f"Erreur inconnue : {is_error}"
        return msg[:250]  # Truncate for VARCHAR(250)

    def __init__(self):
        # This dictionary ONLY tracks processes running on THIS replica.
        # The global state is in Redis.
        self.local_processes: Dict[str, asyncio.subprocess.Process] = {}

    def _kill_process_group(self, pid: int):
        """Kill a process and all its children via the process group."""
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            logger.info(f"Killed process group for PID {pid}")
        except ProcessLookupError:
            logger.debug(f"Process group for PID {pid} already terminated")
        except Exception as e:
            logger.warning(f"Could not kill process group for PID {pid}: {e}")

    async def _publish_update(self, crawl_id: str, status: str):
        """Publie une mise à jour du statut d'un job sur le canal Pub/Sub de Redis."""
        try:
            # Création du message au format JSON
            message = json.dumps({
                "crawl_id": crawl_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            })
            # Publication sur le canal
            await cache_service.publish(CRAWL_UPDATES_CHANNEL, message)
            logger.info(f"Published update for '{crawl_id}': status changed to '{status}'")
        except Exception as e:
            logger.error(f"Failed to publish update for job '{crawl_id}': {e}", exc_info=True)

    async def start_crawl(self, domain: str, start_url: str, crawl_id: str, callback_url: str, failure_callback_url: Optional[str], params: Dict[str, Any], is_restart: bool = False, oom_restart_count: int = 0) -> str:
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
        # If is_restart=True, we bypass this check because we theoretically still hold the slot (status is restarting_oom)
        existing_job = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if existing_job and existing_job.get("status") == "running" and not is_restart:
            logger.warning(f"Crawl job '{crawl_id}' is already running globally. Request rejected.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A crawl job with ID '{crawl_id}' is already in progress."
            )

        # Check dynamic global limit (V3 Logic)
        # If is_restart=True, we skip this because we already consumed a slot.
        if not is_restart:
            redis_max_global_str = await cache_service.get_key(CRAWL_MAX_GLOBAL_KEY)
            current_max_global = int(redis_max_global_str) if redis_max_global_str else settings.DEFAULT_MAX_GLOBAL_CRAWLS

            # Optimistic increment: atomically claim a slot, then check the limit.
            # This prevents the TOCTOU race where two concurrent requests both read
            # count=N-1, both pass the check, and both increment to N+1.
            new_count = await cache_service.increment_key(CRAWL_RUNNING_COUNT_KEY)

            if new_count > current_max_global:
                # Over limit — roll back the optimistic increment and reject
                await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                logger.warning(f"Global concurrency limit reached ({new_count - 1}/{current_max_global}). Rejecting '{crawl_id}'.")
                detail_payload = {
                "error_code": "GLOBAL_CAPACITY_EXCEEDED",
                "message": "The service has reached its global concurrency limit.",
                "global_limit": current_max_global,
                "current_running": new_count - 1
                }
                raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail_payload
                )

        # Local concurrency check for this replica
        # Bypassed for is_restart=True (OOM relaunch) because the slot is reserved
        # in local_processes until relaunch completes.
        active_local = sum(1 for p in self.local_processes.values() if p.returncode is None)
        if not is_restart and active_local >= settings.MAX_CONCURRENT_CRAWLS:
            # Roll back the global INCR we claimed above before rejecting
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.warning(f"Max concurrent crawls for this replica reached. Rejecting job '{crawl_id}'. Global counter rolled back.")
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

        # Mask sensitive params for logging
        safe_command = []
        for arg in command:
            if arg.startswith('--proxyapify='):
                safe_command.append('--proxyapify=***')
            elif arg.startswith('--callbackUrl='):
                safe_command.append('--callbackUrl=***')
            else:
                safe_command.append(arg)
        logger.info(f"Starting crawl '{crawl_id}' with command: {' '.join(safe_command)}")
        
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True  # Create new process group for safe cleanup (V3 Logic)
        )
        self.local_processes[crawl_id] = process

        # Create the initial job state in Redis
        job_data = {
            "crawl_id": crawl_id, "status": "running", "domain": domain,
            "start_url": start_url, "start_time": datetime.utcnow(),
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": process.pid,
            "crawl_mode": params.get("crawlMode", "standard"), # Persist mode for webhooks logic
            "params": params, # STORE PARAMS FOR RELAUNCH
            "oom_restart_count": oom_restart_count # START/TRACK RESTART COUNT
        }
        await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_data)
        
        # Note: Global counter was already incremented via optimistic increment above
        # (for non-restart crawls). For is_restart=True, we intentionally skip
        # incrementing because the slot was preserved from the original OOM'd crawl.

        await self._publish_update(crawl_id, "running")
        
        asyncio.create_task(self._monitor_process(crawl_id, process))
        return crawl_id


    async def _relaunch_oom_crawl(self, job_info: dict):
        """
        Relaunches a crawl that was killed due to OOM, preserving the concurrency slot.
        """
        crawl_id = job_info["crawl_id"]
        restart_count = int(job_info.get("oom_restart_count", 0))

        if restart_count >= settings.MAX_OOM_RESTARTS:
            logger.error(f"Maximum OOM restarts ({settings.MAX_OOM_RESTARTS}) reached for '{crawl_id}'. Failing job.")
            
            # Manually clean up since we skipped the normal failure step
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            
            job_info["status"] = "failed"
            job_info["isError"] = "OOM_MAX_RESTARTS"
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")
            
            if job_info.get("failure_callback_url"):
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]), 
                    crawl_id, 
                    job_info["domain"], 
                    -1, # Special exit code for max restart fail
                    job_info.get("crawl_mode", "standard")
                ))
            return

        logger.info(f"Relaunching OOM Job '{crawl_id}' (Attempt {restart_count + 1}/{settings.MAX_OOM_RESTARTS + 1})")
        
        # Ensure we don't drop data on restart!
        params = job_info.get("params", {})
        params["dropdata"] = False 
        
        try:
            # Short delay to allow OS to settle
            await asyncio.sleep(2)
            
            await self.start_crawl(
                domain=job_info["domain"],
                start_url=job_info["start_url"],
                crawl_id=crawl_id,
                callback_url=job_info["callback_url"],
                failure_callback_url=job_info.get("failure_callback_url"),
                params=params,
                is_restart=True, # Critical: bypass concurrency check and decrement
                oom_restart_count=restart_count + 1
            )
        except Exception as e:
            logger.error(f"Failed to relaunch OOM job '{crawl_id}': {e}", exc_info=True)
            # Release the reserved slot since relaunch failed
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            # Mark job as failed
            job_info["status"] = "failed"
            job_info["isError"] = "OOM_RELAUNCH_FAILED"
            await cache_service.set_json(f"{CRAWL_JOB_PREFIX}{crawl_id}", job_info)
            await self._publish_update(crawl_id, "failed")
            if job_info.get("failure_callback_url"):
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    -1,
                    job_info.get("crawl_mode", "standard")
                ))

    async def _send_success_webhook(self, job_info: dict):
        callback_url = job_info.get("callback_url")
        crawl_id = job_info["crawl_id"]

        if not callback_url:
            return

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

        # --- START: Add Disk-Based File Count ---
        try:
            domain = job_info.get("domain")
            if domain:
                dataset_path = os.path.join(job_info["storage_path"], 'storage', 'datasets', domain)
                if not os.path.isdir(dataset_path):
                    dataset_path = os.path.join(job_info["storage_path"], 'storage', 'datasets', domain.replace('.', '-'))
                stored_files_count = _count_files_in_dir(dataset_path)
                params["stored_files_count"] = stored_files_count
                # Optional: Override 'success' if you want the main success field to reflect disk count
                # params["success"] = stored_files_count 
                logger.info(f"Added stored_files_count ({stored_files_count}) to success webhook for '{crawl_id}'.")
        except Exception as e:
            logger.error(f"Failed to count stored files for '{crawl_id}': {e}")
        # --- END: Add Disk-Based File Count ---

        # --- START: Update Mode Report Inclusion ---
        # If this is an update job, check for the update report and include specific fields in the webhook
        if job_info.get("crawl_mode") == "update":
            try:
                report_path = os.path.join(job_info["storage_path"], '_update_report.json')
                if os.path.exists(report_path):
                    async with aiofiles.open(report_path, 'r') as f:
                        report_content = await f.read()
                        report_json = json.loads(report_content)
                        
                        # Extract specific fields and merge into top-level params
                        # Requested fields: mode, health, metrics, rates, thresholds
                        target_fields = ["mode", "health", "metrics", "rates", "thresholds", "jsonl_files"]
                        for field in target_fields:
                            if field in report_json:
                                params[field] = report_json[field]
                                
                        logger.info(f"Included filtered update report data for '{crawl_id}' in webhook.")
                else:
                    logger.info(f"Update report not found for '{crawl_id}' (maybe finished before generation).")
            except Exception as e:
                logger.warning(f"Failed to include update report for '{crawl_id}': {e}")
        # --- END: Update Mode Report Inclusion ---

        # --- START: Ensure message_erreur_crawling is present ---
        # The TypeScript crawler writes this field in _callback_payload.json.
        # If absent (e.g., older crawler version), apply Python-side fallback mapping.
        if "message_erreur_crawling" not in params:
            is_error = params.get("isError", "")
            if is_error:
                params["message_erreur_crawling"] = self._map_error_to_message(str(is_error))
        # --- END: Ensure message_erreur_crawling is present ---

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(str(callback_url), params=params, timeout=30.0)
                logger.info(f"Successfully sent success notification for '{crawl_id}'. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to send success notification for '{crawl_id}'. Error: {e}")

    async def _send_failure_webhook(self, url: str, crawl_id: str, domain: str, exit_code: int, crawl_mode: str = "standard"):
        # We process failures for both standard and update modes now
        # Determine message_erreur_crawling from context
        error_message = ""
        if exit_code == -1:
            error_message = "Out Of Memory"  # Special exit code for OOM max restarts or shutdown
        elif exit_code == 3:
            error_message = "Out Of Memory"  # OOM_RELAUNCH exit code
        
        params = {
            "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
            "timestamp": datetime.utcnow().isoformat(),
            "message_erreur_crawling": error_message
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30.0)
                logger.info(f"Successfully sent failure notification for '{crawl_id}'. Status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to send failure notification for '{crawl_id}'. Error: {e}")

    async def _send_stop_webhook(self, job_info: dict, reason: str = "stopped"):
        """
        Send webhook when a job is stopped or force-finished. (V3 Feature)
        Uses callback_url (not failure_callback_url) to match PHP script's expected format.
        """
        crawl_id = job_info['crawl_id']
        domain = job_info.get('domain', 'unknown')
        storage_path = job_info.get('storage_path', '')
        
        # Use callback_url (the PHP script expects id_domaine + storagePath for this route)
        url = job_info.get("callback_url")
        if not url:
            logger.warning(f"No callback URL for stop notification of '{crawl_id}'.")
            return
        
        # Calculate file counts for the report
        urls_crawled = 0
        error_urls = 0
        try:
            dataset_path = os.path.join(storage_path, 'storage', 'datasets', domain)
            if not os.path.isdir(dataset_path):
                # Try sanitized name fallback
                dataset_path = os.path.join(storage_path, 'storage', 'datasets', domain.replace('.', '-'))
            if os.path.isdir(dataset_path):
                urls_crawled = len([f for f in os.listdir(dataset_path) if os.path.isfile(os.path.join(dataset_path, f))])
            
            error_path = os.path.join(storage_path, 'storage', 'datasets', f'error-{domain}')
            if not os.path.isdir(error_path):
                error_path = os.path.join(storage_path, 'storage', 'datasets', f"error-{domain.replace('.', '-')}")
            if os.path.isdir(error_path):
                error_urls = len([f for f in os.listdir(error_path) if os.path.isfile(os.path.join(error_path, f))])
        except Exception as e:
            logger.warning(f"Could not count files for stop webhook: {e}")
        
        # Map reason to PHP's expected isError values
        is_error_map = {
            "stopped": "stoppedManually",
            "finished": "",  # Empty = success
            "failed": "insufficientData"
        }
        is_error = is_error_map.get(reason, "stoppedManually")
        is_finished = 1 if reason == "finished" else 0
        
        # PHP-compatible parameters
        params = {
            "id_domaine": crawl_id,
            "storagePath": storage_path,
            "isFinished": is_finished,
            "isError": is_error,
            "domain": domain,
            "success": urls_crawled,
            "failed": error_urls,
            "stored_files_count": urls_crawled,
            "timestamp": datetime.utcnow().isoformat(),
            "message_erreur_crawling": self._map_error_to_message(is_error) if is_error else ""
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(str(url), params=params, timeout=30.0)
                logger.info(f"Sent stop webhook for '{crawl_id}' (reason: {reason}). Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send stop webhook for '{crawl_id}': {e}")

    async def _monitor_process(self, crawl_id: str, process: asyncio.subprocess.Process):
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        
        job_info_initial = await cache_service.get_json(job_key)
        if not job_info_initial:
            logger.error(f"Cannot monitor process for '{crawl_id}': job info vanished immediately after start.")
            # Clean up: decrement counter and remove from local processes
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            if crawl_id in self.local_processes:
                del self.local_processes[crawl_id]
            self._kill_process_group(process.pid)
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
        # Ensure we kill any child processes (Chrome) that Node left behind
        self._kill_process_group(process.pid)

        job_info = await cache_service.get_json(job_key)
        if job_info:
            exit_code = process.returncode
            # Allow exit code 2 (Node.js intentional success/partial success) or 0 (Standard success)
            is_success = (exit_code in (0, 2))
            # Exit code 3 is a specially dedicated code for OOM_RELAUNCH
            is_oom_relaunch = (exit_code == 3)

            if is_oom_relaunch:
                 # OOM path: preserve BOTH the global counter slot AND the local_processes
                 # entry so no other crawl can steal the reserved slot before relaunch.
                 # The slot will be released by _relaunch_oom_crawl if max restarts is
                 # reached or if the relaunch itself fails.
                 logger.warning(f"Crawl '{crawl_id}' exited with OOM_RELAUNCH (code 3). Slot preserved. Auto-relaunching...")

                 job_info["status"] = "restarting_oom"
                 if "last_heartbeat" in job_info:
                    del job_info["last_heartbeat"]
                 await cache_service.set_json(job_key, job_info)
                 await self._publish_update(crawl_id, "restarting_oom")

                 # DO NOT decrement global counter — slot is reserved for relaunch
                 # DO NOT remove from local_processes — prevents slot stealing during relaunch delay
                 asyncio.create_task(self._relaunch_oom_crawl(job_info))

                 return # EXIT FUNCTION EARLY - NO WEBHOOKS

            # Non-OOM path: release the global counter slot
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)

            final_status = "finished" if is_success else "failed"
            job_info["status"] = final_status
            job_info["pid"] = None
            if "last_heartbeat" in job_info:
                del job_info["last_heartbeat"]
            await cache_service.set_json(job_key, job_info)
            logger.info(f"Crawl '{crawl_id}' finished with exit code {exit_code}. Status: {final_status}. Counter decremented.")

            await self._publish_update(crawl_id, final_status)

            # --- Create Completion Marker ---
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

            # --- WEBHOOK LOGIC ---
            if is_success and job_info.get("callback_url"):
                logger.info(f"Crawl '{crawl_id}' succeeded. Triggering success webhook.")
                asyncio.create_task(self._send_success_webhook(job_info))
            elif not is_success and job_info.get("failure_callback_url"):
                logger.info(f"Crawl '{crawl_id}' failed. Triggering failure webhook.")
                asyncio.create_task(self._send_failure_webhook(
                    str(job_info["failure_callback_url"]),
                    crawl_id,
                    job_info["domain"],
                    exit_code,
                    job_info.get("crawl_mode", "standard")
                ))

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

        await self._publish_update(crawl_id, "stopping")
        
        # Send stop notification callback immediately (V3 Logic)
        asyncio.create_task(self._send_stop_webhook(job_info, "stopped"))

        logger.info(f"Stop signal sent to crawl '{crawl_id}'. Status updated in Redis.")
        return True

    async def force_finish_crawl(self, job_info: dict, target_status: str = "finished") -> dict:
        """
        Force a job to a terminal status (finished/failed).
        Used to clean up stuck 'stopping' or 'running' jobs that have no active process.
        (V3 Feature)
        """
        crawl_id = job_info['crawl_id']
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        
        old_status = job_info.get("status")

        # Kill the actual OS process if running on this replica
        if crawl_id in self.local_processes:
            proc = self.local_processes[crawl_id]
            if proc.returncode is None:
                self._kill_process_group(proc.pid)
                logger.info(f"Force-finish: killed process for '{crawl_id}' (PID {proc.pid}).")

        # Validate target status
        if target_status not in ("finished", "failed"):
            target_status = "finished"

        # Release the global concurrency slot if the job was holding one
        if old_status in ("running", "restarting_oom", "stopping"):
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.info(f"Force-finish: released global slot for '{crawl_id}' (was '{old_status}').")

        # Update status
        job_info["status"] = target_status
        job_info["pid"] = None
        if "last_heartbeat" in job_info:
            del job_info["last_heartbeat"]
        
        await cache_service.set_json(job_key, job_info)
        await self._publish_update(crawl_id, target_status)
        
        # Use appropriate webhook based on target status
        if target_status == "failed" and job_info.get("failure_callback_url"):
            asyncio.create_task(self._send_failure_webhook(
                str(job_info["failure_callback_url"]),
                crawl_id,
                job_info.get("domain", "unknown"),
                -1,  # Force-finish exit code
                job_info.get("crawl_mode", "standard")
            ))
        else:
            asyncio.create_task(self._send_stop_webhook(job_info, target_status))
        
        # Write completion marker
        marker_path = os.path.join(job_info["storage_path"], '_completion_marker.json')
        try:
            async with aiofiles.open(marker_path, 'w') as f:
                await f.write(json.dumps({
                    "final_status": target_status,
                    "forced": True,
                    "forced_at": datetime.utcnow().isoformat()
                }))
        except Exception as e:
            logger.warning(f"Could not write completion marker for force-finish: {e}")
        
        logger.info(f"Force-finished job '{crawl_id}': {old_status} -> {target_status}")
        return {"crawl_id": crawl_id, "old_status": old_status, "new_status": target_status}

    async def get_all_statuses(self, status_filter: Optional[list] = None) -> Dict[str, CrawlStatus]:
        all_job_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
        if not all_job_keys:
            return {}

        # Batch-fetch all jobs in a single Redis round-trip (pipeline)
        pipe = cache_service.redis_client.pipeline()
        for key in all_job_keys:
            pipe.get(key)
        all_jobs_raw = await pipe.execute()

        statuses = {}
        for i, job_raw in enumerate(all_jobs_raw):
            if not job_raw:
                continue
            try:
                job_info = json.loads(job_raw)
            except (json.JSONDecodeError, TypeError):
                continue
            # Apply filter before computing full status (avoids unnecessary disk I/O)
            if status_filter and job_info.get("status") not in status_filter:
                continue
            crawl_id = all_job_keys[i].replace(CRAWL_JOB_PREFIX, "")
            status_data = await self.get_status(job_info)
            if status_data:
                statuses[crawl_id] = status_data
        return statuses

    async def get_status(self, job_info: dict) -> CrawlStatus:
        crawl_id = job_info['crawl_id']
        storage_path = job_info["storage_path"]

        # --- START: CHECK FOR STATUS SNAPSHOT ---
        # If the job is not running and a status snapshot exists, use it instead of recalculating
        # This is crucial for archived jobs where dataset files have been deleted
        snapshot_path = os.path.join(storage_path, '_status_snapshot.json')
        if job_info["status"] != "running" and os.path.exists(snapshot_path):
            try:
                async with aiofiles.open(snapshot_path, 'r') as f:
                    content = await f.read()
                    snapshot_data = json.loads(content)
                logger.info(
                    f"Loaded status from snapshot for archived crawl '{crawl_id}'.")
                return CrawlStatus(**snapshot_data)
            except Exception as e:
                logger.error(
                    f"Failed to load status snapshot for '{crawl_id}': {e}", exc_info=True)
                # Fall through to recalculate from disk
        # --- END: CHECK FOR STATUS SNAPSHOT ---

        # --- START: ENHANCED STATS CALCULATION (V3 Logic: Fallback Paths) ---
        domain = job_info["domain"]
        sanitized_name = domain.replace('.', '-')
        crawlee_storage_base = os.path.join(storage_path, 'storage', 'datasets')

        # 1. Main Dataset
        dataset_path = os.path.join(crawlee_storage_base, domain)
        if not os.path.isdir(dataset_path):
            # Try sanitized name
            dataset_path = os.path.join(crawlee_storage_base, sanitized_name)
        
        # 2. Error Dataset
        error_dataset_path = os.path.join(crawlee_storage_base, f"error-{domain}")
        if not os.path.isdir(error_dataset_path):
            error_dataset_path = os.path.join(crawlee_storage_base, f"error-{sanitized_name}")

        # 3. NFR Dataset
        nfr_dataset_path = os.path.join(crawlee_storage_base, f"nfr-{domain}")
        if not os.path.isdir(nfr_dataset_path):
            nfr_dataset_path = os.path.join(crawlee_storage_base, f"nfr-{sanitized_name}")

        urls_crawled = _count_files_in_dir(dataset_path)
        error_urls_crawled = _count_files_in_dir(error_dataset_path)
        nfr_urls_crawled = _count_files_in_dir(nfr_dataset_path)
        
        last_url_time = None
        if os.path.isdir(dataset_path):
            try:
                files = [os.path.join(dataset_path, f) for f in os.listdir(dataset_path) if os.path.isfile(os.path.join(dataset_path, f))]
                if files:
                    latest_file = max(files, key=os.path.getmtime)
                    last_url_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
            except Exception as e:
                logger.warning(f"Could not read dataset info for '{crawl_id}': {e}")
        
        return CrawlStatus(
            crawl_id=crawl_id,
            id_domaine=crawl_id, # Legacy alias
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
        
    async def get_results_archive(self, job_info: dict, include: List[IncludeInArchive]) -> Tuple[str, bool]:
        """
        Returns (archive_path, is_temporary).
        is_temporary=True means the file should be cleaned up after serving (GCS download).
        is_temporary=False means the file is cached and should NOT be cleaned up.
        """
        crawl_id = job_info['crawl_id']

        if job_info["status"] == "running":
             raise HTTPException(status_code=400, detail="Cannot get results for a running crawl.")

        # For archived crawls: local data is gone, retrieve from GCS via daemon
        if job_info["status"] == "archived":
            # First check if the shared archive still exists locally (daemon hasn't uploaded yet)
            local_shared_archive = os.path.join(settings.ARCHIVES_SHARED_PATH, f"{crawl_id}.tar.gz")
            if os.path.exists(local_shared_archive):
                logger.info(f"Serving locally staged archive for archived crawl '{crawl_id}'.")
                return local_shared_archive, False

            # Otherwise, request download from GCS via daemon
            archive_path = await self._retrieve_from_gcs_daemon(crawl_id)
            return archive_path, True

        # For finished crawls with local data: generate custom archive
        try:
            path = await anyio.to_thread.run_sync(self._generate_archive_sync, job_info, include)
            return path, False
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in background archive generation for '{crawl_id}': {e}", exc_info=True)
            raise e

    async def _retrieve_from_gcs_daemon(self, crawl_id: str) -> str:
        """
        Triggers a GCS download via the host-side download daemon and waits for the result.
        The daemon watches a shared 'requests' volume and writes downloaded archives
        to a shared 'results' volume.
        Returns the path to the downloaded archive file.
        """
        requests_dir = settings.DOWNLOAD_REQUESTS_PATH
        results_dir = settings.DOWNLOAD_RESULTS_PATH

        request_path = os.path.join(requests_dir, f"{crawl_id}.request")
        download_path = os.path.join(results_dir, f"{crawl_id}.tar.gz")
        done_path = os.path.join(results_dir, f"{crawl_id}.done")
        error_path = os.path.join(results_dir, f"{crawl_id}.error")

        # If already downloaded (from a concurrent or previous request), return immediately
        if os.path.exists(done_path) and os.path.exists(download_path):
            logger.info(f"GCS download already available for '{crawl_id}'.")
            return download_path

        # Submit download request only if not already pending
        if not os.path.exists(request_path) and not os.path.exists(done_path):
            os.makedirs(requests_dir, exist_ok=True)
            async with aiofiles.open(request_path, 'w') as f:
                await f.write(crawl_id)
            logger.info(f"GCS download request submitted for '{crawl_id}'. Waiting for daemon...")
        else:
            logger.info(f"GCS download already pending/complete for '{crawl_id}'. Waiting...")

        # Poll for completion with deadline-based timeout
        deadline = time.monotonic() + settings.GCS_DOWNLOAD_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            # Check for error first
            if os.path.exists(error_path):
                error_msg = "Download failed"
                try:
                    async with aiofiles.open(error_path, 'r') as f:
                        error_msg = (await f.read()).strip()
                except Exception:
                    pass
                # Clean up error marker
                try:
                    os.remove(error_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"GCS download failed for '{crawl_id}': {error_msg}"
                )

            # Check for success
            if os.path.exists(done_path) and os.path.exists(download_path):
                logger.info(f"GCS download complete for '{crawl_id}'.")
                return download_path

            await asyncio.sleep(1)

        # Timeout: clean up the request file to avoid daemon processing a stale request
        try:
            if os.path.exists(request_path):
                os.remove(request_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"GCS download timed out after {settings.GCS_DOWNLOAD_TIMEOUT_SECONDS}s for '{crawl_id}'. Ensure the download daemon is running."
        )

    def _generate_archive_sync(self, job_info: dict, include: List[IncludeInArchive]) -> str:
        """
        Synchronous helper function to generate the archive.
        Optimized for performance:
        1. Checks for existing cached archive properly hashing the inputs.
        2. Uses direct tarfile writing (no temp dir staging).
        3. Uses reduced compression level for speed.
        V3 Logic: Includes remapping of sanitized names back to original domain.
        """
        crawl_id = job_info['crawl_id']
        job_storage_path = job_info["storage_path"]
        domain = job_info["domain"]
        sanitized_name = domain.replace('.', '-')

        # Sort include list to ensure deterministic hash
        sorted_include = sorted([item.value for item in include])
        include_hash = hashlib.md5(json.dumps(sorted_include).encode()).hexdigest()
        
        # Define the centralized archive path with hash to allow caching of different requests
        archive_base_path = os.path.join(settings.CRAWLER_STORAGE_PATH, "archives")
        os.makedirs(archive_base_path, exist_ok=True)
        final_archive_path = os.path.join(archive_base_path, f"{crawl_id}-results-{include_hash}.tar.gz")

        # --- CACHING STRATEGY (with concurrency lock) ---
        # Get or create a lock for this specific archive path
        with _archive_locks_guard:
            if final_archive_path not in _archive_locks:
                _archive_locks[final_archive_path] = threading.Lock()
            lock = _archive_locks[final_archive_path]

        with lock:
            # Re-check cache after acquiring lock (another thread may have created it)
            if os.path.exists(final_archive_path):
                logger.info(f"Returning cached archive for '{crawl_id}' (hash: {include_hash})")
                return final_archive_path

            # Map the user's request to the actual folder names
            # Note: We prioritize original domain, then sanitized
            path_mappings = {
                IncludeInArchive.DATASET: ["datasets/" + domain, "datasets/" + sanitized_name],
                IncludeInArchive.DATASET_NFR: ["datasets/nfr-" + domain, "datasets/nfr-" + sanitized_name],
                IncludeInArchive.DATASET_ERROR: ["datasets/error-" + domain, "datasets/error-" + sanitized_name],
                IncludeInArchive.DATASET_UPDATE: ["datasets/update-" + domain, "datasets/update-" + sanitized_name],
                IncludeInArchive.REQUEST_QUEUES: ["request_queues/" + domain, "request_queues/" + sanitized_name],
                IncludeInArchive.REQUEST_URLS: ["request_urls/" + domain, "request_urls/" + sanitized_name],
                IncludeInArchive.MISCELLANEOUS: ["miscellaneous/" + domain, "miscellaneous/" + sanitized_name],
            }

            crawlee_storage_base = os.path.join(job_storage_path, 'storage')
            copied_anything = False

            # Use a temporary file for writing the partial archive to avoid race conditions
            # or serving incomplete files if the process fails mid-way.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz", dir=archive_base_path) as tmp_file:
                try:
                    # Open tarfile with reduced compression level (1 = fastest)
                    with tarfile.open(fileobj=tmp_file, mode='w:gz', compresslevel=1) as tar:
                        for item in set(include):
                            possible_paths = path_mappings.get(item, [])

                            found = False
                            for relative_path in possible_paths:
                                source_path = os.path.join(crawlee_storage_base, relative_path)

                                if os.path.exists(source_path):
                                    # V3 Logic: Remap sanitized names back to original domain in archive
                                    # If we found 'datasets/example-com', we want to store it as 'storage/datasets/example.com'
                                    arcname = os.path.join("storage", relative_path)
                                    if sanitized_name in relative_path and domain != sanitized_name:
                                        arcname = arcname.replace(sanitized_name, domain)

                                    tar.add(source_path, arcname=arcname)
                                    copied_anything = True
                                    found = True
                                    break # Stop checking fallbacks for this item type

                    if not copied_anything:
                        # Don't leave the empty temp file
                        tmp_file.close() # Ensure closed before remove
                        os.remove(tmp_file.name)
                        raise HTTPException(
                            status_code=404,
                            detail=f"None of the requested components were found for crawl '{crawl_id}'. "
                            f"The crawl data may have been cleaned up after archiving to GCS."
                        )

                except Exception:
                    # Cleanup on error
                    tmp_file.close()
                    if os.path.exists(tmp_file.name):
                        os.remove(tmp_file.name)
                    raise

                # Atomic move: only put the file in its final place when fully done
                tmp_file.close()
                shutil.move(tmp_file.name, final_archive_path)
            
        logger.info(f"Created new optimized archive for '{crawl_id}' at {final_archive_path}")
        return final_archive_path
        
    async def reindex_storage(self) -> ReindexResponse:
        """Scans storage for orphaned jobs and re-indexes them in Redis."""
        logger.info("Starting storage re-indexing process.")
        
        summary = {"scanned_directories": 0, "reindexed_jobs": 0, "already_indexed": 0, "errors": 0}
        
        try:
            redis_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
            redis_key_set = set(redis_keys)
            
            storage_dirs = [d for d in os.listdir(settings.CRAWLER_STORAGE_PATH) if os.path.isdir(os.path.join(settings.CRAWLER_STORAGE_PATH, d)) and d != "archives"]
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
                    # V3 Logic: Grace period heuristic
                    try:
                        storage_mtime = os.path.getmtime(job_storage_path)
                        age_hours = (datetime.utcnow().timestamp() - storage_mtime) / 3600
                        if age_hours < 2:
                            final_status = "running"
                        else:
                            final_status = "failed"
                    except Exception:
                        final_status = "failed"
                
                # Reconstruct metadata by parsing the log file (best effort)
                domain, start_url = "unknown", "http://unknown.com"
                log_path = os.path.join(job_storage_path, 'crawler.log')
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r', errors='ignore') as f:
                            for i, line in enumerate(f):
                                if i > 200:
                                    break
                                if '"domain":' in line:
                                    match = re.search(r'"domain":\s*"([^"]+)"', line)
                                    if match: domain = match.group(1)
                                if '"site":' in line:
                                    match = re.search(r'"site":\s*"([^"]+)"', line)
                                    if match: start_url = match.group(1)
                                if domain != "unknown" and start_url != "http://unknown.com":
                                    break
                    except Exception as e:
                        logger.error(f"Error reading log for '{crawl_id}': {e}")
                
                reindexed_data = {
                    "crawl_id": crawl_id, "status": final_status, "domain": domain,
                    "start_url": start_url, "start_time": datetime.fromtimestamp(os.path.getctime(job_storage_path)).isoformat(),
                    "storage_path": job_storage_path,
                    "callback_url": None, "failure_callback_url": None, "pid": None
                }

                if final_status in ("running", "stopping"):
                    logger.warning(f"Recovered job '{crawl_id}' has no callback_url. Webhooks will not fire for this job.")

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
            # 1. Kill the process group (V3 Logic)
            self._kill_process_group(process.pid)
            
            # 2. Update state in Redis
            job_info = await cache_service.get_json(job_key)
            if job_info and job_info.get("status") in ("running", "restarting_oom"):
                job_info["status"] = "failed"
                job_info["shutdown_reason"] = "Service instance terminated" # V3 Logic
                if "last_heartbeat" in job_info:
                    del job_info["last_heartbeat"]
                
                await cache_service.set_json(job_key, job_info)
                logger.info(f"Marked job '{crawl_id}' as 'failed' in Redis.")

                # 3. Decrement the global running counter
                await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)

                await self._publish_update(crawl_id, "failed")

                logger.info(f"Decremented global running counter for job '{crawl_id}'.")

                # 4. Send failure webhook
                if job_info.get("failure_callback_url"):
                    logger.info(f"Sending failure webhook for job '{crawl_id}'.")
                    # Use a special exit code like -1 for shutdown
                    await self._send_failure_webhook(
                        str(job_info["failure_callback_url"]),
                        crawl_id,
                        job_info["domain"],
                        -1,
                        job_info.get("crawl_mode", "standard")
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

    async def archive_crawl(self, job_info: dict) -> dict:
        """
        Archives a finished crawl job to a shared volume for host-side upload to GCS.
        Only 'finished' jobs can be archived. Sets status to 'archived' to prevent double-archiving.
        Returns a dict with crawl_id, archive_status, and archive_size_bytes.
        """
        crawl_id = job_info['crawl_id']
        job_status = job_info.get('status')

        if job_status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Crawl '{crawl_id}' has already been archived."
            )

        if job_status != "finished":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot archive crawl '{crawl_id}' because it is not in 'finished' state (current status: {job_status})."
            )

        job_storage_path = job_info["storage_path"]
        archives_dir = settings.ARCHIVES_SHARED_PATH
        target_archive_path = os.path.join(archives_dir, f"{crawl_id}.tar.gz")

        # Acquire a Redis lock to prevent concurrent archiving of the same crawl
        lock_key = f"archive_lock:{crawl_id}"
        lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=300)  # 5 min TTL
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archiving for crawl '{crawl_id}' is already in progress."
            )

        try:
            # Idempotency: if archive file already exists (e.g. daemon hasn't picked it up yet), skip re-generation
            if os.path.exists(target_archive_path):
                archive_size = os.path.getsize(target_archive_path)
                logger.info(f"Archive already exists for '{crawl_id}' at '{target_archive_path}'. Skipping re-generation.")
                await self._mark_as_archived(crawl_id, job_info)
                return {
                    "crawl_id": crawl_id,
                    "archive_status": "pending_upload",
                    "archive_size_bytes": archive_size,
                }

            # Save current status snapshot before archiving (critical: dataset files will be deleted)
            try:
                current_status = await self.get_status(job_info)
                snapshot_path = os.path.join(job_storage_path, '_status_snapshot.json')
                snapshot_data = current_status.model_dump(mode='json')

                async with aiofiles.open(snapshot_path, 'w') as f:
                    await f.write(json.dumps(snapshot_data, indent=2, default=str))

                logger.info(f"Created status snapshot for crawl '{crawl_id}' before archiving.")
            except Exception as e:
                logger.error(f"Failed to create status snapshot for '{crawl_id}': {e}", exc_info=True)

            logger.info(f"Starting archiving for crawl '{crawl_id}' to '{target_archive_path}'.")

            try:
                def _create_archive():
                    """Create tar.gz archive in shared volume."""
                    os.makedirs(archives_dir, exist_ok=True)
                    base_name = os.path.join(archives_dir, crawl_id)
                    final_path = shutil.make_archive(base_name, 'gztar', root_dir=job_storage_path)
                    archive_size = os.path.getsize(final_path)
                    if archive_size == 0:
                        raise RuntimeError(f"Archive at '{final_path}' is empty (0 bytes).")

                    # Verify archive is readable
                    try:
                        import tarfile as tf
                        with tf.open(final_path, 'r:gz') as t:
                            t.getnames()  # Force read of the archive index
                    except Exception as e:
                        os.remove(final_path)
                        raise RuntimeError(f"Archive integrity check failed: {e}")

                    return final_path, archive_size

                def _cleanup_local_data():
                    """Remove crawl data files, keeping only logs and markers."""
                    files_to_keep = {'crawler.log', '_callback_payload.json',
                                     '_completion_marker.json', '_status_snapshot.json',
                                     '_exit_reason.json', '_update_report.json',
                                     'update_stats.json'}
                    for root, dirs, files in os.walk(job_storage_path, topdown=False):
                        for name in files:
                            if name not in files_to_keep:
                                os.remove(os.path.join(root, name))
                        for name in dirs:
                            try:
                                os.rmdir(os.path.join(root, name))
                            except OSError:
                                pass

                # Step 1: Create archive
                final_path, archive_size = await anyio.to_thread.run_sync(_create_archive)
                logger.info(f"Successfully archived crawl '{crawl_id}' ({archive_size} bytes).")

                # Step 2: Mark as archived (must succeed before cleanup)
                await self._mark_as_archived(crawl_id, job_info)

                # Step 3: Cleanup (safe to fail — data is in the archive)
                try:
                    await anyio.to_thread.run_sync(_cleanup_local_data)
                    logger.info(f"Cleaned up local storage for '{crawl_id}'.")
                except Exception as e:
                    logger.warning(f"Local cleanup failed for '{crawl_id}' (archive is safe): {e}")

                return {
                    "crawl_id": crawl_id,
                    "archive_status": "pending_upload",
                    "archive_size_bytes": archive_size,
                }

            except Exception as e:
                logger.error(f"Failed to archive crawl '{crawl_id}': {e}", exc_info=True)
                raise HTTPException(
                    status_code=500, detail=f"Archiving failed: {str(e)}")
        finally:
            await cache_service.redis_client.delete(lock_key)

    async def _mark_as_archived(self, crawl_id: str, job_info: dict):
        """Updates job status to 'archived' in Redis to prevent double-archiving."""
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        job_info["status"] = "archived"
        job_info["archived_at"] = datetime.utcnow().isoformat()
        await cache_service.set_json(job_key, job_info)
        await self._publish_update(crawl_id, "archived")
        logger.info(f"Marked crawl '{crawl_id}' as 'archived' in Redis.")

    def cleanup_temp_download(self, crawl_id: str):
        """Cleans up temporary GCS download files after serving to the client."""
        results_dir = settings.DOWNLOAD_RESULTS_PATH
        for suffix in ('.tar.gz', '.done', '.error'):
            path = os.path.join(results_dir, f"{crawl_id}{suffix}")
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.debug(f"Cleaned up temp download file: {path}")
            except OSError as e:
                logger.warning(f"Failed to clean up temp file '{path}': {e}")

    async def reconcile_jobs(self):
        """
        Scans all jobs in Redis, identifies stale 'running' jobs (missing heartbeats),
        marks them as failed, and corrects the global running jobs counter.
        """
        logger.info("Starting job reconciliation...")

        all_job_keys = await cache_service.scan_keys_by_prefix(CRAWL_JOB_PREFIX)
        true_running_count = 0
        stale_jobs_count = 0

        if not all_job_keys:
            logger.info("No jobs found in Redis during reconciliation.")
            await cache_service.set_key(CRAWL_RUNNING_COUNT_KEY, 0)
            return

        # Use a pipeline to fetch all jobs at once for performance
        pipe = cache_service.redis_client.pipeline()
        for key in all_job_keys:
            pipe.get(key)

        all_jobs_raw = await pipe.execute()

        for i, job_raw in enumerate(all_jobs_raw):
            if not job_raw: continue

            try:
                job_data = json.loads(job_raw)
                crawl_id = job_data.get("crawl_id")
                status = job_data.get("status")

                if status in ("running", "restarting_oom", "stopping"):
                    # Check for staleness — applies to both running and restarting_oom jobs.
                    # A restarting_oom job holds a concurrency slot but may be orphaned
                    # if the replica that owned it crashed without cleanup.
                    last_heartbeat_str = job_data.get("last_heartbeat")
                    start_time_str = job_data.get("start_time")

                    last_activity_time = None
                    if last_heartbeat_str:
                        last_activity_time = datetime.fromisoformat(str(last_heartbeat_str))
                    elif start_time_str:
                        last_activity_time = datetime.fromisoformat(str(start_time_str))

                    is_stale = False
                    if last_activity_time:
                        time_since_activity = (datetime.utcnow() - last_activity_time).total_seconds()
                        if time_since_activity > STALE_JOB_THRESHOLD_SECONDS:
                            is_stale = True
                            logger.warning(f"Job '{crawl_id}' (status: {status}) is stale! Last activity: {time_since_activity:.0f}s ago. Marking as failed.")
                    else:
                        is_stale = True
                        logger.warning(f"Job '{crawl_id}' (status: {status}) has no time data. Marking as stale/failed.")

                    if is_stale:
                        # Mark as failed
                        job_data["status"] = "failed"
                        job_data["shutdown_reason"] = "Stale job detected (missing heartbeat)" # V3 Logic
                        if "last_heartbeat" in job_data:
                            del job_data["last_heartbeat"]

                        # Update Redis
                        # We do this individually to ensure safety, though pipeline could be used for speed if needed
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, "failed")

                        # Send failure webhook
                        if job_data.get("failure_callback_url"):
                            asyncio.create_task(self._send_failure_webhook(
                                str(job_data["failure_callback_url"]),
                                crawl_id,
                                job_data.get("domain", "unknown"),
                                -1,
                                job_data.get("crawl_mode", "standard")
                            ))

                        stale_jobs_count += 1
                    else:
                        # Truly running
                        true_running_count += 1

            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error(f"Error processing job data during reconciliation: {e}")
                continue

        # Correct the global counter
        counter_value_raw = await cache_service.get_key(CRAWL_RUNNING_COUNT_KEY)
        try:
            counter_value = int(counter_value_raw) if counter_value_raw else 0
        except (ValueError, TypeError):
            counter_value = 0

        if true_running_count != counter_value:
            logger.warning(
                f"Running jobs counter drifted. "
                f"Counter value: {counter_value}, Actual running jobs: {true_running_count}. "
                f"Resetting counter."
            )
            await cache_service.set_key(CRAWL_RUNNING_COUNT_KEY, true_running_count)
        else:
            logger.info(f"Reconciliation complete. Running: {true_running_count}, Stale/Fixed: {stale_jobs_count}")

    async def cleanup_archives(self, max_age_hours: int, delete_all: bool = False) -> Tuple[int, int, int]:
        """
        Deletes archive files that are older than `max_age_hours`.
        If `delete_all` is True, ignores age and deletes EVERYTHING.
        """
        archives_dir = os.path.join(settings.CRAWLER_STORAGE_PATH, "archives")
        if not os.path.exists(archives_dir):
            return 0, 0, 0

        logger.info(f"Starting archive cleanup. Max age: {max_age_hours}h. Delete all: {delete_all}")
        
        def _cleanup_sync():
            deleted_count = 0
            retained_count = 0
            errors = 0
            now = datetime.now().timestamp()
            
            # If delete_all is True, we set max_age_seconds to -1 so that (age > -1) is always True
            # (since age is always >= 0)
            max_age_seconds = -1 if delete_all else (max_age_hours * 3600)
            
            
            try:
                for filename in os.listdir(archives_dir):
                    file_path = os.path.join(archives_dir, filename)
                    if not os.path.isfile(file_path): continue
                        
                    # Calculate age
                    try:
                        mtime = os.path.getmtime(file_path)
                        age = now - mtime
                        
                        if age > max_age_seconds:
                            os.remove(file_path)
                            deleted_count += 1
                        else:
                            retained_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to process/delete archive '{filename}': {e}")
                        errors += 1
                        
            except Exception as e:
                logger.error(f"Error listing archives directory during cleanup: {e}")
                errors += 1

            # Also clean up stale GCS download artifacts
            for dir_path, file_suffixes in [
                (settings.DOWNLOAD_RESULTS_PATH, ('.tar.gz', '.done', '.error')),
                (settings.DOWNLOAD_REQUESTS_PATH, ('.request',)),
            ]:
                if not os.path.exists(dir_path):
                    continue
                try:
                    for filename in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, filename)
                        if not os.path.isfile(file_path):
                            continue
                        try:
                            mtime = os.path.getmtime(file_path)
                            age = now - mtime
                            if age > max_age_seconds:
                                os.remove(file_path)
                                deleted_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to clean up '{filename}': {e}")
                            errors += 1
                except Exception as e:
                    logger.error(f"Error listing directory '{dir_path}': {e}")
                    errors += 1

            return deleted_count, retained_count, errors

        # Run in thread
        try:
            deleted, retained, errors = await anyio.to_thread.run_sync(_cleanup_sync)
            logger.info(f"Archive cleanup complete. Deleted: {deleted}, Retained: {retained}, Errors: {errors}")
            return deleted, retained, errors
        except Exception as e:
            logger.error(f"Failed to execute archive cleanup: {e}")
            return 0, 0, 1

crawler_manager = CrawlerManager()
