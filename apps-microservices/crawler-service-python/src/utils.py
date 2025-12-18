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
            if os.path.islink(dataset_path):
                os.unlink(dataset_path)
            else:
                shutil.rmtree(dataset_path)
        
        if os.path.exists(queue_path):
            import shutil
            if os.path.islink(queue_path):
                os.unlink(queue_path)
            else:
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
                logger.warning(f"Symlink Base Dir NOT FOUND: {base_dir}")
                continue
            
            logger.info(f"Checking symlinks in {os.path.abspath(base_dir)}...")
            # Correct paths: we are inside base_dir
            # Structure: ./storage/datasets/sanitized-name
            # We want:   ./storage/datasets/original.name -> sanitized-name
            
            target_path = os.path.join(base_dir, sanitized_name)
            link_path = os.path.join(base_dir, original_name)
            
            # Scenario A: New Crawl (Legacy Alias)
            # Create link: prodealcenter.fr -> prodealcenter-fr
            # Condition: Target (sanitized) exists, Link (original) does NOT exist
            if os.path.exists(target_path) and not os.path.exists(link_path):
                os.symlink(sanitized_name, link_path)
                logger.info(f"Created symlink alias: {link_path} -> {sanitized_name}")
                
            # Scenario B: Resume Legacy Crawl (Reverse Alias)
            # Create link: prodealcenter-fr -> prodealcenter.fr
            # Condition: Link (original) exists (is a real dir), Target (sanitized) does NOT exist
            elif os.path.exists(link_path) and not os.path.exists(target_path):
                 if os.path.isdir(link_path) and not os.path.islink(link_path):
                     os.symlink(original_name, target_path)
                     logger.info(f"Created REVERSE symlink for resume: {target_path} -> {original_name}")

            # Scenario C: Conflict Resolution (Accidental Directory Blocking Resume)
            # Condition: BOTH exist and BOTH are directories (no symlinks)
            # This happens if a run started without the fix and created a fresh 'prodealcenter-fr'
            elif os.path.isdir(link_path) and os.path.isdir(target_path) and not os.path.islink(target_path) and not os.path.islink(link_path):
                try:
                    # HEURISTIC: If 'sanitized' (new) is tiny vs 'original' (legacy), assume accidental creation
                    # Check file counts
                    count_target = len(os.listdir(target_path))
                    count_link = len(os.listdir(link_path))
                    
                    # If legacy has significantly more data (e.g. > 100 items) and new has very little (< 50)
                    if count_link > 100 and count_target < 100:
                        logger.warning(f"Conflict usage detected! Found small new dir '{sanitized_name}' ({count_target} items) vs large legacy '{original_name}' ({count_link} items).")
                        logger.warning("Assuming accidental creation. Backing up new dir and forcing Resume.")
                        
                        import shutil
                        backup_name = f"{sanitized_name}_backup_{int(datetime.now().timestamp())}"
                        backup_path = os.path.join(base_dir, backup_name)
                        os.rename(target_path, backup_path)
                        
                        os.symlink(original_name, target_path)
                        logger.info(f"Fixed Collision: Moved to {backup_name} and linked {target_path} -> {original_name}")
                except Exception as inner_e:
                     logger.error(f"Failed to resolve directory conflict: {inner_e}")
                     
        except Exception as e:
            logger.warning(f"Failed to create symlink alias in {base_dir}: {e}")
