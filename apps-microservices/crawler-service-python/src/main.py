import asyncio
import argparse
import sys
import os
import json
import logging
import signal
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Camoufox Integration
from camoufox import AsyncNewBrowser
from typing_extensions import override

# Updated imports to include ConcurrencySettings and BrowserPool components
from crawlee import Request, SkippedReason, ConcurrencySettings
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext, PlaywrightPreNavCrawlingContext, BasicCrawlingContext
from crawlee.browsers import BrowserPool, PlaywrightBrowserPlugin, PlaywrightBrowserController
from crawlee.fingerprint_suite import DefaultFingerprintGenerator, HeaderGeneratorOptions, ScreenOptions
from crawlee.proxy_configuration import ProxyConfiguration
from crawlee.configuration import Configuration
from crawlee.storages import Dataset, RequestQueue
from redis.asyncio import Redis

import routes
from state import DedupManager, StatsManager
from utils import get_system_stats, get_urls_crawled, update_urls_crawled, drop_dataset, is_stopped_manually, attach_file_logger, ensure_alias_symlink, load_dataset_urls_generator, reclaim_failed_requests, sanitize_queue_on_disk, process_page, detect_captcha

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

# Load Env
load_dotenv()

# --- EXIT REASON TRACKING ---
# Global variable to track exit reason across the application
EXIT_REASON_INFO = {
    "reason": "unknown",        # completed, error, signal, oom_suspected
    "details": None,            # Additional details (exception message, signal number)
    "traceback": None,          # Full traceback if available
    "stats": None,              # Crawler stats at exit time
    "timestamp": None           # ISO timestamp of exit
}

def write_exit_reason(storage_path: str, reason: str, details: str | None = None, tb: str | None = None, stats: dict | None = None):
    """
    Writes the exit reason to a JSON file for later analysis.
    Called from finally blocks and signal handlers.
    """
    global EXIT_REASON_INFO
    
    EXIT_REASON_INFO["reason"] = reason
    EXIT_REASON_INFO["details"] = details
    EXIT_REASON_INFO["traceback"] = tb
    EXIT_REASON_INFO["stats"] = stats
    EXIT_REASON_INFO["timestamp"] = datetime.now().isoformat()
    
    exit_file = os.path.join(storage_path, "_exit_reason.json")
    try:
        with open(exit_file, "w", encoding="utf-8") as f:
            json.dump(EXIT_REASON_INFO, f, indent=2, ensure_ascii=False)
        logger.info(f"Exit reason written to {exit_file}")
    except Exception as e:
        logger.error(f"Failed to write exit reason file: {e}")

def check_previous_crash(storage_path: str):
    """
    Checks if a previous run ended abnormally by looking at the exit reason file.
    Logs a warning if the previous run crashed.
    """
    exit_file = os.path.join(storage_path, "_exit_reason.json")
    
    if os.path.exists(exit_file):
        try:
            with open(exit_file, "r", encoding="utf-8") as f:
                prev_reason = json.load(f)
            
            reason = prev_reason.get("reason", "unknown")
            
            if reason not in ["completed", "stoppedManually", "limitCrawl", "limitQuestionMark", "limitDiez"]:
                logger.warning(f"⚠️ Previous run ended abnormally: {reason}")
                if prev_reason.get("details"):
                    logger.warning(f"   Details: {prev_reason.get('details')}")
                if prev_reason.get("timestamp"):
                    logger.warning(f"   Timestamp: {prev_reason.get('timestamp')}")
        except Exception as e:
            logger.warning(f"Could not read previous exit reason: {e}")
# --------------------------------

