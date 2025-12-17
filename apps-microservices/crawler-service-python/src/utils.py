import asyncio
import logging
import time
from datetime import datetime
import psutil
import os
from playwright.async_api import Page
import logging
import json


logger = logging.getLogger(__name__)

async def wait_and_scroll(
    page: Page,
    url: str,
    log: logging.Logger,
    max_scrolls: int = 100,
    timeout_secs: int = 30
) -> None:
    """
    Simulates infinite scroll behavior on a page until no new content loads.
    
    Args:
        page: Playwright Page object
        url: Current page URL for logging
        log: Logger instance
        max_scrolls: Maximum number of scrolls to perform
        timeout_secs: Maximum time in seconds to spend scrolling
    """
    try:
        # Wait for initial network requests to complete
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # Continue even if networkidle times out (common on heavy sites)
            pass

        # Track page height
        previous_height = await page.evaluate("document.body.scrollHeight")
        scrolls = 0
        start_time = time.time()

        while True:
            # Check limits
            if scrolls >= max_scrolls:
                log.warning(f"Max scrolls ({max_scrolls}) reached for {url}")
                break

            if (time.time() - start_time) > timeout_secs:
                log.warning(f"Scroll timeout ({timeout_secs}s) reached for {url}")
                break

            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # Allow time for new content to load
            await asyncio.sleep(0.75)

            # Get new page height
            new_height = await page.evaluate("document.body.scrollHeight")

            # If height hasn't changed, we've reached the bottom
            if new_height == previous_height:
                break

            previous_height = new_height
            scrolls += 1
            
    except Exception as e:
        log.error(f"Error while scrolling the page: {url} : {str(e)}")

async def process_page(
    page: Page,
    url: str,
    log: logging.Logger,
    max_scrolls: int = 100,
    timeout_secs: int = 30
) -> str:
    """
    Process a page by scrolling through all content and returning the HTML.
    """
    try:
        await wait_and_scroll(page, url, log, max_scrolls, timeout_secs)
        return await page.content()
    except Exception as e:
        log.error(f"Error process_page for {url}: {str(e)}")
        # Return current content even if scrolling failed
        try:
            return await page.content()
        except Exception as inner_e:
            raise Exception(f"Critical error process_page : {str(inner_e)}")

def get_system_stats():
    """
    Get current memory and CPU usage using psutil.
    """
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)
    
    # Get top 3 memory consuming processes (simplified)
    # logic to list top processes can be complex in python one-liner, 
    # for now we return basic stats
    
    return {
        "ram_used_gb": mem.used / (1024**3),
        "ram_total_gb": mem.total / (1024**3),
        "ram_percent": mem.percent,
        "cpu_percent": cpu_percent
    }

def drop_dataset(name: str):
    """
    Drops (deletes) an existing dataset by its name.
    Useful when you need to start fresh before a new crawling session.
    """
    try:
        # In Crawlee Python, we might need to access storage client directly or just remove the folder.
        # For now, let's assume we can't easily drop via SDK static method (API differs).
        # We will remove the directory manually if it's local storage.
        storage_path = os.getenv("CRAWLEE_STORAGE_DIR", "storage")
        dataset_path = os.path.join(storage_path, "datasets", name)
        queue_path = os.path.join(storage_path, "request_queues", name)
        
        if os.path.exists(dataset_path):
            import shutil
            shutil.rmtree(dataset_path)
        
        if os.path.exists(queue_path):
            import shutil
            shutil.rmtree(queue_path)
            
    except Exception as e:
        logger.error(f"Error dropDataset: {e}")

def get_urls_crawled(name: str, historised: bool, drop_data: bool = False) -> list[str]:
    """
    Retrieves all url scraped from a folder request_urls/{domain}
    Manages history rotation.
    """
    folder_name = f"./request_urls/{name}"
    
    try:
        if not os.path.exists(folder_name):
            os.makedirs(folder_name, exist_ok=True)
    except Exception as e:
        logger.error(f"Couldn't create the folder {folder_name}: {e}")
        folder_name = "./request_urls"

    file_urls = f"{folder_name}/{name}.json"

    if drop_data:
        logger.info(f"Dropping the file {file_urls}")
        if os.path.exists(file_urls):
            os.remove(file_urls)

    if os.path.exists(file_urls):
        list_urls = []
        if historised:
            logger.info("The list of urls crawled have been historised")
            date_string = time.strftime("%Y-%m-%d")
            file_historised = f"{folder_name}/{date_string}-{name}.json"
            
            import shutil
            shutil.copyfile(file_urls, file_historised)
            
            # Reset current file
            with open(file_urls, "w") as f:
                json.dump([], f)
        else:
            try:
                with open(file_urls, "r") as f:
                    content = json.load(f)
                    if isinstance(content, list) and len(content) > 0:
                        list_urls = content
            except Exception as e:
                logger.error(f"Error reading history file: {e}")
                
        return list_urls
    else:
        logger.info("First creation of the file list urls")
        with open(file_urls, "w") as f:
            json.dump([], f)
        return []

