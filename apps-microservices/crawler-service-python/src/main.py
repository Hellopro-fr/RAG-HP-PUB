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

async def main():
    parser = argparse.ArgumentParser(description="Python Crawler Service")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--storagePath", required=True)
    parser.add_argument("--callbackUrl", required=True)
    parser.add_argument("--breaklimit", default="False")
    parser.add_argument("--proxyapify", default=None)
    
    args = parser.parse_args()
    
    domain = args.domain
    site = args.site
    job_id = args.id
    storage_path = args.storagePath
    proxy_apify_password = args.proxyapify
    
    break_limit = str(args.breaklimit).lower() == 'true'

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

        # Run
        await crawler.run([site])
        
        logger.info("Crawl finished successfully")
        
    except Exception as e:
        logger.error(f"Crawl failed: {e}")
        sys.exit(1)
    finally:
        hb_task.cancel()
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
