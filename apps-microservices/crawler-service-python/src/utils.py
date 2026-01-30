import asyncio
import logging
import time
from datetime import datetime
import psutil
import os
from playwright.async_api import Page
import logging
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Optional, Union

# Imports for Reclaim Logic
from crawlee.storages import Dataset, RequestQueue


logger = logging.getLogger(__name__)

async def wait_and_scroll(
    page: Page,
    url: str,
    log: logging.Logger,
    max_scrolls: int = 15,  # Reduced from 100 - most content loads in first few scrolls
    timeout_secs: int = 10  # Reduced from 30 - prevents hanging on slow pages
) -> None:
    """
    Simulates infinite scroll behavior on a page until no new content loads.
    Optimized for speed with reduced defaults.
    
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
                log.debug(f"Max scrolls ({max_scrolls}) reached for {url}")
                break

            if (time.time() - start_time) > timeout_secs:
                log.debug(f"Scroll timeout ({timeout_secs}s) reached for {url}")
                break

            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # Reduced from 0.75s to 0.3s - faster scrolling
            await asyncio.sleep(0.3)

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
    
    # Get top 3 memory consuming processes (mimicking Node.js logic)
    top_processes = []
    try:
        import subprocess
        # Command: ps aux --sort=-rss | head -n 4 | tail -n 3
        # Output cols: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        cmd = "ps aux --sort=-rss | head -n 4 | tail -n 3"
        output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
        
        for line in output.split('\n'):
            parts = line.split()
            if len(parts) > 10:
                # RSS is usually column 5 (index 5) or 6 depending on ps version, but usually 6th col (index 5)
                # USER(0) PID(1) %CPU(2) %MEM(3) VSZ(4) RSS(5)
                rss_kb = int(parts[5])
                # Command starts from index 10
                command = " ".join(parts[10:])[:30] # Truncate to 30 chars
                
                top_processes.append({
                    "name": command,
                    "ram": rss_kb * 1024 # Convert KB to Bytes
                })
    except Exception as e:
        logger.error(f"Failed to get top processes: {e}")

    
    # Defaults (Host memory)
    total_mem = mem.total
    used_mem = mem.used
    
    # Try reading Cgroup memory limits (for Docker container accuracy)
    try:
        # Cgroup V2
        cgroup_max = "/sys/fs/cgroup/memory.max"
        cgroup_current = "/sys/fs/cgroup/memory.current"
        
        # Cgroup V1
        cgroup_limit_v1 = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
        cgroup_usage_v1 = "/sys/fs/cgroup/memory/memory.usage_in_bytes"

        if os.path.exists(cgroup_max):
            with open(cgroup_max, "r") as f:
                val = f.read().strip()
                if val != "max":
                    total_mem = int(val)
            with open(cgroup_current, "r") as f:
                used_mem = int(f.read().strip())
        elif os.path.exists(cgroup_limit_v1):
             with open(cgroup_limit_v1, "r") as f:
                val = f.read().strip()
                # Unset limit is often very larg number
                if int(val) < 900000000000000: # reasonable check
                    total_mem = int(val)
             with open(cgroup_usage_v1, "r") as f:
                used_mem = int(f.read().strip())
                
    except Exception:
        # Fallback to psutil (host stats)
        pass

    return {
        "ram_used_gb": used_mem / (1024**3),
        "ram_total_gb": total_mem / (1024**3),
        "ram_percent": (used_mem / total_mem) * 100 if total_mem > 0 else 0,
        "cpu_percent": cpu_percent,
        "top_processes": top_processes
    }

async def drop_dataset(name: str):
    """
    Drops (deletes) an existing dataset by its name.
    Useful when you need to start fresh before a new crawling session.
    It manually deletes the directory if using local storage to ensure
    both symlinks and real directories are handled.
    """
    try:
        # In Crawlee Python, we might need to access storage client directly or just remove the folder.
        # We will remove the directory manually if it's local storage.
        storage_path = os.getenv("CRAWLEE_STORAGE_DIR", "storage")
        
        # Paths to clean
        targets = [
            os.path.join(storage_path, "datasets", name),
            os.path.join(storage_path, "request_queues", name),
            os.path.join(storage_path, "key_value_stores", name), # Also clean KVS
            # Also clean request_urls (check both root and inside storage for safety/consistency)
            os.path.join("request_urls", name),
            os.path.join(storage_path, "request_urls", name)
        ]
        
        for target_path in targets:
            if os.path.exists(target_path) or os.path.islink(target_path):
                import shutil
                try:
                    if os.path.islink(target_path):
                        os.unlink(target_path)
                        logger.info(f"Unlinked symlink: {target_path}")
                    else:
                        shutil.rmtree(target_path)
                        logger.info(f"Removed directory: {target_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove {target_path}: {e}")
            
    except Exception as e:
        logger.error(f"Error dropDataset: {e}")

def get_urls_crawled(name: str, historised: bool, drop_data: bool = False) -> list[str]:
    """
    Retrieves all url scraped from a folder request_urls/{domain}.
    Used now primarily for seeding Redis.
    """
    folder_name = f"./request_urls/{name}"
    
    # CHECK LEGACY PATH
    original_domain_guess = name.replace('-', '.')
    legacy_folder = f"./request_urls/{original_domain_guess}"
    
    if os.path.exists(legacy_folder):
        logger.info(f"Detected legacy history folder: {legacy_folder}")
        folder_name = legacy_folder
        name = original_domain_guess # Update name to match file inside
    
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

def load_dataset_urls_generator(previous_id: str, domain: str):
    """
    Generator that efficiently yields URLs from a previous crawl's dataset.
    Scans the storage directory structure to find the datasets.
    """
    # Base storage root (assuming we are in /app/storage/{current_id} when this runs, 
    # we need to go up to /app/storage/{previous_id})
    # But usually we can just use absolute paths if provided or assume relative to /app/storage
    
    # We are in CWD = /app/storage/{current_id}
    # So previous is ../{previous_id}
    
    base_storage = os.path.abspath("..")
    prev_job_path = os.path.join(base_storage, previous_id)
    
    if not os.path.isdir(prev_job_path):
        logger.error(f"Previous job storage not found at {prev_job_path}")
        return

    # Check for sanitized name vs original
    crawlee_base = os.path.join(prev_job_path, "storage", "datasets")
    dataset_path = os.path.join(crawlee_base, domain)
    
    if not os.path.isdir(dataset_path):
        sanitized = domain.replace('.', '-')
        dataset_path = os.path.join(crawlee_base, sanitized)
    
    if not os.path.isdir(dataset_path):
        logger.error(f"Dataset for domain {domain} not found in {prev_job_path}")
        return

    logger.info(f"Loading URLs from previous dataset: {dataset_path}")
    
    try:
        # scandir is more efficient for large directories
        with os.scandir(dataset_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith('.json') and not entry.name.startswith('__'):
                    try:
                        with open(entry.path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if 'url' in data:
                                yield data['url']
                    except Exception as e:
                        logger.warning(f"Error reading dataset file {entry.name}: {e}")
    except Exception as e:
        logger.error(f"Error iterating dataset directory: {e}")

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
    
    Handles 4 scenarios:
    A) New Crawl: sanitized exists, original doesn't -> create original -> sanitized
    B) Resume Legacy: original exists (real dir), sanitized doesn't -> create sanitized -> original
    C) Conflict: Both exist as real dirs -> backup smaller, link to larger
    D) Broken Symlink: Either path is a broken symlink -> remove and retry
    """
    if sanitized_name == original_name:
        return

    for base_dir in base_dirs:
        try:
            if not os.path.exists(base_dir):
                # Base dir might not exist yet (lazy creation by Crawlee)
                continue
            
            logger.info(f"Checking symlinks in {os.path.abspath(base_dir)}...")
            
            target_path = os.path.join(base_dir, sanitized_name)
            link_path = os.path.join(base_dir, original_name)
            
            # --- Scenario D: Broken Symlink Cleanup ---
            # Check for broken symlinks FIRST and remove them
            if os.path.islink(target_path) and not os.path.exists(target_path):
                logger.warning(f"Removing broken symlink: {target_path}")
                os.unlink(target_path)
            if os.path.islink(link_path) and not os.path.exists(link_path):
                logger.warning(f"Removing broken symlink: {link_path}")
                os.unlink(link_path)
            
            # Re-check existence after cleanup
            target_exists = os.path.exists(target_path)
            link_exists = os.path.exists(link_path)
            target_is_link = os.path.islink(target_path)
            link_is_link = os.path.islink(link_path)
            target_is_dir = os.path.isdir(target_path)
            link_is_dir = os.path.isdir(link_path)
            
            # --- Scenario A: New Crawl (Legacy Alias) ---
            # Create link: prodealcenter.fr -> prodealcenter-fr
            if target_exists and not link_exists:
                os.symlink(sanitized_name, link_path)
                logger.info(f"Created symlink alias: {link_path} -> {sanitized_name}")
                
            # --- Scenario B: Resume Legacy Crawl (Reverse Alias) ---
            # Create link: prodealcenter-fr -> prodealcenter.fr
            elif link_exists and not target_exists:
                 if link_is_dir and not link_is_link:
                     os.symlink(original_name, target_path)
                     logger.info(f"Created REVERSE symlink for resume: {target_path} -> {original_name}")

            # --- Scenario C: Conflict Resolution (Both dirs exist) ---
            elif link_is_dir and target_is_dir and not target_is_link and not link_is_link:
                try:
                    count_target = len(os.listdir(target_path))
                    count_link = len(os.listdir(link_path))
                    
                    # Use RATIO-based comparison: if one has 10x more files, it's the real one
                    # Also handle edge case where one is empty
                    if count_link > 0 and (count_target == 0 or count_link / max(count_target, 1) > 5):
                        logger.warning(f"Conflict: '{sanitized_name}' ({count_target}) vs '{original_name}' ({count_link}). Backing up smaller.")
                        
                        import shutil
                        backup_name = f"{sanitized_name}_backup_{int(datetime.now().timestamp())}"
                        backup_path = os.path.join(base_dir, backup_name)
                        os.rename(target_path, backup_path)
                        
                        os.symlink(original_name, target_path)
                        logger.info(f"Fixed: {target_path} -> {original_name} (backup: {backup_name})")
                    elif count_target > 0 and (count_link == 0 or count_target / max(count_link, 1) > 5):
                        logger.warning(f"Conflict: '{original_name}' ({count_link}) vs '{sanitized_name}' ({count_target}). Backing up smaller.")
                        
                        import shutil
                        backup_name = f"{original_name}_backup_{int(datetime.now().timestamp())}"
                        backup_path = os.path.join(base_dir, backup_name)
                        os.rename(link_path, backup_path)
                        
                        os.symlink(sanitized_name, link_path)
                        logger.info(f"Fixed: {link_path} -> {sanitized_name} (backup: {backup_name})")
                    else:
                        logger.warning(f"Conflict: Both dirs have similar file counts ({count_target} vs {count_link}). Manual intervention may be needed.")
                except Exception as inner_e:
                     logger.error(f"Failed to resolve directory conflict: {inner_e}")
                     
        except Exception as e:
            logger.warning(f"Failed to create symlink alias in {base_dir}: {e}")