def update_urls_crawled(name: str, list_urls: list[str]):
    """
    Update the content of the file named "{domaine}.json" in the folder request_urls/{domain}
    """
    folder_name = f"./request_urls/{name}"
    file_urls = f"{folder_name}/{name}.json"

    if not os.path.exists(folder_name):
         os.makedirs(folder_name, exist_ok=True)

    try:
        with open(file_urls, "w") as f:
            json.dump(list_urls, f)
    except Exception as e:
        logger.error(f"Error updating urls crawled: {e}") 

async def detect_captcha(page: Page, content: str) -> str:
    """
    Detects various types of Captchas on the page.
    Returns the name of the captcha detected or empty string.
    """
    captcha_detected = ""
    
    try:
        # Check selectors first
        if await page.query_selector(".g-recaptcha"):
            return "reCAPTCHA V2"
            
        if await page.query_selector(".cf-turnstile"):
            return "Cloudflare Turnstile"
            
        # Check content strings
        if "grecaptcha.execute" in content or "grecaptcha.enterprise.execute" in content:
            return "reCAPTCHA V3"
        elif "api.leminnow.com" in content:
            return "Lemin Captcha"
        elif "geo.captcha-delivery.com" in content:
            return "DataDome Captcha"
        elif "s_s_c_user_id" in content and "s_s_c_session_id" in content and \
             "s_s_c_web_server_sign" in content and "s_s_c_web_server_sign2" in content:
            return "KeyCAPTCHA"
            
    except Exception as e:
        logger.error(f"Error checking captcha: {e}")
        
    return captcha_detected 

def is_stopped_manually(domain: str, historised: bool = False) -> bool:
    """
    Checks if a file named "{domain}.txt" exists in the 'stopper' directory.
    If it exists, indicates the crawler should stop.
    """
    stopper_file = f"stopper/{domain}.txt"
    try:
        if os.path.exists(stopper_file):
            if historised:
                logger.info("The crawler has been stopped manually.")
                history_file = f"stopper/history-{domain}.txt"
                with open(history_file, "a") as f:
                     date_str = datetime.now().isoformat()
                     f.write(f"- Date arrêt : {date_str}\n")
                try:
                    os.remove(stopper_file)
                except Exception as e:
                     logger.warning(f"Could not remove stopper file: {e}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking stopper file: {e}")
        return False

def attach_file_logger(file_name: str):
    """
    Attaches a FileHandler to the root logger to save logs to a file.
    Follows the structure: ./logs/YYYY/MM/file_name
    """
    try:
        now = datetime.now()
        folder_date = f"{now.year}/{now.month:02d}"
        folder_path = f"./logs/{folder_date}"
        
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            
        file_path = f"{folder_path}/{file_name}"
        
        file_handler = logging.FileHandler(file_path, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(file_handler)
        logging.info(f"File logger attached: {file_path}")
        
    except Exception as e:
        print(f"Failed to attach file logger: {e}") # Use print as logger might not be ready or error is in logging system 

def ensure_alias_symlink(sanitized_name: str, original_name: str, base_dirs: list[str]):
    """
    Creates a symlink from original_name to sanitized_name in provided base directories
    to ensure compatibility with legacy systems expecting the original name (e.g. with dots).
    """
    if sanitized_name == original_name:
        return

    for base_dir in base_dirs:
        try:
            if not os.path.exists(base_dir):
                continue
            
            # Correct paths: we are inside base_dir
            # Structure: ./storage/datasets/sanitized-name
            # We want:   ./storage/datasets/original.name -> sanitized-name
            
            target_path = os.path.join(base_dir, sanitized_name)
            link_path = os.path.join(base_dir, original_name)
            
            if os.path.exists(target_path) and not os.path.exists(link_path):
                os.symlink(sanitized_name, link_path)
                logger.info(f"Created symlink alias: {link_path} -> {sanitized_name}")
        except Exception as e:
            logger.warning(f"Failed to create symlink alias in {base_dir}: {e}")
