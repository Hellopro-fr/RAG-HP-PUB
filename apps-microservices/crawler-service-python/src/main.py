import asyncio
import argparse
import sys
import os
import json
import logging
import signal
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from crawlee.crawlers import PlaywrightCrawler
from crawlee.browsers import BrowserPool, PlaywrightBrowserPlugin
from crawlee.fingerprint_suite import DefaultFingerprintGenerator
from crawlee.proxy_configuration import ProxyConfiguration
from crawlee.configuration import Configuration
from crawlee.storages import Dataset, RequestQueue
from redis.asyncio import Redis

import routes
from state import DedupManager, StatsManager
from utils import get_system_stats, get_urls_crawled, update_urls_crawled, drop_dataset, is_stopped_manually, attach_file_logger, ensure_alias_symlink, load_dataset_urls_generator

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

# Load Env
load_dotenv()

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

async def monitor_task(crawler: PlaywrightCrawler):
    """
    Monitors crawler health and progress.
    Replaces the complex 'checkQueue' logic from Node.js with a simple stall detector.
    """
    last_finished = 0
    stalled_checks = 0
    
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
                if stalled_checks >= 10: # 5 minutes without progress
                    logger.warning(f"⚠️ Crawler might be stalled! No progress for 5 minutes. (Processed: {total})")
            else:
                stalled_checks = 0
                last_finished = finished
                
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
    parser.add_argument("--maxConcurrency", default=5, type=int)
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
    
    # Configure Routes Global Vars
    routes.SKIP_QUESTION_MARK = str(args.skipquestionmark).lower() == 'true'
    routes.SKIP_DIEZ = str(args.skipdiez).lower() == 'true'
    routes.DOMAIN = domain
    routes.BASE_URL = site
    routes.TO_KEEP_CUSTOM = to_keep
    routes.TO_REMOVE_CUSTOM = to_remove
    
    # Inject Limits
    routes.max_errors = args.maxErrors
    routes.max_redirects = args.maxRedirects
    routes.max_new_urls = args.maxNewUrls

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

    # Sanitize storage name
    crawlee_storage_name = domain.replace('.', '-')
    routes.CRAWLEE_STORAGE_NAME = crawlee_storage_name
    
    # Symlink aliases
    CRAWLEE_STORAGE_DIR = os.getenv("CRAWLEE_STORAGE_DIR", "storage")
    base_queues = os.path.join(CRAWLEE_STORAGE_DIR, "request_queues")
    base_datasets = os.path.join(CRAWLEE_STORAGE_DIR, "datasets")
    base_kvs = os.path.join(CRAWLEE_STORAGE_DIR, "key_value_stores")
    ensure_alias_symlink(crawlee_storage_name, domain, [base_queues, base_datasets, base_kvs])

    is_historised = False
    if drop_data:
        logger.info("Dropping datasets and request queue...")
        try:
           # We use our custom drop_dataset logic
           drop_dataset(domain)
           drop_dataset(f"error-{domain}")
           drop_dataset(f"nfr-{domain}")
           is_historised = True
        except Exception as e:
           logger.warning(f"Failed to drop datasets: {e}")
    # ------------------------------------

    # --- STATE MANAGEMENT INIT ---
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Initialize Managers
    dedup_manager = DedupManager(redis_url, job_id)
    stats_manager = StatsManager(redis_url, job_id, storage_path)
    
    # Inject into routes
    routes.dedup_manager = dedup_manager
    routes.stats_manager = stats_manager
    
    # Load Stats if resuming
    await stats_manager.load_state_from_disk()
    
    # Load Historical URLs into Redis (Cold Storage -> Hot Redis)
    # Note: We pass `drop_data` here because get_urls_crawled handles file removal if True
    history_urls = get_urls_crawled(domain, is_historised, drop_data) 
    if history_urls:
        logger.info(f"Seeding {len(history_urls)} historical URLs into Redis Deduplication...")
        await dedup_manager.load_from_list(history_urls)

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
             await request_queue.add_request({
                 "url": url,
                 "userData": {"is_existing": True}
             })
             count += 1
             if count % 1000 == 0:
                 logger.info(f"Seeded {count} URLs...")
                 
        logger.info(f"Finished seeding {count} URLs from previous crawl.")
        
    elif await request_queue.is_empty():
        # Standard Seed
        logger.info("Seeding standard start URL...")
        await request_queue.add_request({"url": site, "userData": {"is_existing": False}})
        # Don't add to Dedup here, let request_handler handle the add for proper counting
    
    # Start Heartbeat
    hostname = os.uname().nodename
    hb_task = asyncio.create_task(heartbeat_task(redis_url, job_id, domain, hostname))

    # Configure Proxy
    proxy_configuration = None
    if proxy_apify_password:
        proxy_url = f"http://auto:{proxy_apify_password}@proxy.apify.com:8000"
        proxy_configuration = ProxyConfiguration(proxy_urls=[proxy_url])

    try:
        # Initialize Crawler
        # Configure Browser Pool with Fingerprints
        fingerprint_generator = DefaultFingerprintGenerator()
        
        browser_plugin = PlaywrightBrowserPlugin(
            browser_type='chromium',
            fingerprint_generator=fingerprint_generator,
            browser_launch_options={
                "headless": True,
                "args": ["--no-sandbox", "--disable-setuid-sandbox"]
            }
        )
        browser_pool = BrowserPool(plugins=[browser_plugin], retire_browser_after_page_count=10)

        crawler = PlaywrightCrawler(
            request_handler=routes.router,
            request_manager=request_queue,
            max_requests_per_crawl=5000 if not break_limit else None,
            browser_pool=browser_pool,
            proxy_configuration=proxy_configuration,
        )
        
        # Note: Crawlee Python auto-manages concurrency via AutoscaledPool
        # The --maxConcurrency argument is available but not directly settable in current version
        # Concurrency adapts based on CPU, memory, and event loop metrics
        # Browser rotation is handled via retire_browser_after_page_count=10 in BrowserPool
        
        # Assign error handler manually
        crawler.failed_request_handler = routes.error_handler
        
        # Start Monitor Task
        mon_task = asyncio.create_task(monitor_task(crawler))

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
            # Check if we stopped due to thresholds
            if args.maxErrors and await stats_manager.check_threshold("errors", args.maxErrors): is_error = "limitErrors"
            elif args.maxRedirects and await stats_manager.check_threshold("redirects", args.maxRedirects): is_error = "limitRedirects"
            elif args.maxNewUrls and await stats_manager.check_threshold("new_urls", args.maxNewUrls): is_error = "limitNewUrls"
            
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
        
    except Exception as e:
        logger.error(f"Crawl failed: {e}")
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