class CamoufoxPlugin(PlaywrightBrowserPlugin):
    """Browser plugin that uses Camoufox stealth browser with optimized settings."""
    @override
    async def new_browser(self) -> PlaywrightBrowserController:
        if not self._playwright:
            raise RuntimeError('Playwright browser plugin is not initialized.')

        MAX_RETRIES = 3
        BASE_BACKOFF = 2  # Exponential backoff: 2s, 4s, 8s
        last_error = None
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"🕵️ Attempt {attempt}/{MAX_RETRIES}: Launching Camoufox browser...")
                
                # Wrap creation in timeout because Camoufox can hang in Docker
                # Reduced from 60s to 45s - fail faster to allow retry
                browser = await asyncio.wait_for(
                    AsyncNewBrowser(self._playwright, **self._browser_launch_options),
                    timeout=45
                )
                
                logger.info("✅ Camoufox browser launched successfully")
                return PlaywrightBrowserController(
                    browser=browser,
                    # Increased from 3 to 5 to reduce browser creation bottleneck
                    max_open_pages_per_browser=5,
                    # This turns off the crawlee header_generation. Camoufox has its own.
                    header_generator=None,
                )
            except asyncio.TimeoutError:
                last_error = "Timeout waiting for Camoufox to launch (>45s)"
                logger.warning(f"⚠️ {last_error}. Retrying...")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"⚠️ Failed to launch Camoufox: {e}. Retrying...")
                
            # Exponential backoff before retry (2s, 4s, 8s)
            if attempt < MAX_RETRIES:
                backoff_time = BASE_BACKOFF ** attempt
                logger.info(f"⏳ Waiting {backoff_time}s before retry...")
                await asyncio.sleep(backoff_time)
                
        raise RuntimeError(f"Failed to launch Camoufox after {MAX_RETRIES} attempts. Last error: {last_error}")

async def heartbeat_task(redis_url: str, job_id: str, domain: str, hostname: str):
    """
    Sends heartbeat to Redis every 2 seconds.
    """
    redis = Redis.from_url(redis_url)
    try:
        await redis.ping()
        logger.info("Connected to Redis for Heartbeat")
        
        while True:
            stats = get_system_stats()
            
            payload = {
                "type": "heartbeat",
                "replicaId": hostname,
                "jobId": job_id,
                "domain": domain,
                "cpu": stats["cpu_percent"] / 100.0, # Frontend likely expects 0.0-1.0 or percent? Node.js sent Math.min(cpuPercent, 1) where cpuPercent was 0-1. psutil returns 0-100. So divide by 100.
                "ram": int(stats["ram_used_gb"] * 1024 * 1024 * 1024), 
                "totalRam": int(stats["ram_total_gb"] * 1024 * 1024 * 1024),
                "topProcesses": stats["top_processes"],
                "timestamp": int(datetime.now().timestamp() * 1000),
                "status": "running"
            }
            
            await redis.publish("crawler:heartbeat", json.dumps(payload))
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        logger.info("Heartbeat task cancelled")
    except Exception as e:
        logger.error(f"Heartbeat error: {e}")
    finally:
        await redis.aclose()

