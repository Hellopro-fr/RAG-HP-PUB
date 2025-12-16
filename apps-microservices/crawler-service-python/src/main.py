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
from crawlee.storages import Dataset
from redis.asyncio import Redis

from routes import router
from utils import get_system_stats

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
                "cpu": stats["cpu_percent"],
                "ram": stats["ram_used_gb"] * 1024 * 1024 * 1024, # Convert GB to Bytes for compat
                "totalRam": stats["ram_total_gb"] * 1024 * 1024 * 1024,
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
            if not crawler.running:
                break
                
            stats = crawler.statistics.state
            finished = stats.requests_finished
            failed = stats.requests_failed
            total = finished + failed
            
            logger.info(f"Health Check: Finished={finished}, Failed={failed}, Queued=Unknown (managed by Crawlee)")
            
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
    parser.add_argument("--breaklimit", default="False")
    parser.add_argument("--proxyapify", default=None)
    parser.add_argument("--dropdata", default="False")
    parser.add_argument("--method", default="prod")
    parser.add_argument("--skipquestionmark", default="False")
    parser.add_argument("--skipdiez", default="False")
    
    args = parser.parse_args()
    
    domain = args.domain
    site = args.site
    job_id = args.id
    storage_path = args.storagePath
    proxy_apify_password = args.proxyapify
    
    break_limit = str(args.breaklimit).lower() == 'true'
    drop_data = str(args.dropdata).lower() == 'true'
    
    import routes
    routes.SKIP_QUESTION_MARK = str(args.skipquestionmark).lower() == 'true'
    routes.SKIP_DIEZ = str(args.skipdiez).lower() == 'true'
    
    method = args.method

    logger.info(f"Starting crawler for {domain} ({site}) in {storage_path}")

    # Change CWD to storage path
    try:
        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)
        os.chdir(storage_path)
        logger.info(f"Changed working directory to: {os.getcwd()}")
    except Exception as e:
        logger.error(f"Failed to change CWD: {e}")
        sys.exit(1)

    # Load History & Drop Data logic
    from utils import get_urls_crawled, drop_dataset, update_urls_crawled, is_stopped_manually
    from routes import router, error_handler
    import routes
    
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

    # Load previously crawled URLs
    # This populates the Set in routes.py
    history = get_urls_crawled(domain, is_historised, drop_data)
    routes.all_urls_crawled = set(history)
    logger.info(f"Loaded {len(routes.all_urls_crawled)} URLs from history.")

    # Configure Crawlee
    # Note: Crawlee Python automatic storage configuration relies on CRAWLEE_STORAGE_DIR env var
    # or it defaults to ./storage within CWD. Since we changed CWD, it should be fine.
    
    # Configure Proxy
    proxy_configuration = None
    if proxy_apify_password:
        # Construct Apify Proxy URL
        # Format: http://auto:{password}@proxy.apify.com:8000
        proxy_url = f"http://auto:{proxy_apify_password}@proxy.apify.com:8000"
        logger.info(f"Configuring Apify Proxy (auto/port 8000)")
        
        try:
           proxy_configuration = ProxyConfiguration(proxy_urls=[proxy_url])
        except Exception as e:
           logger.error(f"Failed to create ProxyConfiguration: {e}")
           sys.exit(1)

    # Set Global Domain for Routes
    routes.DOMAIN = domain

    # Start Heartbeat
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    hostname = os.uname().nodename
    hb_task = asyncio.create_task(heartbeat_task(redis_url, job_id, domain, hostname))

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
        
        browser_pool = BrowserPool(plugins=[browser_plugin])

        crawler = PlaywrightCrawler(
            request_handler=router,
            max_requests_per_crawl=5000 if not break_limit else None,
            browser_pool=browser_pool,
            proxy_configuration=proxy_configuration,
        )
        # Assign error handler manually 
        crawler.failed_request_handler = error_handler
        
        # Start Monitor Task
        mon_task = asyncio.create_task(monitor_task(crawler))

        # Run
        await crawler.run([site])
        
        logger.info("Crawl finished successfully")
        # --- Post-Crawl Logic ---
        stats = crawler.statistics.state
        
        # Update history file with new URLs
        if len(routes.all_urls_crawled) > 0:
            update_urls_crawled(domain, list(routes.all_urls_crawled))
            
        # Write callback payload
        if method != "test":
            payload = {
                "id_domaine": job_id,
                "success": stats.requests_finished,
                "failed": stats.requests_failed,
                "isFinished": 1 if stats.requests_finished > 0 else 0, # Simple check for POC
                "method": method,
                "isError": "", # TODO: Add granular error codes (limitCrawl, etc.)
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
        hb_task.cancel()
        if 'mon_task' in locals():
            mon_task.cancel()
        try:
            await hb_task
            if 'mon_task' in locals():
               await mon_task
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