def process_url(
    url: str,
    skip_question_mark: bool,
    skip_diez: bool,
    to_keep: Optional[list[str]] = None,
    to_remove: Optional[list[str]] = None
) -> str:
    """
    Process a URL to filter query parameters and remove hash fragments.
    Ported from Node.js processUrl function.
    """
    # Default parameters to keep if no custom lists provided
    default_parameters_to_keep = ["page", "id", "lang"]

    # Validate parameters
    if to_keep and to_remove:
        raise ValueError("Cannot specify both toKeep and toRemove parameters")

    try:
        # Parse URL
        parsed = urlparse(url)
        scheme, netloc, path, params, query, fragment = parsed
        
        # 1. Handle Hash (#)
        # In Node: if (url.includes("#")) ... if (skipDiez) hashPart = ""
        if skip_diez:
            fragment = ""
        
        # 2. Handle Query (?)
        # In Node: if (skipQuestionMark && baseUrlPart.includes("?"))
        if skip_question_mark and query:
            query_dict = parse_qs(query, keep_blank_values=True)
            new_query_dict = {}
            
            if to_keep:
                # Keep only specified parameters
                for key in query_dict:
                    if key in to_keep:
                        new_query_dict[key] = query_dict[key]
            
            elif to_remove:
                # Remove specified parameters
                new_query_dict = query_dict.copy()
                for key in to_remove:
                    if key in new_query_dict:
                        del new_query_dict[key]
            
            else:
                # Use default parameters
                for key in query_dict:
                    if key in default_parameters_to_keep:
                        new_query_dict[key] = query_dict[key]
            
            # Rebuild query string
            query = urlencode(new_query_dict, doseq=True)
            
        # Reconstruct URL
        return urlunparse((scheme, netloc, path, params, query, fragment))
        
    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        return url
    