async def monitor_task(crawler: PlaywrightCrawler, stop_reason_setter):
    """
    Monitors crawler health and progress.
    Stops the crawler if it stalls with zero progress.
    """
    last_finished = 0
    stalled_checks = 0
    MAX_STALL_CHECKS = 6  # 6 checks * 30s = 3 minutes
    
    while True:
        await asyncio.sleep(30)
        try:
            # Stats check
            stats = crawler.statistics.state
            finished = stats.requests_finished
            failed = stats.requests_failed
            total = finished + failed
            
            logger.info(f"Health Check: Finished={finished}, Failed={failed}, Queued=Unknown")
            
            if finished == last_finished:
                stalled_checks += 1
                
                # Critical stall: No progress at all after 3 minutes
                if stalled_checks >= MAX_STALL_CHECKS and total == 0:
                    logger.error(f"🛑 CRITICAL: Crawler stalled with ZERO pages processed after {MAX_STALL_CHECKS * 30}s. Stopping.")
                    stop_reason_setter("stalledZeroProgress")
                    crawler.stop()
                    return
                
                # Regular stall warning (but crawler is making some progress)
                if stalled_checks >= 10:  # 5 minutes
                    logger.warning(f"⚠️ Crawler might be stalled! No progress for 5 minutes. (Processed: {total})")
            else:
                stalled_checks = 0
                last_finished = finished
                
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Monitor task error: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Python Crawler Service")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--storagePath", required=True)
    parser.add_argument("--callbackUrl", required=True)
    
    # Standard Options
    parser.add_argument("--breaklimit", default="False")
    parser.add_argument("--proxyapify", default=None)
    parser.add_argument("--dropdata", default="False")
    parser.add_argument("--method", default="prod")
    parser.add_argument("--skipquestionmark", default="False")
    parser.add_argument("--skipdiez", default="False")
    
    # Bypass Options (Added)
    parser.add_argument("--bypassquestionmark", default="False")
    parser.add_argument("--bypassdiez", default="False")

    parser.add_argument("--maxConcurrency", default=5, type=int)
    
    # Added paramPerCrawl (Point 7)
    parser.add_argument("--percrawl", default=500, type=int)
    # Added paramPerMinute (Point 8)
    parser.add_argument("--perminute", default=100, type=int)
    
    # Add new params for URL cleaning (comma separated)
    parser.add_argument("--tokeep", default="")
    parser.add_argument("--toremove", default="")
    parser.add_argument("--typecrawling", default="link")

    # Update Mode Options
    parser.add_argument("--crawlMode", default="standard")
    parser.add_argument("--previousCrawlId", default=None)
    parser.add_argument("--maxErrors", default=0, type=int)
    parser.add_argument("--maxRedirects", default=0, type=int)
    parser.add_argument("--maxNewUrls", default=0, type=int)
    
    # Camoufox Integration
    parser.add_argument("--camoufox", default="False")
    
    args, unknown = parser.parse_known_args()
    
    if unknown:
        logger.warning(f"Ignored unknown CLI arguments: {unknown}")
    
    domain = args.domain
    site = args.site
    job_id = args.id
    storage_path = args.storagePath
    proxy_apify_password = args.proxyapify
    
    crawl_mode = args.crawlMode
    previous_crawl_id = args.previousCrawlId
    
    # Parse lists
    to_keep = [x.strip() for x in args.tokeep.split(',') if x.strip()]
    to_remove = [x.strip() for x in args.toremove.split(',') if x.strip()]
    
    break_limit = str(args.breaklimit).lower() == 'true'
    drop_data = str(args.dropdata).lower() == 'true'
    use_camoufox = str(args.camoufox).lower() == 'true'
    
    # Configure Routes Global Vars
    routes.SKIP_QUESTION_MARK = str(args.skipquestionmark).lower() == 'true'
    routes.SKIP_DIEZ = str(args.skipdiez).lower() == 'true'
    routes.BYPASS_QUESTION_MARK = str(args.bypassquestionmark).lower() == 'true'
    routes.BYPASS_DIEZ = str(args.bypassdiez).lower() == 'true'
    
    routes.DOMAIN = domain
    routes.BASE_URL = site
    routes.TO_KEEP_CUSTOM = to_keep
    routes.TO_REMOVE_CUSTOM = to_remove
    
    # Inject Limits
    routes.max_errors = args.maxErrors
    routes.max_redirects = args.maxRedirects
    routes.max_new_urls = args.maxNewUrls

    # Limits Configuration
    param_per_crawl = args.percrawl
    # Point 8: paramPerMinute
    param_per_minute = args.perminute

    logger.info(f"Starting crawler for {domain} ({site}) in {storage_path} (Mode: {crawl_mode})")

    # --- MEMORY PRE-FLIGHT CHECK ---
    # Parity with Node.js: Warn if memory usage is already > 80%, but DO NOT ABORT (User Request)
    pre_stats = get_system_stats()
    ram_percent = pre_stats["ram_percent"]
    if ram_percent > 80:
        logger.warning(f"⚠️ Memory is high: {ram_percent:.1f}% used. Starting anyway (relying on AutoscaledPool).")
        logger.warning(f"   Limits: {pre_stats['ram_used_gb']:.2f}GB / {pre_stats['ram_total_gb']:.2f}GB")
        # sys.exit(1) # DISABLED per user request
    else:
        logger.info(f"✅ Pre-flight memory check passed: {ram_percent:.1f}% used")
    # -------------------------------

    # Change CWD to storage path
    try:
        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)
        os.chdir(storage_path)
        # CRITICAL: Frontend expects this exact string subset to parse logs correctly
        logger.info(f"[stdout] Changed working directory to: {os.getcwd()}")
    except Exception as e:
        logger.error(f"Failed to change CWD: {e}")
        sys.exit(1)

    # Attach File Logger
    now_str = datetime.now().isoformat().replace(":", "-")
    log_name = f"{domain}-logs-{now_str}.log"
    attach_file_logger(log_name)

    # --- CRASH DETECTION ---
    # Check if a previous run ended abnormally
    check_previous_crash(storage_path)

    # Clean up stale stopper file from previous runs to prevent immediate stop (Restart Loop Fix)
    stopper_file = os.path.join(storage_path, "stopper", f"{domain}.txt")
    if os.path.exists(stopper_file):
        try:
            os.remove(stopper_file)
            logger.info(f"Removed stale stopper file from previous run: {stopper_file}")
        except Exception as e:
            logger.warning(f"Failed to remove stale stopper file: {e}")

    # Sanitize storage name
    crawlee_storage_name = domain.replace('.', '-')
    routes.CRAWLEE_STORAGE_NAME = crawlee_storage_name
    
    # Symlink aliases
    CRAWLEE_STORAGE_DIR = os.getenv("CRAWLEE_STORAGE_DIR", "storage")
    base_queues = os.path.join(CRAWLEE_STORAGE_DIR, "request_queues")
    base_datasets = os.path.join(CRAWLEE_STORAGE_DIR, "datasets")
    base_kvs = os.path.join(CRAWLEE_STORAGE_DIR, "key_value_stores")
    
    # 1. Main Domain Symlinks
    ensure_alias_symlink(crawlee_storage_name, domain, [base_queues, base_datasets, base_kvs])
    
    # 2. Error & NFR Dataset Symlinks (Bridge legacy folders like 'error-domain.com' to 'error-domain-com')
    ensure_alias_symlink(f"error-{crawlee_storage_name}", f"error-{domain}", [base_datasets])
    ensure_alias_symlink(f"nfr-{crawlee_storage_name}", f"nfr-{domain}", [base_datasets])

    # --- STATE MANAGEMENT INIT ---
    # Moved initialization BEFORE drop_data logic to ensure we can clean up Redis
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Initialize Managers
    dedup_manager = DedupManager(redis_url, job_id)
    stats_manager = StatsManager(redis_url, job_id, storage_path)
    
    # Inject into routes
    routes.dedup_manager = dedup_manager
    routes.stats_manager = stats_manager

    is_historised = False
    if drop_data:
        logger.info("Dropping datasets, request queue, and clearing state...")
        try:
           # Implement "Double Drop" to remove both original and sanitized folder names
           await drop_dataset(domain) 
           await drop_dataset(crawlee_storage_name)
           
           # Also clean up error/nfr datasets
           await drop_dataset(f"error-{domain}")
           await drop_dataset(f"error-{crawlee_storage_name}")
           
           await drop_dataset(f"nfr-{domain}")
           await drop_dataset(f"nfr-{crawlee_storage_name}")
           
           # --- STATE CLEANUP ---
           # Clear Redis keys and local stats file
           await dedup_manager.cleanup()
           await stats_manager.cleanup()
           
           if os.path.exists(stats_manager.stats_file):
               try:
                   os.remove(stats_manager.stats_file)
                   logger.info(f"Removed local stats file: {stats_manager.stats_file}")
               except Exception as e:
                   logger.warning(f"Failed to remove stats file: {e}")

           is_historised = True
        except Exception as e:
           logger.warning(f"Failed to drop datasets/state: {e}")
    # ------------------------------------
    
    # Load Stats if resuming (will be empty if we just cleaned it up)
    await stats_manager.load_state_from_disk()
    
    # Load Historical URLs into Redis (Cold Storage -> Hot Redis)
    # Note: We pass `drop_data` here because get_urls_crawled handles file removal if True
    history_urls = get_urls_crawled(domain, is_historised, drop_data) 
    if history_urls:
        logger.info(f"Seeding {len(history_urls)} historical URLs into Redis Deduplication...")
        await dedup_manager.load_from_list(history_urls)

    # --- QUEUE SANITIZATION ON DISK (Point 11) ---
    # Runs before opening the queue to ensure clean state
    if routes.SKIP_QUESTION_MARK or routes.SKIP_DIEZ:
        sanitize_queue_on_disk(
            crawlee_storage_name,
            routes.SKIP_QUESTION_MARK,
            routes.SKIP_DIEZ,
            to_keep,
            to_remove
        )

    # Initialize Request Queue
    request_queue = await RequestQueue.open(name=crawlee_storage_name)
    logger.info(f"Opened RequestQueue: {crawlee_storage_name}")
    
    # --- SEEDING LOGIC ---
    if crawl_mode == "update":
        if not previous_crawl_id:
            logger.error("Update mode requires --previousCrawlId")
            sys.exit(1)
            
        logger.info(f"Running in UPDATE mode. Seeding from previous crawl: {previous_crawl_id}")
        
        # Generator for memory efficiency
        count = 0
        async for url in load_dataset_urls_generator(previous_crawl_id, domain):
             # 1. Add to Redis (Mark as Known)
             await dedup_manager.add_url(url)
             
             # 2. Add to Queue (Mark as Existing for Verification)
             await request_queue.add_request(Request.from_url(url, user_data={"is_existing": True}))
             count += 1
             if count % 1000 == 0:
                 logger.info(f"Seeded {count} URLs...")
                 
        logger.info(f"Finished seeding {count} URLs from previous crawl.")
        
    elif await request_queue.is_empty():
        # Standard Seed
        logger.info("Seeding standard start URL...")
        await request_queue.add_request(Request.from_url(site, user_data={"is_existing": False}))
    
    # Reclaim Failed Requests (Point 10)
    if crawl_mode != "generate_data": # Just in case we support generate_data later
         await reclaim_failed_requests(crawlee_storage_name, request_queue)

    # Safety Reseed: If queue is empty after reclaim (e.g., initial request was lost), re-add seed.
    if await request_queue.is_empty():
        logger.warning("Queue is empty after reclaim. Re-seeding start URL...")
        await request_queue.add_request(Request.from_url(site, user_data={"is_existing": False}))

    # Start Heartbeat
    hostname = os.uname().nodename
    hb_task = asyncio.create_task(heartbeat_task(redis_url, job_id, domain, hostname))

    # Configure Proxy
    proxy_configuration = None
    if proxy_apify_password:
        proxy_url = f"http://auto:{proxy_apify_password}@proxy.apify.com:8000"
        proxy_configuration = ProxyConfiguration(proxy_urls=[proxy_url])
        # Log proxy URL (mask password for security)
        masked_proxy = f"http://auto:****@proxy.apify.com:8000"
        logger.info(f"🌐 Proxy configured: {masked_proxy}")
    else:
        logger.warning("⚠️ No proxy configured. Running without proxy (direct connection).")

    try:
        # Initialize Crawler
        if use_camoufox:
            logger.info("🕵️ Using Camoufox stealth browser")
            plugin = CamoufoxPlugin()
            browser_pool = BrowserPool(
                plugins=[plugin],
                # Reduced from 60s to 30s - fail faster on stuck page creation
                # This allows the retry mechanism to kick in sooner
                operation_timeout=timedelta(seconds=30),
                # Increased from 10 to 25 - reduce browser restart overhead
                # Browser launches are expensive in Docker, keep browsers longer
                retire_browser_after_page_count=25
            )
        else:
            # Configure Browser Pool with Fingerprints
            fingerprint_generator = DefaultFingerprintGenerator(
                header_options=HeaderGeneratorOptions(
                    browsers=['chrome'],
                    operating_systems=['windows', 'macos', 'linux'],
                    devices=['desktop'],
                    locales=['fr']
                ),
                screen_options=ScreenOptions(min_width=400)
            )
            
            browser_plugin = PlaywrightBrowserPlugin(
                browser_type='chromium',
                fingerprint_generator=fingerprint_generator,
                # CRITICAL: These flags are REQUIRED for Chromium to work in Docker
                browser_launch_options={
                    "headless": True,
                    "args": [
                        "--no-sandbox",              # Required: Docker runs as root
                        "--disable-setuid-sandbox",  # Required: Additional sandbox workaround
                        "--disable-dev-shm-usage",   # Prevents /dev/shm memory issues in containers
                        "--disable-gpu",             # GPU not available in containers
                    ]
                }
            )
            # Aligned with Camoufox path: retire_browser_after_page_count=25
            browser_pool = BrowserPool(plugins=[browser_plugin], retire_browser_after_page_count=25)

        # Initialize Crawler 
        crawler_args = {
            "request_handler": routes.router,
            "request_manager": request_queue,
            "max_requests_per_crawl": param_per_crawl if param_per_crawl > 0 else None,
            # Point 8: Rate Limiting
            "concurrency_settings": ConcurrencySettings(max_tasks_per_minute=param_per_minute),
            "use_session_pool": True,
            "browser_pool": browser_pool,
            "respect_robots_txt_file": True,
            "max_request_retries": 5,  # Allow more retries for transient blocks
            # Reduced timeouts to fail faster - prevents hanging on slow/blocked pages
            "navigation_timeout": timedelta(seconds=45),
            "request_handler_timeout": timedelta(seconds=60)
        }

        if proxy_configuration:
            crawler_args["proxy_configuration"] = proxy_configuration

        crawler = PlaywrightCrawler(**crawler_args)
        
        # Inject crawler instance into routes for manual stop control
        routes.crawler_instance = crawler
        
        # Failed Request Handler (Error Handler)
        # Uses closure to access stats_manager, crawler, and crawlee_storage_name
        @crawler.failed_request_handler
        async def error_handler(context: BasicCrawlingContext | PlaywrightCrawlingContext, error: Exception) -> None:
            from crawlee.storages import Dataset
            
            request = context.request
            log = context.log
            
            # Safely access page - it might be None if error occurred before navigation
            page = getattr(context, 'page', None)
            
            # Accumulate errors in user_data since Request object doesn't have error_messages attribute
            errors_list = request.user_data.get("error_messages")
            if not isinstance(errors_list, list):
                errors_list = []
            
            # Extract error info from context if available
            # For PyCrawlee, error details might be attached differently or just inferred from context
            # If the handler was called, an exception occurred.
            
            # In newer Crawlee versions, the error might be passed as a second arg, 
            # but the failed_request_handler signature in Python only guarantees 'context'.
            # We log generic failure.
            errors_list.append(f"Request failed (handled by error_handler): {error}")
            request.user_data["error_messages"] = errors_list

            log.error(f"Request {request.url} failed. Errors: {errors_list}")
            
            # --- Circuit Breaker: Error Count ---
            if stats_manager:
                await stats_manager.increment("errors")
                if args.maxErrors and await stats_manager.check_threshold("errors", args.maxErrors):
                    log.warning("🛑 Max errors reached. Stopping.")
                    crawler.stop()
            # ------------------------------------
            
            if page:
                try:
                   # Try to get content for analysis
                   content = await process_page(page, request.loaded_url or request.url, log)
                   captcha_detected = await detect_captcha(page, content)
                   
                   if captcha_detected:
                       log.error(f"Captcha detected on {request.url} : {captcha_detected}")
                       
                except Exception as e:
                   log.error(f"Error processing page for failure analysis: {e}")
            
            # Push to error dataset
            try:
                # USE CORRECT STORAGE NAME from local scope
                if crawlee_storage_name != '':
                    error_dataset_name = f"error-{crawlee_storage_name}"
                else:
                    from urllib.parse import urlparse
                    domain_part = urlparse(request.url).netloc.replace("www.", "")
                    safe_domain_name = domain_part.replace('.', '-')
                    error_dataset_name = f"error-{safe_domain_name}"
                
                error_dataset = await Dataset.open(name=error_dataset_name)
                await error_dataset.push_data({
                    "id": getattr(request, 'unique_key', 'unknown'),
                    "url": request.url,
                    "errors": errors_list
                })
            except Exception as e:
                 log.error(f"Failed to push to error dataset: {e}")
        
        # Hook for skipped requests (Robots.txt logging)
        @crawler.on_skipped_request
        async def on_skipped_request(url: str, reason: SkippedReason):
            if reason == 'robots_txt':
                logger.info(f"Bloqué par robots.txt : {url}")

        # Hook for Safety Limit (Point 7 - 5000 items)
        @crawler.pre_navigation_hook
        async def check_global_safety_limit(context: PlaywrightPreNavCrawlingContext):
            if not break_limit:
                try:
                    # Check dataset size
                    dataset = await Dataset.open(name=crawlee_storage_name)
                    data = await dataset.get_data()
                    current_count = len(data.items)
                    
                    if current_count >= 5000:
                        logger.warning("We have reached the limit of 5000 entries. The crawler will be stopped.")
                        # Point 18: Error Code Granularity
                        routes.STOP_REASON = "limitCrawl"
                        crawler.stop()
                except Exception as e:
                    logger.error(f"Error checking safety limit: {e}")
        
        # --- PROACTIVE RESOURCE BLOCKING (Performance Optimization) ---
        # This hook runs BEFORE navigation, blocking heavy resources at the network level
        # before the browser even attempts to load them. This is much faster than
        # blocking after navigation starts.
        @crawler.pre_navigation_hook
        async def block_resources_before_navigation(context: PlaywrightPreNavCrawlingContext):
            """Block heavy resources before navigation to speed up page loading."""
            page = context.page
            
            async def resource_route_handler(route):
                try:
                    req = route.request
                    resource_type = req.resource_type
                    req_url = req.url
                    
                    # Block heavy media and fonts - saves bandwidth and speeds up load
                    if resource_type in ['image', 'media', 'font', 'stylesheet']:
                        await route.abort()
                        return

                    # Block download scripts and tracking pixels
                    if 'download.php' in req_url or 'imp=1' in req_url:
                        await route.abort()
                        return
                    
                    # Block binary file extensions
                    import re
                    if re.search(r'\.(pdf|zip|rar|doc|docx|xls|xlsx|exe|bin|iso|dmg)$', req_url, re.IGNORECASE):
                        await route.abort()
                        return

                    await route.continue_()
                except Exception:
                    # Ignore route errors (e.g. page already closed)
                    pass
            
            try:
                await page.route("**/*", resource_route_handler)
            except Exception as e:
                logger.warning(f"Failed to set up resource blocking: {e}")
        
        # Helper to set stop reason from monitor task
        def set_stop_reason(reason: str):
            routes.STOP_REASON = reason
        
        # Start Monitor Task
        mon_task = asyncio.create_task(monitor_task(crawler, set_stop_reason))

        # Run
        await crawler.run()
        
        logger.info("Crawl finished successfully")
        
        # --- Post-Crawl Logic ---
        stats = crawler.statistics.state
        
        # Save Stats State
        await stats_manager.save_state_to_disk()
        
        # Write callback payload
        if args.method != "test":
            # Determine error status from stats or manual stops
            is_error = ""
            
            # Point 18: Granular Error Reporting
            # Priority 1: Explicit Stop Reason (Manual, Limits)
            if routes.STOP_REASON:
                is_error = routes.STOP_REASON
            # Priority 2: Threshold Breaches
            elif args.maxErrors and await stats_manager.check_threshold("errors", args.maxErrors): is_error = "limitErrors"
            elif args.maxRedirects and await stats_manager.check_threshold("redirects", args.maxRedirects): is_error = "limitRedirects"
            elif args.maxNewUrls and await stats_manager.check_threshold("new_urls", args.maxNewUrls): is_error = "limitNewUrls"
            # Priority 3: Fallback (NodeJS behavior usually defaults here if not finished)
            elif stats.requests_finished >= 5000 and not break_limit:
                 is_error = "limitCrawl"
            
            payload = {
                "id_domaine": job_id,
                "success": stats.requests_finished,
                "failed": stats.requests_failed,
                "isFinished": 1 if stats.requests_finished > 0 else 0,
                "method": args.method,
                "isError": is_error, 
                "storagePath": storage_path
            }
            
            payload_path = os.path.join(storage_path, "_callback_payload.json")
            try:
                with open(payload_path, "w") as f:
                    json.dump(payload, f, indent=2)
                logger.info(f"Callback payload written to {payload_path}")
            except Exception as e:
                logger.error(f"Failed to write callback payload: {e}")
        
            # Exit with error code if crawler stopped due to an error condition (FAILURE ONLY)
            # This ensures the failure webhook is sent only for genuine crashes.
            # Business limits (manual stop, max items) are considered SUCCESS (Finished).
            
            failure_stop_reasons = [
                "stalledZeroProgress", # The crawler got stuck
                "limitErrors",         # Circuit breaker: too many 404s/500s
                "limitRedirects",      # Circuit breaker: redirect loops
                "limitNewUrls"         # Circuit breaker: spider trap detection
            ]
            
            if routes.STOP_REASON in failure_stop_reasons:
                logger.warning(f"Exiting with error code due to failure condition: {routes.STOP_REASON}")
                # Write exit reason before exiting
                write_exit_reason(
                    storage_path, 
                    routes.STOP_REASON, 
                    details=f"Crawler stopped due to: {routes.STOP_REASON}"
                )
                sys.exit(1)
            else:
                # Normal completion or business limit reached
                exit_reason = routes.STOP_REASON if routes.STOP_REASON else "completed"
                write_exit_reason(
                    storage_path, 
                    exit_reason, 
                    details=f"Finished: {stats.requests_finished}, Failed: {stats.requests_failed}",
                    stats={
                        "requests_finished": stats.requests_finished,
                        "requests_failed": stats.requests_failed
                    }
                )
        
    except Exception as e:
        # Capture full traceback for analysis
        tb_str = traceback.format_exc()
        logger.error(f"Crawl failed: {e}")
        logger.error(f"Full traceback:\n{tb_str}")
        
        # Write exit reason with full traceback
        write_exit_reason(
            storage_path, 
            "error", 
            details=str(e),
            tb=tb_str
        )
        sys.exit(1)
        
    finally:
        logger.info("Starting teardown...")
        hb_task.cancel()
        if 'mon_task' in locals(): mon_task.cancel()
        
        # --- PERSISTENCE & CLEANUP ---
        try:
            logger.info("Persisting crawled URLs history...")
             # Retrieve full list from Redis
            final_url_list = []
            async for url in dedup_manager.get_all_urls():
                final_url_list.append(url)
             
            update_urls_crawled(domain, final_url_list)
            logger.info(f"Updated history file with {len(final_url_list)} URLs.")
        except Exception as e:
             logger.error(f"Failed to update history file: {e}")

        # 2. Cleanup Redis
        if dedup_manager: await dedup_manager.cleanup()
        if stats_manager: await stats_manager.cleanup()
        
        try:
            await hb_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received SIGINT, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
