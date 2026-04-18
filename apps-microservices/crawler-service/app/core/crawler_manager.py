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
# Distributed lock prefix — separate from state document to avoid stale-key deadlocks.
# Lock keys have a TTL and are refreshed by heartbeat; state keys can persist for observability.
CRAWL_LOCK_PREFIX = "crawl_lock:"
CRAWL_LOCK_TTL_SECONDS = 600  # 10 minutes — refreshed every heartbeat (60s)
# The global counter for running jobs
CRAWL_RUNNING_COUNT_KEY = "crawl_jobs:running_count"
# The dynamic global max crawls key in Redis
CRAWL_MAX_GLOBAL_KEY = "crawl_jobs:max_global_crawls"

CRAWL_UPDATES_CHANNEL = "crawl_updates"
# Stale thresholds now in config.py (settings.STALE_JOB_THRESHOLD_LOCAL / _REMOTE)

# Webhook retry configuration
WEBHOOK_RETRY_DELAYS = [5, 30, 120]  # seconds between attempts (exponential backoff)
FAILED_CALLBACKS_KEY = "crawl_jobs:failed_callbacks"

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
        
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
        job_storage_path = os.path.join(settings.CRAWLER_STORAGE_PATH, crawl_id)

        # Build job data early (pid will be patched after spawn).
        # last_heartbeat is set to now() immediately so concurrent reconciliation
        # on other replicas sees a fresh heartbeat — preventing the 60s blind
        # window between start_crawl and the first monitor-loop tick.
        now = datetime.utcnow()
        job_data = {
            "crawl_id": crawl_id, "status": "starting", "domain": domain,
            "start_url": start_url, "start_time": now,
            "last_heartbeat": now,
            "storage_path": job_storage_path,
            "callback_url": callback_url,
            "failure_callback_url": failure_callback_url, "pid": None,
            "crawl_mode": params.get("crawlMode", "standard"),
            "previous_crawl_id": params.get("previousCrawlId"),
            "params": params,
            "oom_restart_count": oom_restart_count,
            "replica_id": os.uname().nodename
        }

        # --- DISTRIBUTED LOCK via SET NX (separate from state document) ---
        # Lock key: crawl_lock:{id} with TTL — prevents duplicate crawl_ids across replicas.
        # State key: crawl_job:{id} — persists for observability, no locking semantics.
        if not is_restart:
            claimed = await cache_service.redis_client.set(lock_key, crawl_id, nx=True, ex=CRAWL_LOCK_TTL_SECONDS)
            if not claimed:
                logger.warning(f"Crawl job '{crawl_id}' is already running globally (lock NX failed). Request rejected.")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A crawl job with ID '{crawl_id}' is already in progress."
                )

        # Write the state document (always, for both normal starts and OOM restarts)
        await cache_service.set_json(job_key, job_data)

        # --- CAPACITY CHECKS (with cleanup on rejection) ---
        # Helper to rollback both lock claim and counter on rejection.
        # INVARIANT: OOM restarts (is_restart=True) bypass both lock claim and capacity checks,
        # so rollback is never needed. If capacity checks are ever added for restarts,
        # this guard must be updated to also handle the restart path.
        async def _rollback_claim(decrement_counter: bool = False):
            if not is_restart:
                await cache_service.delete_key(lock_key)
                await cache_service.delete_key(job_key)
                if decrement_counter:
                    await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)

        # Check dynamic global limit
        if not is_restart:
            redis_max_global_str = await cache_service.get_key(CRAWL_MAX_GLOBAL_KEY)
            current_max_global = int(redis_max_global_str) if redis_max_global_str else settings.DEFAULT_MAX_GLOBAL_CRAWLS

            new_count = await cache_service.increment_key(CRAWL_RUNNING_COUNT_KEY)

            if new_count > current_max_global:
                await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                await cache_service.delete_key(lock_key)
                await cache_service.delete_key(job_key)
                logger.warning(f"Global concurrency limit reached ({new_count - 1}/{current_max_global}). Rejecting '{crawl_id}'.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error_code": "GLOBAL_CAPACITY_EXCEEDED",
                        "message": "The service has reached its global concurrency limit.",
                        "global_limit": current_max_global,
                        "current_running": new_count - 1
                    }
                )

        # Local concurrency check for this replica
        active_local = sum(1 for p in self.local_processes.values() if p.returncode is None)
        if not is_restart and active_local >= settings.MAX_CONCURRENT_CRAWLS:
            await _rollback_claim(decrement_counter=True)
            logger.warning(f"Max concurrent crawls for this replica reached. Rejecting job '{crawl_id}'. Global counter rolled back.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "REPLICA_CAPACITY_EXCEEDED",
                    "message": "This service instance is at its maximum capacity.",
                    "replica_capacity": settings.MAX_CONCURRENT_CRAWLS,
                    "rejected_request": {"crawl_id": crawl_id, "domain": domain}
                }
            )

        # --- STORAGE SETUP ---
        try:
            os.makedirs(job_storage_path, exist_ok=True)
            logger.info(f"Using storage for crawl_id '{crawl_id}' at '{job_storage_path}'")
        except OSError as e:
            await _rollback_claim(decrement_counter=True)
            logger.error(f"Failed to create/access storage directory for crawl '{crawl_id}': {e}")
            raise HTTPException(status_code=500, detail="Could not initialize crawl environment.")

        # --- UPDATE MODE: VALIDATE PREVIOUS CRAWL ---
        previous_crawl_id = params.get("previousCrawlId")
        if params.get("crawlMode") == "update" and previous_crawl_id:
            prev_job_key = f"{CRAWL_JOB_PREFIX}{previous_crawl_id}"
            prev_job_info = await cache_service.get_json(prev_job_key)
            prev_storage = os.path.join(settings.CRAWLER_STORAGE_PATH, previous_crawl_id)

            if not prev_job_info and not os.path.isdir(prev_storage):
                await _rollback_claim(decrement_counter=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Previous crawl '{previous_crawl_id}' not found in Redis or on disk."
                )

            prev_status = prev_job_info.get("status") if prev_job_info else None
            if prev_status == "failed":
                await _rollback_claim(decrement_counter=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Previous crawl '{previous_crawl_id}' failed and cannot be used for update mode."
                )

            # Check if dataset files exist on disk
            prev_datasets_dir = os.path.join(prev_storage, "storage", "datasets")
            has_local_data = os.path.isdir(prev_datasets_dir) and len(os.listdir(prev_datasets_dir)) > 0

            if prev_status == "archived" and not has_local_data:
                logger.info(f"Previous crawl '{previous_crawl_id}' is archived. Restoring from GCS before starting update crawl.")
                try:
                    await self._restore_archived_crawl(previous_crawl_id)
                except HTTPException:
                    await _rollback_claim(decrement_counter=True)
                    raise
                except Exception as e:
                    await _rollback_claim(decrement_counter=True)
                    logger.error(f"Failed to restore archived crawl '{previous_crawl_id}': {e}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Failed to restore archived crawl '{previous_crawl_id}' from GCS: {str(e)}"
                    )
            elif not has_local_data:
                await _rollback_claim(decrement_counter=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Previous crawl '{previous_crawl_id}' has no dataset files on disk and is not archived. Cannot proceed with update mode."
                )

        # --- BUILD & LOG COMMAND ---
        command = [
            "node", settings.CRAWLER_EXECUTABLE_PATH,
            f"--domain={domain}", f"--site={start_url}", f"--id={crawl_id}",
            f"--storagePath={job_storage_path}", f"--callbackUrl={callback_url}",
        ]
        for key, value in params.items():
            if value is not None:
                command.append(f"--{key}={value}")

        safe_command = []
        for arg in command:
            if arg.startswith('--proxyapify='):
                safe_command.append('--proxyapify=***')
            elif arg.startswith('--callbackUrl='):
                safe_command.append('--callbackUrl=***')
            else:
                safe_command.append(arg)
        logger.info(f"Starting crawl '{crawl_id}' with command: {' '.join(safe_command)}")

        # --- SPAWN PROCESS (with cleanup on failure) ---
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True
            )
        except Exception as e:
            await _rollback_claim(decrement_counter=True)
            logger.error(f"Failed to spawn crawler process for '{crawl_id}': {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Could not start crawler process.")

        self.local_processes[crawl_id] = process

        # --- PATCH Redis with pid + status: running ---
        job_data["pid"] = process.pid
        job_data["status"] = "running"
        await cache_service.set_json(job_key, job_data)

        await self._publish_update(crawl_id, "running")

        asyncio.create_task(self._monitor_process(crawl_id, process))
        return crawl_id


    async def _relaunch_oom_crawl(self, job_info: dict):
        """
        Relaunches a crawl that was killed due to OOM, preserving the concurrency slot.
        """
        crawl_id = job_info["crawl_id"]
        restart_count = int(job_info.get("oom_restart_count", 0))

        # Fix 3: The coroutine may have been scheduled with a stale job_info snapshot.
        # If another actor (stale detection, force-finish, stop) has transitioned the
        # job to a terminal state in the meantime, abort the relaunch. The counter
        # was already released by whoever transitioned the job.
        current = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{crawl_id}")
        if not current or current.get("status") != "restarting_oom":
            current_status = current.get("status") if current else "gone"
            logger.info(f"OOM relaunch for '{crawl_id}' aborted: status is '{current_status}', not 'restarting_oom'.")
            return

        if restart_count >= settings.MAX_OOM_RESTARTS:
            logger.error(f"Maximum OOM restarts ({settings.MAX_OOM_RESTARTS}) reached for '{crawl_id}'. Failing job.")

            # Manually clean up since we skipped the normal failure step
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)

            job_info["status"] = "failed"
            job_info["isError"] = "OOM_MAX_RESTARTS"

            # Write completion marker before deleting key (for disk recovery)
            marker_path = os.path.join(job_info.get("storage_path", ""), '_completion_marker.json')
            try:
                async with aiofiles.open(marker_path, 'w') as f:
                    await f.write(json.dumps({
                        "final_status": "failed", "exit_code": -1,
                        "end_timestamp": datetime.utcnow().isoformat(),
                        "reason": "OOM_MAX_RESTARTS"
                    }, indent=2))
            except Exception as e:
                logger.warning(f"Could not write completion marker for OOM max-restart '{crawl_id}': {e}")

            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
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

            # Write completion marker before deleting key (for disk recovery)
            marker_path = os.path.join(job_info.get("storage_path", ""), '_completion_marker.json')
            try:
                async with aiofiles.open(marker_path, 'w') as f:
                    await f.write(json.dumps({
                        "final_status": "failed", "exit_code": -1,
                        "end_timestamp": datetime.utcnow().isoformat(),
                        "reason": "OOM_RELAUNCH_FAILED"
                    }, indent=2))
            except Exception as marker_err:
                logger.warning(f"Could not write completion marker for OOM relaunch failure '{crawl_id}': {marker_err}")

            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
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

    async def _send_webhook_with_retry(self, url: str, params: dict, crawl_id: str, webhook_type: str):
        """
        Sends an HTTP GET webhook with exponential backoff retry.
        On exhaustion, stores the failed callback in Redis for manual replay.
        """
        last_error = None
        for attempt, delay in enumerate(WEBHOOK_RETRY_DELAYS):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=30.0)
                    if 200 <= response.status_code < 300:
                        logger.info(f"Webhook '{webhook_type}' for '{crawl_id}' sent (attempt {attempt + 1}). Status: {response.status_code}")
                        return True
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(f"Webhook '{webhook_type}' for '{crawl_id}' got {response.status_code} (attempt {attempt + 1}/{len(WEBHOOK_RETRY_DELAYS)})")
            except httpx.RequestError as e:
                last_error = str(e)
                logger.warning(f"Webhook '{webhook_type}' for '{crawl_id}' failed (attempt {attempt + 1}/{len(WEBHOOK_RETRY_DELAYS)}): {e}")
            if attempt < len(WEBHOOK_RETRY_DELAYS) - 1:
                await asyncio.sleep(delay)

        # All retries exhausted — store in Redis for manual replay
        logger.error(f"Webhook '{webhook_type}' for '{crawl_id}' failed after {len(WEBHOOK_RETRY_DELAYS)} attempts. Storing for manual replay.")
        await self._store_failed_callback(url, params, crawl_id, webhook_type, last_error)
        return False

    async def _store_failed_callback(self, url: str, params: dict, crawl_id: str, webhook_type: str, error: str):
        """Appends a failed callback entry to the Redis list for later replay."""
        entry = {
            "crawl_id": crawl_id,
            "webhook_type": webhook_type,
            "url": url,
            "params": params,
            "error": error,
            "failed_at": datetime.utcnow().isoformat(),
        }
        try:
            await cache_service.redis_client.rpush(FAILED_CALLBACKS_KEY, json.dumps(entry, default=str))
        except Exception as e:
            logger.error(f"Failed to store failed callback for '{crawl_id}': {e}")

    async def _send_success_webhook(self, job_info: dict):
        callback_url = job_info.get("callback_url")
        crawl_id = job_info["crawl_id"]

        if not callback_url:
            return

        payload_path = os.path.join(job_info["storage_path"], '_callback_payload.json')

        # Retry reading the payload file — the Node.js process writes it via fs.writeFileSync + fsync
        # before exiting, but OS-level delays can still cause a brief window where the file is
        # not yet visible or fully readable by Python after process.wait() returns.
        params = {}
        max_read_attempts = 3
        retry_delays = [0.5, 1.0, 2.0]

        for attempt in range(max_read_attempts):
            if os.path.exists(payload_path):
                try:
                    async with aiofiles.open(payload_path, 'r') as f:
                        content = await f.read()
                        params = json.loads(content)
                    break  # Success
                except Exception as e:
                    if attempt < max_read_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_read_attempts}: Failed to read payload for '{crawl_id}'. Retrying in {retry_delays[attempt]}s... Error: {e}")
                        await asyncio.sleep(retry_delays[attempt])
                    else:
                        logger.error(f"All {max_read_attempts} attempts failed to read payload for '{crawl_id}'. Error: {e}", exc_info=True)
                        params = {"id_domaine": crawl_id, "isError": "PAYLOAD_READ_ERROR"}
            else:
                if attempt < max_read_attempts - 1:
                    logger.warning(f"Attempt {attempt + 1}/{max_read_attempts}: Payload file not found for '{crawl_id}'. Retrying in {retry_delays[attempt]}s...")
                    await asyncio.sleep(retry_delays[attempt])
                else:
                    logger.warning(f"Payload file not found for '{crawl_id}' after {max_read_attempts} attempts. Sending minimal callback.")
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
        # If this is an update job, check for the update report and include specific fields in the webhook.
        # Retry logic mirrors _callback_payload.json: Node.js writes with fsync but OS delays can still occur.
        if job_info.get("crawl_mode") == "update":
            report_path = os.path.join(job_info["storage_path"], '_update_report.json')
            target_fields = ["mode", "health", "metrics", "rates", "thresholds", "jsonl_files"]
            report_loaded = False

            for attempt in range(max_read_attempts):
                if os.path.exists(report_path):
                    try:
                        async with aiofiles.open(report_path, 'r') as f:
                            report_content = await f.read()
                            report_json = json.loads(report_content)

                            for field in target_fields:
                                if field in report_json:
                                    params[field] = report_json[field]

                            logger.info(f"Included filtered update report data for '{crawl_id}' in webhook.")
                            report_loaded = True
                            break
                    except Exception as e:
                        if attempt < max_read_attempts - 1:
                            logger.warning(f"Attempt {attempt + 1}/{max_read_attempts}: Failed to read update report for '{crawl_id}'. Retrying in {retry_delays[attempt]}s... Error: {e}")
                            await asyncio.sleep(retry_delays[attempt])
                        else:
                            logger.warning(f"Failed to include update report for '{crawl_id}' after {max_read_attempts} attempts: {e}")
                else:
                    if attempt < max_read_attempts - 1:
                        logger.info(f"Attempt {attempt + 1}/{max_read_attempts}: Update report not found for '{crawl_id}'. Retrying in {retry_delays[attempt]}s...")
                        await asyncio.sleep(retry_delays[attempt])
                    else:
                        logger.info(f"Update report not found for '{crawl_id}' after {max_read_attempts} attempts (maybe finished before generation).")
        # --- END: Update Mode Report Inclusion ---

        # --- START: Ensure message_erreur_crawling is present ---
        # The TypeScript crawler writes this field in _callback_payload.json.
        # If absent (e.g., older crawler version), apply Python-side fallback mapping.
        if "message_erreur_crawling" not in params:
            is_error = params.get("isError", "")
            if is_error:
                params["message_erreur_crawling"] = self._map_error_to_message(str(is_error))
        # --- END: Ensure message_erreur_crawling is present ---

        await self._send_webhook_with_retry(str(callback_url), params, crawl_id, "success")

    async def _send_failure_webhook(self, url: str, crawl_id: str, domain: str, exit_code: int, crawl_mode: str = "standard"):
        # We process failures for both standard and update modes now
        # Determine message_erreur_crawling from context
        error_message = ""
        if exit_code == -1:
            error_message = "Out Of Memory"  # Special exit code for OOM max restarts or shutdown
        elif exit_code == 3:
            error_message = "Out Of Memory"  # OOM_RELAUNCH exit code
        elif exit_code == 4:
            error_message = "Update crawl failed: previous crawl data was empty or unavailable"
        elif exit_code in (137, -9):
            error_message = "Processus tué (SIGKILL) - OOM Kill ou redémarrage forcé"
        elif exit_code is not None and exit_code < 0:
            error_message = f"Processus terminé par signal {abs(exit_code)}"  # Signal-killed
        elif exit_code not in (0, 2, 3, 4, -1, 137):
            error_message = f"Erreur inattendue (code de sortie: {exit_code})"
        
        params = {
            "crawl_id": crawl_id, "domain": domain, "exit_code": exit_code,
            "timestamp": datetime.utcnow().isoformat(),
            "message_erreur_crawling": error_message
        }
        
        await self._send_webhook_with_retry(url, params, crawl_id, "failure")

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
        
        await self._send_webhook_with_retry(str(url), params, crawl_id, "stop")

    async def _monitor_process(self, crawl_id: str, process: asyncio.subprocess.Process):
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        
        job_info_initial = await cache_service.get_json(job_key)
        if not job_info_initial:
            logger.error(f"Cannot monitor process for '{crawl_id}': job info vanished immediately after start.")
            # Clean up: decrement counter, release lock, and remove from local processes
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
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
                    lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
                    for hb_attempt in range(2):
                        try:
                            job_info["last_heartbeat"] = datetime.utcnow()
                            await cache_service.set_json(job_key, job_info)
                            await cache_service.redis_client.expire(lock_key, CRAWL_LOCK_TTL_SECONDS)
                            logger.debug(f"Heartbeat sent for running crawl '{crawl_id}'.")
                            break
                        except Exception as hb_err:
                            if hb_attempt == 0:
                                logger.warning(f"Heartbeat write failed for '{crawl_id}': {hb_err}. Retrying in 5s...")
                                await asyncio.sleep(5)
                            else:
                                logger.error(f"Heartbeat retry also failed for '{crawl_id}': {hb_err}")
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
            if exit_code == 4:
                logger.warning(f"Crawl '{crawl_id}' exited with UPDATE_NO_DATA (code 4): previous crawl data was empty or unavailable.")

            if is_oom_relaunch:
                 # OOM path: preserve BOTH the global counter slot AND the local_processes
                 # entry so no other crawl can steal the reserved slot before relaunch.
                 # The slot will be released by _relaunch_oom_crawl if max restarts is
                 # reached or if the relaunch itself fails.

                 # Fix 4: Before entering the OOM relaunch flow, re-read the current
                 # status from Redis. If stale detection (or force-finish) already
                 # transitioned the job to a terminal state, skip the OOM branch
                 # entirely. Otherwise we'd overwrite the terminal status with
                 # 'restarting_oom' and schedule a ghost relaunch.
                 current = await cache_service.get_json(job_key)
                 current_status = current.get("status") if current else None
                 if current_status in ("failed", "stopped", "finished"):
                    logger.info(f"Skipping OOM relaunch for '{crawl_id}': status is already '{current_status}' (likely stale detection or force-finish ran first).")
                    return

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

            # Non-OOM path: release the global counter slot and distributed lock
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")

            final_status = "finished" if is_success else "failed"
            job_info["status"] = final_status
            job_info["pid"] = None
            if "last_heartbeat" in job_info:
                del job_info["last_heartbeat"]
            await cache_service.set_json(job_key, job_info)
            logger.info(f"Crawl '{crawl_id}' finished with exit code {exit_code}. Status: {final_status}. Lock released. Counter decremented.")

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

            # --- CLEANUP RESTORED PREVIOUS CRAWL DATA ---
            prev_id = job_info.get("previous_crawl_id")
            if prev_id and job_info.get("crawl_mode") == "update":
                try:
                    prev_job = await cache_service.get_json(f"{CRAWL_JOB_PREFIX}{prev_id}")
                    if prev_job and prev_job.get("status") == "archived":
                        prev_datasets = os.path.join(settings.CRAWLER_STORAGE_PATH, prev_id, "storage")
                        if os.path.isdir(prev_datasets):
                            await anyio.to_thread.run_sync(lambda: shutil.rmtree(prev_datasets, ignore_errors=True))
                            logger.info(f"Cleaned up restored data for archived previous crawl '{prev_id}'.")
                except Exception as e:
                    logger.warning(f"Failed to clean up restored data for previous crawl '{prev_id}': {e}")

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

        # Fix 5: Make the decrement idempotent. Another actor (stale detection or
        # a concurrent force-finish) may have already released the slot. Re-read
        # the current status from Redis; only decrement if the job is still
        # holding a slot. old_status is the status we read when this function
        # was called — it can be stale if concurrent activity updated Redis since.
        current = await cache_service.get_json(job_key)
        current_status = current.get("status") if current else None
        if current_status in ("running", "restarting_oom", "stopping"):
            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
            logger.info(f"Force-finish: released global slot for '{crawl_id}' (was '{current_status}').")
        else:
            logger.info(f"Force-finish: slot already released for '{crawl_id}' (current status: '{current_status}'). Skipping decrement.")

        # Update status
        job_info["status"] = target_status
        job_info["pid"] = None
        if "last_heartbeat" in job_info:
            del job_info["last_heartbeat"]

        # Write completion marker BEFORE deleting key and firing webhooks,
        # so disk recovery has valid data if the webhook callback queries /status/{id}.
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

        # Release distributed lock, update state document, and notify
        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
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
                # Override status with current Redis value — snapshot was taken before status transition
                snapshot_data["status"] = job_info["status"]
                logger.info(
                    f"Loaded status from snapshot for crawl '{crawl_id}' (status: {job_info['status']}).")
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
        # Include the completion marker timestamp so the cache key changes when the crawl data changes
        # (e.g., after OOM restart or concurrent processes writing to the same storage path)
        sorted_include = sorted([item.value for item in include])
        marker_ts = ""
        marker_path = os.path.join(job_storage_path, '_completion_marker.json')
        if os.path.exists(marker_path):
            try:
                with open(marker_path, 'r') as f:
                    marker_ts = json.loads(f.read()).get("end_timestamp", "")
            except Exception:
                pass  # Fall back to empty string — same as current behavior for running jobs
        hash_input = json.dumps({"include": sorted_include, "end_timestamp": marker_ts})
        include_hash = hashlib.md5(hash_input.encode()).hexdigest()
        
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
                await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                logger.info(f"Marked job '{crawl_id}' as 'failed' in Redis. Lock released.")

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

    def _estimate_archive_required_bytes(self, job_storage_path: str) -> int:
        """Walk the source directory, sum file sizes, return size * 1.5 (gzip + safety margin).
        Returns 0 on any error — the caller is expected to apply a floor (1 GB).
        Fail-open: never raises."""
        try:
            if not os.path.isdir(job_storage_path):
                logger.warning(f"Source dir not found for size estimation: '{job_storage_path}'")
                return 0
            total = 0
            for root, _dirs, files in os.walk(job_storage_path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        continue  # broken symlink or permission denied; skip
            return int(total * 1.5)
        except Exception as e:
            logger.warning(f"Could not estimate required bytes for '{job_storage_path}': {e}")
            return 0

    def _get_archives_disk_state(self, archives_dir: str) -> dict:
        """Collect diagnostics about the archives volume.
        Returns a dict with free_bytes, total_bytes, used_pct, file_count,
        oldest_file_age_seconds. Fail-open: on any error, returns a degraded dict
        with None values and logs a warning (never raises)."""
        degraded = {
            "free_bytes": None,
            "total_bytes": None,
            "used_pct": None,
            "file_count": None,
            "oldest_file_age_seconds": None,
        }
        try:
            usage = shutil.disk_usage(archives_dir)
            total_bytes = usage.total
            free_bytes = usage.free
            used_pct = round(100.0 * (total_bytes - free_bytes) / total_bytes, 2) if total_bytes else None

            file_count = 0
            oldest_mtime = None
            try:
                for name in os.listdir(archives_dir):
                    if not name.endswith(".tar.gz"):
                        continue
                    path = os.path.join(archives_dir, name)
                    if not os.path.isfile(path):
                        continue  # skip dirs like .staging/
                    file_count += 1
                    try:
                        mtime = os.path.getmtime(path)
                        if oldest_mtime is None or mtime < oldest_mtime:
                            oldest_mtime = mtime
                    except OSError:
                        continue
            except FileNotFoundError:
                pass  # archives_dir doesn't exist yet; count stays 0

            oldest_age = int(time.time() - oldest_mtime) if oldest_mtime is not None else None

            return {
                "free_bytes": free_bytes,
                "total_bytes": total_bytes,
                "used_pct": used_pct,
                "file_count": file_count,
                "oldest_file_age_seconds": oldest_age,
            }
        except Exception as e:
            logger.warning(f"Could not get disk state for '{archives_dir}': {e}")
            return degraded

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
        # 30 min TTL: large crawls can take >5 min to archive via shutil.make_archive
        lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=1800)
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Archiving for crawl '{crawl_id}' is already in progress."
            )

        try:
            # Cleanup orphaned temp file from a previous failed attempt
            tmp_archive_path = os.path.join(archives_dir, f"{crawl_id}.tmp.tar.gz")
            if os.path.exists(tmp_archive_path):
                os.remove(tmp_archive_path)
                logger.info(f"Removed orphaned temp archive for '{crawl_id}'.")

            # Idempotency: if archive file already exists (e.g. daemon hasn't picked it up yet), skip re-generation
            if os.path.exists(target_archive_path):
                archive_size = os.path.getsize(target_archive_path)
                logger.info(f"Archive already exists for '{crawl_id}' at '{target_archive_path}'. Skipping re-generation.")
                await self._mark_as_archived(crawl_id)
                return {
                    "crawl_id": crawl_id,
                    "archive_status": "pending_upload",
                    "archive_size_bytes": archive_size,
                }

            # GCS fallback: if local archive is gone, check if it was already uploaded to GCS.
            # This handles legacy crawls stuck at 'finished' due to a previous bug where
            # _mark_as_archived was never called, but the archive was created and uploaded.
            try:
                download_path = await self._retrieve_from_gcs_daemon(crawl_id)
                # Archive exists in GCS — this crawl was already archived. Just fix the status.
                archive_size = os.path.getsize(download_path) if os.path.exists(download_path) else None
                self.cleanup_temp_download(crawl_id)
                await self._mark_as_archived(crawl_id)
                logger.info(f"Archive for '{crawl_id}' found in GCS. Status corrected to 'archived'.")
                return {
                    "crawl_id": crawl_id,
                    "archive_status": "already_in_gcs",
                    "archive_size_bytes": archive_size,
                }
            except HTTPException:
                # Archive not in GCS (502/504) — proceed with normal archiving
                logger.info(f"Archive for '{crawl_id}' not found in GCS. Proceeding with fresh archiving.")

            # --- PRE-FLIGHT DISK SPACE CHECK ---
            # Measure the source directory, check free space on /app/archives/, reject
            # with 503 if insufficient. Fail-open if measurement itself fails.
            baseline_state = self._get_archives_disk_state(archives_dir)
            logger.info(f"Archive disk state for '{crawl_id}': {baseline_state}")

            required_bytes = self._estimate_archive_required_bytes(job_storage_path)
            required_bytes = max(required_bytes, 1_073_741_824)  # 1 GB floor

            if baseline_state.get("free_bytes") is not None and baseline_state["free_bytes"] < required_bytes:
                logger.warning(
                    f"Rejecting archive '{crawl_id}': insufficient disk space. "
                    f"Required: {required_bytes} bytes, Available: {baseline_state['free_bytes']} bytes. "
                    f"Disk state: {baseline_state}"
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error_code": "INSUFFICIENT_DISK_SPACE",
                        "required_bytes": required_bytes,
                        "available_bytes": baseline_state["free_bytes"],
                        "disk_state": baseline_state,
                    },
                )

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
                    """Create tar.gz archive in a staging subdirectory, then atomically
                    move to the final location. The upload daemon uses `find -maxdepth 1`,
                    so it never sees the staging dir — preventing the race where the
                    daemon uploads (and deletes) a partial tmp file."""
                    staging_dir = os.path.join(archives_dir, ".staging")
                    os.makedirs(staging_dir, exist_ok=True)
                    os.makedirs(archives_dir, exist_ok=True)

                    staging_base = os.path.join(staging_dir, crawl_id)
                    final_target = os.path.join(archives_dir, f"{crawl_id}.tar.gz")
                    staging_path = None

                    try:
                        # Create archive in staging dir (hidden from daemon)
                        staging_path = shutil.make_archive(staging_base, 'gztar', root_dir=job_storage_path)
                        archive_size = os.path.getsize(staging_path)
                        if archive_size == 0:
                            raise RuntimeError(f"Archive at '{staging_path}' is empty (0 bytes).")

                        # Verify archive is readable
                        with tarfile.open(staging_path, 'r:gz') as t:
                            t.getnames()  # Force read of the archive index

                        # Atomic rename to final path — same filesystem, always atomic
                        os.rename(staging_path, final_target)
                        staging_path = None  # Successfully moved; skip cleanup

                        return final_target, archive_size
                    finally:
                        # Clean up staging file on any failure (disk full, corrupt, 0 bytes, etc.)
                        if staging_path and os.path.exists(staging_path):
                            try:
                                os.remove(staging_path)
                            except OSError:
                                pass

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
                await self._mark_as_archived(crawl_id)

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
                # Log disk state at failure so we can correlate with the baseline log
                try:
                    post_failure_state = self._get_archives_disk_state(archives_dir)
                    logger.error(f"Archive disk state at failure for '{crawl_id}': {post_failure_state}")
                except Exception:
                    pass
                raise HTTPException(
                    status_code=500, detail=f"Archiving failed: {str(e)}")
        finally:
            await cache_service.redis_client.delete(lock_key)

    async def _mark_as_archived(self, crawl_id: str):
        """Updates job status to 'archived' in Redis to prevent double-archiving.
        Re-reads the job from Redis to avoid overwriting concurrent field updates."""
        job_key = f"{CRAWL_JOB_PREFIX}{crawl_id}"
        fresh_job_info = await cache_service.get_json(job_key)
        if not fresh_job_info:
            logger.error(f"Cannot mark '{crawl_id}' as archived: job not found in Redis.")
            return
        fresh_job_info["status"] = "archived"
        fresh_job_info["archived_at"] = datetime.utcnow().isoformat()
        await cache_service.set_json(job_key, fresh_job_info)
        await self._publish_update(crawl_id, "archived")
        logger.info(f"Marked crawl '{crawl_id}' as 'archived' in Redis.")

    async def _restore_archived_crawl(self, previous_crawl_id: str):
        """
        Restores an archived crawl's data from GCS for use by an update-mode crawl.
        Uses the existing download daemon and extracts the archive to the storage path.
        """
        lock_key = f"restore_lock:{previous_crawl_id}"
        lock_acquired = await cache_service.redis_client.set(lock_key, "1", nx=True, ex=1800)

        if not lock_acquired:
            # Another request is restoring — wait for it to complete by checking for data
            logger.info(f"Restoration of '{previous_crawl_id}' already in progress. Waiting...")
            deadline = time.monotonic() + settings.GCS_DOWNLOAD_TIMEOUT_SECONDS
            target_dir = os.path.join(settings.CRAWLER_STORAGE_PATH, previous_crawl_id, "storage", "datasets")
            while time.monotonic() < deadline:
                if os.path.isdir(target_dir) and len(os.listdir(target_dir)) > 0:
                    logger.info(f"Restoration of '{previous_crawl_id}' completed by another request.")
                    return
                await asyncio.sleep(2)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Timed out waiting for restoration of archived crawl '{previous_crawl_id}'."
            )

        try:
            target_storage = os.path.join(settings.CRAWLER_STORAGE_PATH, previous_crawl_id)

            # Check if already restored (race between lock check and actual data)
            datasets_dir = os.path.join(target_storage, "storage", "datasets")
            if os.path.isdir(datasets_dir) and len(os.listdir(datasets_dir)) > 0:
                logger.info(f"Data for '{previous_crawl_id}' already present. Skipping restoration.")
                return

            # Download from GCS via the existing daemon mechanism
            logger.info(f"Requesting GCS download for archived crawl '{previous_crawl_id}'...")
            download_path = await self._retrieve_from_gcs_daemon(previous_crawl_id)

            # Extract the archive to the storage path
            logger.info(f"Extracting archive for '{previous_crawl_id}' to '{target_storage}'...")
            def _extract_archive():
                os.makedirs(target_storage, exist_ok=True)
                with tarfile.open(download_path, 'r:gz') as tar:
                    tar.extractall(path=target_storage)

            await anyio.to_thread.run_sync(_extract_archive)
            logger.info(f"Successfully restored archived crawl '{previous_crawl_id}' from GCS.")

            # Clean up the downloaded tar.gz and daemon markers
            self.cleanup_temp_download(previous_crawl_id)

        finally:
            await cache_service.redis_client.delete(lock_key)

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

    async def get_pending_callbacks(self) -> list:
        """Returns all failed webhook callbacks stored in Redis."""
        raw_entries = await cache_service.redis_client.lrange(FAILED_CALLBACKS_KEY, 0, -1)
        callbacks = []
        for raw in raw_entries:
            try:
                callbacks.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return callbacks

    async def clear_pending_callbacks(self) -> int:
        """Clears all failed webhook callbacks from Redis. Returns number of keys deleted."""
        return await cache_service.redis_client.delete(FAILED_CALLBACKS_KEY)

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

                    # --- Ownership-aware stale detection ---
                    job_replica_id = job_data.get("replica_id")
                    my_replica_id = os.uname().nodename
                    is_local_job = (job_replica_id == my_replica_id) if job_replica_id else False

                    # Determine threshold based on ownership
                    if is_local_job:
                        stale_threshold = settings.STALE_JOB_THRESHOLD_LOCAL
                    elif job_replica_id:
                        stale_threshold = settings.STALE_JOB_THRESHOLD_REMOTE
                    else:
                        # Legacy job (no replica_id) — backward compatible
                        stale_threshold = settings.STALE_JOB_THRESHOLD_LOCAL

                    is_stale = False
                    if last_activity_time:
                        time_since_activity = (datetime.utcnow() - last_activity_time).total_seconds()
                        if time_since_activity > stale_threshold:
                            is_stale = True
                    else:
                        is_stale = True

                    # Local job override: if process is alive locally, skip stale detection
                    if is_stale and is_local_job and status != "stopping":
                        if crawl_id in self.local_processes:
                            proc = self.local_processes[crawl_id]
                            if proc.returncode is None:
                                logger.info(f"Job '{crawl_id}' heartbeat is stale but local process is alive (PID {proc.pid}). Skipping stale detection.")
                                is_stale = False

                    if is_stale:
                        # Branch based on status: stopping jobs are cleaned up silently,
                        # running/restarting_oom jobs are marked as failed with webhook.
                        is_stopping = (status == "stopping")
                        final_status = "stopped" if is_stopping else "failed"

                        if is_stopping:
                            logger.info(f"Job '{crawl_id}' (status: stopping) is stale. Cleaning up as 'stopped' (stop webhook already sent).")
                        else:
                            time_info = f"{time_since_activity:.0f}s ago" if last_activity_time else "no time data"
                            ownership_info = f"local" if is_local_job else (f"remote (replica: {job_replica_id})" if job_replica_id else "legacy (no replica_id)")
                            logger.warning(f"Job '{crawl_id}' (status: {status}, {ownership_info}) is stale! Last activity: {time_info}. Marking as failed.")

                        # Fix 1: Release the global slot if this job was holding one.
                        # Without this, the counter drifts: job is marked failed but
                        # the slot stays reserved until the next reconciliation bulk reset.
                        if status in ("running", "restarting_oom", "stopping"):
                            await cache_service.safe_decrement_key(CRAWL_RUNNING_COUNT_KEY)
                            logger.info(f"Stale detection: released global slot for '{crawl_id}' (was '{status}').")

                        # Fix 2: Kill the subprocess if still alive. A stale job whose
                        # subprocess is still running is a zombie — it'll keep consuming
                        # resources and may eventually exit with OOM (code 3), triggering
                        # a ghost relaunch of an already-failed job. Mirrors force_finish_crawl.
                        if crawl_id in self.local_processes:
                            proc = self.local_processes[crawl_id]
                            if proc.returncode is None:
                                self._kill_process_group(proc.pid)
                                logger.info(f"Stale detection: killed process for '{crawl_id}' (PID {proc.pid}).")

                        job_data["status"] = final_status
                        job_data["shutdown_reason"] = "Stop cleanup (stale)" if is_stopping else "Stale job detected (missing heartbeat)"
                        if "last_heartbeat" in job_data:
                            del job_data["last_heartbeat"]

                        # Write completion marker
                        storage_path = job_data.get("storage_path", "")
                        if storage_path and os.path.isdir(storage_path):
                            marker_path = os.path.join(storage_path, '_completion_marker.json')
                            try:
                                async with aiofiles.open(marker_path, 'w') as f:
                                    await f.write(json.dumps({
                                        "final_status": final_status, "exit_code": 0 if is_stopping else -1,
                                        "end_timestamp": datetime.utcnow().isoformat(),
                                        "reason": "stop_cleanup" if is_stopping else "stale_heartbeat"
                                    }, indent=2))
                            except Exception as marker_err:
                                logger.warning(f"Could not write completion marker for stale job '{crawl_id}': {marker_err}")

                        # Release distributed lock and update state document
                        await cache_service.delete_key(f"{CRAWL_LOCK_PREFIX}{crawl_id}")
                        await cache_service.set_json(all_job_keys[i], job_data)
                        await self._publish_update(crawl_id, final_status)

                        # Only send failure webhook for non-stopping jobs
                        if not is_stopping and job_data.get("failure_callback_url"):
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

                elif status in ("failed", "finished"):
                    # Terminal state keys are safe to keep (lock is separate).
                    # Clean up any orphaned lock keys that may have survived a crash.
                    lock_key = f"{CRAWL_LOCK_PREFIX}{crawl_id}"
                    if await cache_service.redis_client.exists(lock_key):
                        await cache_service.delete_key(lock_key)
                        logger.info(f"Reconciliation: cleaned up orphaned lock for terminal job '{crawl_id}'.")

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
