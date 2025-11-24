import os
import shutil
import asyncio
import httpx
import logging
import json
from google.cloud import storage
from common_utils.redis import cache_service
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def run_test():
    logger.info("Starting Safe GCS Archive Test...")

    # 1. Identify an existing finished crawl
    storage_path = settings.CRAWLER_STORAGE_PATH
    if not os.path.exists(storage_path):
        logger.error(f"Storage path {storage_path} does not exist.")
        return

    candidates = []
    for item in os.listdir(storage_path):
        full_path = os.path.join(storage_path, item)
        if os.path.isdir(full_path) and not item.startswith("test-archive-"):
            # Check if it looks like a valid crawl (has logs or marker)
            if os.path.exists(os.path.join(full_path, "crawler.log")) or os.path.exists(os.path.join(full_path, "_completion_marker.json")):
                candidates.append(item)

    if not candidates:
        logger.error("No existing crawl jobs found in storage to use as a template.")
        return

    original_id = candidates[0]
    test_id = f"test-archive-{original_id}"
    original_path = os.path.join(storage_path, original_id)
    test_path = os.path.join(storage_path, test_id)

    logger.info(f"Selected original crawl '{original_id}'. Creating test clone '{test_id}'...")

    # 2. Clone storage directory
    if os.path.exists(test_path):
        shutil.rmtree(test_path)
    shutil.copytree(original_path, test_path)
    logger.info(f"Cloned storage to {test_path}")

    # 3. Inject temporary job into Redis
    await cache_service.init_redis_pool()
    job_key = f"crawl_job:{test_id}"
    job_data = {
        "crawl_id": test_id,
        "status": "finished",
        "domain": "test-domain.com",
        "start_url": "http://test-domain.com",
        "start_time": "2023-01-01T00:00:00",
        "storage_path": test_path,
        "callback_url": None,
        "failure_callback_url": None
    }
    await cache_service.set_json(job_key, job_data)
    logger.info(f"Injected job '{test_id}' into Redis.")

    try:
        # 4. Call archive endpoint
        async with httpx.AsyncClient() as client:
            # Assuming running inside container on port 8503
            url = f"http://localhost:8503/crawler/archive/{test_id}"
            logger.info(f"Calling API: POST {url}")
            response = await client.post(url, timeout=60.0)
            
            if response.status_code != 200:
                logger.error(f"API call failed: {response.status_code} - {response.text}")
                return
            
            logger.info(f"API success: {response.json()}")

        # 5. Verify GCS Upload
        bucket_name = settings.GCS_BUCKET_NAME
        blob_name = f"{test_id}.tar.gz"
        
        logger.info(f"Verifying GCS upload in bucket '{bucket_name}'...")
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if not blob.exists():
            logger.error("GCS Blob does not exist! Test Failed.")
            return
        
        logger.info("GCS Blob found.")

        # 6. Verify Local Cleanup
        logger.info("Verifying local cleanup...")
        files_remaining = os.listdir(test_path)
        logger.info(f"Files remaining in {test_path}: {files_remaining}")
        
        expected_files = {'crawler.log', '_callback_payload.json', '_completion_marker.json'}
        # Note: os.listdir returns filenames, but our cleanup logic keeps directories if they are not empty (though it tries to remove them).
        # The cleanup logic in manager: removes files NOT in keep list. Removes dirs if empty.
        
        # Let's check if any forbidden files exist
        forbidden_found = False
        for root, dirs, files in os.walk(test_path):
            for f in files:
                if f not in expected_files:
                    logger.error(f"Found unexpected file: {f}")
                    forbidden_found = True
        
        if forbidden_found:
             logger.error("Local cleanup failed: Unexpected files remain.")
        else:
             logger.info("Local cleanup passed.")

    except Exception as e:
        logger.error(f"Test execution failed: {e}", exc_info=True)

    finally:
        # 7. Teardown
        logger.info("Starting Teardown...")
        
        # Delete from GCS
        try:
            if 'blob' in locals() and blob.exists():
                blob.delete()
                logger.info("Deleted test blob from GCS.")
        except Exception as e:
            logger.error(f"Failed to delete GCS blob: {e}")

        # Delete local dir
        try:
            if os.path.exists(test_path):
                shutil.rmtree(test_path)
                logger.info("Deleted local test directory.")
        except Exception as e:
            logger.error(f"Failed to delete local directory: {e}")

        # Delete Redis key
        try:
            await cache_service.delete_key(job_key)
            logger.info("Deleted Redis key.")
            await cache_service.close_redis_pool()
        except Exception as e:
            logger.error(f"Failed to delete Redis key: {e}")

    logger.info("Test Complete.")

if __name__ == "__main__":
    asyncio.run(run_test())
