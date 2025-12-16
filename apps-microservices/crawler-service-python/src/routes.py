from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.router import Router
import re
from urllib.parse import urlparse, parse_qs
import logging
from utils import process_page, is_stopped_manually

logger = logging.getLogger(__name__)

# Compile regex patterns once for performance
IGNORED_EXTENSIONS = re.compile(r".*\.(" + "|".join([
    "7z", "7zip", "bz2", "rar", "tar", "tar.gz", "xz", "zip",
    "mng", "pct", "bmp", "gif", "jpg", "jpeg", "png", "pst", "psp", "tif", "tiff",
    "ai", "drw", "dxf", "eps", "ps", "svg", "cdr", "ico", "webp",
    "mp3", "wma", "ogg", "wav", "ra", "aac", "mid", "au", "aiff",
    "3gp", "asf", "asx", "avi", "mov", "mp4", "mpg", "qt", "rm", "swf", "wmv", "m4a", "m4v", "flv", "webm",
    "xls", "xlsx", "ppt", "pptx", "pps", "doc", "docx", "odt", "ods", "odg", "odp",
    "css", "pdf", "exe", "bin", "rss", "dmg", "iso", "apk", "xml"
]) + r")(\?.*)?(#.*)?$", re.IGNORECASE)

# Spider Traps & Forbidden Patterns
FORBIDDEN_PARAMS = [
    'order', 'sort', 'dir', 'limit', 'resultsPerPage',
    'filter', 'price', 'price_min', 'price_max',
    'id_category', 'categoryId', 'productListView',
    'q', 'search', 'query', 'offset', 'start',
    'view', 'mode', 'display', 'per_page', 'items',
    'year', 'month', 'day', 'date', 'from', 'to',
    'ref', 'referrer', 'source', 'sort_by',
    'size_', 'taille_', 'color_', 'couleur_',
    'price_', 'prix_', 'brand_', 'marque_', 'type_', 'vendor_'
]

router = Router()

# Global set for deduplication (populated dynamically)
all_urls_crawled: set[str] = set()

# Global Limit Config (set from main.py)
SKIP_QUESTION_MARK = False
SKIP_DIEZ = False
LIMIT_QUESTION_MARK_DIEZ = 50
DOMAIN = ""

# Global Counters
count_question_mark = 0
count_diez = 0

@router.default_handler
async def request_handler(context: PlaywrightCrawlingContext) -> None:
    page = context.page
    request = context.request
    log = context.log
    
    url = request.url
    
    # Check Manual Stop
    if DOMAIN and is_stopped_manually(DOMAIN, historised=True):
         log.warning("🛑 Manual STOP detected via file. Stopping crawler...")
         await context.crawler.stop()
         return
    
    # Deduplication Check
    if url in all_urls_crawled:
        log.info(f"Skipping duplicate URL (history): {url}")
        return
        
    all_urls_crawled.add(url)
    
    # Safety Limit for Set
    if len(all_urls_crawled) > 100000:
        log.warning("all_urls_crawled exceeded 100k items. Clearing to prevent OOM. Deduplication relies on RequestQueue now.")
        all_urls_crawled.clear()

    # Limit Checking & Counting logic
    global count_question_mark, count_diez
    if '?' in url:
        count_question_mark += 1
    if '#' in url:
        count_diez += 1
        
    # Check Stops
    should_stop = False
    stop_reason = ""
    
    if not SKIP_QUESTION_MARK and count_question_mark >= LIMIT_QUESTION_MARK_DIEZ:
         should_stop = True
         stop_reason = f"Limit of {LIMIT_QUESTION_MARK_DIEZ} entries with '?' reached."
         
    if not SKIP_DIEZ and count_diez >= LIMIT_QUESTION_MARK_DIEZ:
         should_stop = True
         stop_reason = f"Limit of {LIMIT_QUESTION_MARK_DIEZ} entries with '#' reached."
         
    if should_stop:
        log.warning(f"🛑 STOPPING CRAWLER: {stop_reason}")
        # Not sure if we can stop crawler from context directly easily in Python yet without reference
        # We can raise an exception or try context.crawler.stop() if available?
        # context generally has crawler instance access? In Python SDK context seems to be PlaywrightCrawlingContext.
        # Let's try graceful exit via sys.exit? No, that kills container.
        # Ideally: await context.crawler.run() -> returns.
        # We will log error and potentially valid way is to not enqueue anything else and maybe set a global flag?
        # Re-check main.py: we can check these counters in a pre_navigation_hook or similar.
        # But here is fine.
        await context.crawler.stop()
        return

    log.info(f"Processing {url} ...")

    # Block resources (Images, Fonts, CSS)
    # ... (existing)
    
    # Process the page
    # Note: We assume 'domain' and other configs are available or passed via context.user_data
    # For this POC, we'll keep it simple.
    
    content = await process_page(page, url, log)
    
    # Push data to dataset
    await context.push_data({
        "url": url,
        "title": await page.title(),
        "content": content[:200] + "..." # Truncated for POC
    })

async def error_handler(context: PlaywrightCrawlingContext) -> None:
    request = context.request
    log = context.log
    page = context.page
    
    log.error(f"Request {request.url} failed with error messages: {request.error_messages}")
    
    errors_list = request.error_messages
    
    if page:
        try:
           # Try to get content for analysis
           from utils import process_page, detect_captcha
           
           content = await process_page(page, request.loaded_url or request.url, log)
           captcha_detected = await detect_captcha(page, content)
           
           if captcha_detected:
               log.error(f"Captcha detected on {request.url} : {captcha_detected}")
               
        except Exception as e:
           log.error(f"Error processing page for failure analysis: {e}")
    
    # Push to error dataset
    try:
        from crawlee.storages import Dataset
        # Extract domain from request URL or context?
        # We don't have easy access to 'domain' var from main.py here unless payload user_data.
        # Minimal fix: use "error-dataset" generic or try to extract domain.
        # Or assumes user_data has domain.
        # Let's extract hostname as approximation for domain.
        # Or just use "error-dataset".
        
        from urllib.parse import urlparse
        domain = urlparse(request.url).netloc.replace("www.", "")
        
        error_dataset = await Dataset.open(f"error-{domain}")
        await error_dataset.push_data({
            "id": request.id,
            "url": request.url,
            "errors": errors_list
        })
    except Exception as e:
         log.error(f"Failed to push to error dataset: {e}")

    # Enqueue links with filtering
    await context.enqueue_links(
        strategy="same-domain",
        transform_request_function=filter_request
    )

def filter_request(request):
    if isinstance(request, dict):
        url = request.get('url')
    else:
        url = getattr(request, 'url', None)

    if not url:
        return False

    parsed = urlparse(url)
    
    
    # Check extensions
    if IGNORED_EXTENSIONS.match(url):
        return False

    # Check Skip Flags
    if SKIP_QUESTION_MARK and '?' in url:
        return False
    if SKIP_DIEZ and '#' in url:
        return False
        
    # Check forbidden params
    query = parse_qs(parsed.query)
    for param in FORBIDDEN_PARAMS:
        if param in query:
            # logger.info(f"Blocked forbidden param {param}: {url}")
            return False
            
    # Check Spider Traps (Path based)
    if '/quotation/cart/' in url or '/cart/cart/' in url or '/catalog/product_compare/' in url:
        return False
        
    return request
