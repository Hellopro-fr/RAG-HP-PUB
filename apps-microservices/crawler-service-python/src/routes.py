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

    # --- Block Resources (Performance & Bandwidth) ---
    async def route_handler(route):
        try:
            req = route.request
            resource_type = req.resource_type
            req_url = req.url
            
            # Block heavy media and fonts
            if resource_type in ['image', 'media', 'font', 'stylesheet']:
                await route.abort()
                return

            # Block download scripts and binary files
            if 'download.php' in req_url or 'imp=1' in req_url:
                await route.abort()
                return
            
            # Block binary extensions
            if re.search(r'\.(pdf|zip|rar|doc|docx|xls|xlsx|exe|bin|iso|dmg)$', req_url, re.IGNORECASE):
                await route.abort()
                return

            await route.continue_()
        except Exception:
            # Ignore route errors (e.g. page closed)
            pass

    await page.route("**/*", route_handler)
    # -------------------------------------------------
    
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
    
    # Smart Memory Management: Keep most recent URLs when limit reached
    if len(all_urls_crawled) > 500000:
        log.warning(f"all_urls_crawled exceeded 500k items. Keeping 250k most recent URLs to prevent re-crawls.")
        recent_urls = list(all_urls_crawled)[-250000:]
        all_urls_crawled.clear()
        all_urls_crawled.update(recent_urls)
        log.info(f"Deduplication set trimmed. Now contains {len(all_urls_crawled)} URLs.")

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
        await context.crawler.stop()
        return

    log.info(f"Processing {url} ...")

    # Process the page
    content = await process_page(page, url, log)
    
    # Push data to Named Dataset (Legacy Node.js Compatibility)
    from crawlee.storages import Dataset
    if DOMAIN:
        dataset = await Dataset.open(DOMAIN)
        await dataset.push_data({
            "url": url,
            "title": await page.title(),
            "content": content  # Full content stored
        })
    else:
        # Fallback to default
        await context.push_data({
            "url": url,
            "title": await page.title(),
            "content": content 
        })
    
    # Enqueue links with filtering
    await context.enqueue_links(
        strategy="same-domain",
        transform_request_function=filter_request
    )

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

# Extended Clean List (from Node.js)
PARAMS_TO_REMOVE = [
    # === CART & WISHLIST ===
    "add-to-cart", "add_to_cart", "addtocart",
    "add-to-compare", "add_to_compare",
    "add-to-wishlist", "add_to_wishlist", "addtowishlist",
    "remove_from_wishlist", "remove_wishlist",
    "remove_compare", "remove_item",
    "quantity", "qty",
    # === TRACKING UTM (Marketing) ===
    "utm_source", "utm_medium", "utm_campaign",
    "utm_content", "utm_term", "utm_id",
    "utm_referrer", "utm_name",
    # === FACEBOOK & META ===
    "fbclid", "fb_action_ids", "fb_action_types", "fb_source", "fb_ref",
    # === GOOGLE ADS & ANALYTICS ===
    "gclid", "gclsrc", "dclid", "srsltid", "utmcct", "utmcsr",
    "utmcmd", "utmccn", "_ga", "_gid", "_gat",
    # === OTHERS ===
    "mc_cid", "mc_eid", "twclid", "li_fat_id", "msclkid",
    "igshid", "tt_medium", "tt_content", "_wpnonce", "sessionid", 
    "PHPSESSID", "sid", "aff_id", "click_id", "timestamp", "random", "nocache"
]

# Dynamic Configs from Main
TO_REMOVE_CUSTOM: list[str] = []
TO_KEEP_CUSTOM: list[str] = []

def clean_url_params(url: str) -> str:
    """Removes tracking and useless parameters from URL."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        
        # 1. Logic for KEEPING specific params (overrides remove)
        if TO_KEEP_CUSTOM:
            keys_to_delete = []
            for key in query.keys():
                if key not in TO_KEEP_CUSTOM:
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del query[key]
        
        # 2. Logic for REMOVING (if not in Keep mode or mixed)
        # Note: If TO_KEEP is set, we usually only keep those. 
        # But if TO_KEEP is empty, we remove dirty ones.
        else:
            # Combine hardcoded + custom
            blocklist = set(PARAMS_TO_REMOVE + TO_REMOVE_CUSTOM)
            
            for param in list(query.keys()): # list() to allow modification
                if param in blocklist:
                    del query[param]
                
        # Reconstruct
        from urllib.parse import urlencode, urlunparse
        new_query = urlencode(query, doseq=True)
        return urlunparse(parsed._replace(query=new_query))
    except Exception:
        return url

def filter_request(request):
    if isinstance(request, dict):
        url = request.get('url')
    else:
        url = getattr(request, 'url', None)

    if not url:
        return False
        
    # 1. Clean URL (Remove UTMs, etc.)
    cleaned_url = clean_url_params(url)
    
    # Update request URL if it changed
    if cleaned_url != url:
        if isinstance(request, dict):
            request['url'] = cleaned_url
        else:
            try:
                request.url = cleaned_url
            except AttributeError:
                pass # Some request objects might be immutable
        url = cleaned_url

    parsed = urlparse(url)
    
    # Check extensions
    if IGNORED_EXTENSIONS.match(url):
        return False

    # Check Skip Flags
    if SKIP_QUESTION_MARK and '?' in url:
        return False
    if SKIP_DIEZ and '#' in url:
        return False
        
    # Check forbidden params (Blocking)
    query = parse_qs(parsed.query)
    for param in FORBIDDEN_PARAMS:
        if param in query:
            return False
            
    # Check Spider Traps (Path based)
    if '/quotation/cart/' in url or '/cart/cart/' in url or '/catalog/product_compare/' in url:
        return False
        
    # Check base64 long strings (often dynamic infinite urls)
    if re.search(r'/url/[a-zA-Z0-9]{20,}', url):
        return False
        
    return request