def manage_french_detection_method(
    name: str,
    check_french_method: Optional[str] = None
) -> Union[str, Exception]:
    """
    Manages French language detection method storage for domains.
    Stores/Retrieves the method that successfully detected the language (e.g. "langHtml").
    """
    try:
        storage_path = f"./storage/miscellaneous/{name}"
        file_path = f"{storage_path}/{name}.json"
        
        # Create directory if needed
        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

        # If checkFrenchMethod is provided, we want to store it
        if check_french_method:
            with open(file_path, "w", encoding='utf-8') as f:
                json.dump({"method": check_french_method}, f, indent=2)
            return check_french_method

        # If no checkFrenchMethod provided, try to read existing file
        if os.path.exists(file_path):
            with open(file_path, "r", encoding='utf-8') as f:
                content = json.load(f)
                return content.get("method")

        # If no file and no method provided, return Exception (to be handled by caller)
        return Exception(f"No French detection method stored for domain {name}")

    except Exception as e:
        return e

async def get_scraping_data(name: str):
    """
    Retrieves data from a dataset.
    Wraps Dataset.open(name).get_data() to match Node.js helper style.
    """
    try:
        dataset = await Dataset.open(name=name)
        return await dataset.get_data()
    except Exception as e:
        # If dataset doesn't exist or error, return None
        logger.warning(f"Error accessing dataset {name}: {e}")
        return None

