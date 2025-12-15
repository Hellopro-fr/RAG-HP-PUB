import asyncio
import logging
import time
import psutil
import os
from playwright.async_api import Page
import logging


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