async def reclaim_failed_requests(queue_name: str, request_queue: RequestQueue):
    """
    Reclaims failed requests from error dataset for retry processing.
    Matches the Node.js reclaimFailedRequest logic.
    """
    # In Node, error dataset is named `error-${name}`
    error_dataset_name = f"error-{queue_name}"
    
    logger.info(f"Checking for failed requests in {error_dataset_name}...")

    data = await get_scraping_data(error_dataset_name)

    if not data or not data.items:
        return

    logger.info(f"Found {len(data.items)} failed requests to reclaim.")

    reclaimed_count = 0
    for item in data.items:
        request_id = item.get("id")
        if not request_id:
            continue

        try:
            # Fetch original request from queue
            request = await request_queue.get_request(request_id)
            
            if request:
                # Reset counters
                request.retry_count = 0
                request.handled_at = None # Clear handled status
                
                # Reclaim (move back to pending)
                await request_queue.reclaim_request(request)
                reclaimed_count += 1
        except Exception as e:
             logger.error(f"Failed to reclaim request {request_id}: {e}")

    logger.info(f"Successfully reclaimed {reclaimed_count} requests.")
    
    # Drop the error dataset after reclaiming
    await drop_dataset(error_dataset_name)

def sanitize_queue_on_disk(
    queue_name: str,
    skip_question_mark: bool,
    skip_diez: bool,
    to_keep: Optional[list[str]] = None,
    to_remove: Optional[list[str]] = None
):
    """
    Parse and modify JSON files from request queues to clean URLs.
    This runs 'offline' before the queue is loaded into memory by Crawlee.
    """
    storage_path = os.getenv("CRAWLEE_STORAGE_DIR", "storage")
    queue_path = os.path.join(storage_path, "request_queues", queue_name)

    if not os.path.exists(queue_path):
        return

    logger.info(f"Sanitizing queue on disk: {queue_path}")
    count = 0

    try:
        # os.scandir is efficient for iterating directories
        with os.scandir(queue_path) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith('.json'):
                    try:
                        # Read file
                        with open(entry.path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        original_url = data.get('url')
                        if not original_url:
                            continue

                        # Process URL
                        new_url = process_url(
                            original_url,
                            skip_question_mark,
                            skip_diez,
                            to_keep,
                            to_remove
                        )

                        if new_url != original_url:
                            # Update outer URL
                            data['url'] = new_url
                            # FIX: Update outer UniqueKey
                            data['uniqueKey'] = new_url
                            
                            # Update nested json string if present (Crawlee internal)
                            if 'json' in data:
                                try:
                                    inner = json.loads(data['json'])
                                    if 'url' in inner:
                                        inner['url'] = new_url
                                    # FIX: Update inner UniqueKey
                                    if 'uniqueKey' in inner:
                                        inner['uniqueKey'] = new_url
                                    
                                    # Re-serialize inner JSON
                                    data['json'] = json.dumps(inner)
                                except Exception:
                                    pass # Ignore inner parsing errors if format differs

                            # Write back modified content
                            with open(entry.path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, indent=4)
                            
                            count += 1
                    except Exception as e:
                        logger.warning(f"Failed to sanitize file {entry.name}: {e}")
        
        if count > 0:
            logger.info(f"Sanitized {count} URLs in queue on disk.")

    except Exception as e:
        logger.error(f"Error iterating queue directory: {e}")
