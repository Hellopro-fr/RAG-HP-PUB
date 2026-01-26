from crawlee.crawlers import BasicCrawlingContext, PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.router import Router
from crawlee import EnqueueStrategy, RequestOptions
import re
import os
from urllib.parse import urlparse, parse_qs
import logging
from utils import process_page, is_stopped_manually, process_url, manage_french_detection_method, detect_captcha
from domain_fr import DomainFR
from typing import Optional, TYPE_CHECKING, Dict, Any, Literal

if TYPE_CHECKING:
    from state import DedupManager, StatsManager

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

# Extended Clean List (Always Remove)
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
    "fbclid", "fb_action_ids", "fb_action_types",
    "fb_source", "fb_ref",

    # === GOOGLE ADS & ANALYTICS ===
    "gclid", "gclsrc", "dclid",
    "srsltid", "utmcct", "utmcsr", "utmcmd", "utmccn",
    "_ga", "_gid", "_gat",

    # === HUBSPOT ===
    "hsa_acc", "hsa_cam", "hsa_grp",
    "hsa_ad", "hsa_src", "hsa_mt",
    "hsa_kw", "hsa_tgt", "hsa_ver", "hsa_net",
    "hsCtaTracking", "hsCta",

    # === MAILCHIMP ===
    "mc_cid", "mc_eid",

    # === SOCIAL MEDIA TRACKING ===
    "twclid", "li_fat_id", "msclkid",
    "igshid", "tt_medium", "tt_content",

    # === WORDPRESS ===
    "_wpnonce", "preview", "preview_id",
    "preview_nonce", "et_blog",

    # === PRESTASHOP ===
    "id_product", "id_category", "pid",
    "controller", "id_product_attribute",
    "isolang", "id_lang",

    # === SHOPIFY ===
    "pr_prod_strat", "pr_rec_id", "pr_rec_pid",
    "pr_ref_pid", "pr_seq",
    "variant", "selling_plan",

    # === MAGENTO ===
    "SID", "___store", "___from_store",

    # === SESSION & TRACKING ===
    "sessionid", "session_id", "PHPSESSID",
    "sid", "s_id",
    "_gl", "ref", "referrer",

    # === AFFILIATE & MARKETING ===
    "aff_id", "affiliate", "partner",
    "coupon", "discount", "promo",
    "voucher",

    # === AUTRES TRACKING ===
    "click_id", "transaction_id",
    "source", "medium", "campaign",

    # === FILTRES SOUVENT INUTILES ===
    "view", "mode", "display",
    "timestamp", "random", "nocache",
    "order", "sort", "resultsPerPage", "productListView", # Added for deduplication
]

router = Router()

# Global Limit Config
SKIP_QUESTION_MARK = False
SKIP_DIEZ = False
# Added bypass flags
BYPASS_QUESTION_MARK = False
BYPASS_DIEZ = False

LIMIT_QUESTION_MARK_DIEZ = 50
DOMAIN = os.getenv("DOMAIN", "")
BASE_URL = ""
CRAWLEE_STORAGE_NAME = ""

# Dynamic Configs from Main
TO_REMOVE_CUSTOM: list[str] = []
TO_KEEP_CUSTOM: list[str] = []

# Global Counters (Local)
count_question_mark = 0
count_diez = 0

# Global Stop Reason (Point 18)
STOP_REASON = ""

# Managers (Injected from main.py)
dedup_manager: Optional['DedupManager'] = None
stats_manager: Optional['StatsManager'] = None
max_errors: Optional[int] = None
max_redirects: Optional[int] = None
max_new_urls: Optional[int] = None

# Crawler Instance (Injected from main.py)
crawler_instance: Optional[PlaywrightCrawler] = None

# Initialize DomainFR logic
domain_fr = DomainFR("")

# Point 12: Blocked Status Codes
BLOCKED_STATUS_CODES = [401, 403, 429, 404, 410, 423, 502, 500, 503]

@router.default_handler
async def request_handler(context: PlaywrightCrawlingContext) -> None:
    # Use global STOP_REASON to communicate with main.py
    global STOP_REASON, count_question_mark, count_diez, crawler_instance

    page = context.page
    request = context.request
    log = context.log
    
    # Use loaded_url to ensure we check the actual page we are on (handles redirects)
    url = request.loaded_url or request.url
    
    # --- Check Blocked Status (Point 12) ---
    response = context.response
    if response:
        status = response.status
        if status in BLOCKED_STATUS_CODES:
            log.warning(f"Session retired due to blocked status code: {status}")
            if context.session:
                context.session.retire()
            # Raise an error to trigger Crawlee's retry logic for this request
            raise Exception(f"Request blocked with status {status}. Retrying with new session.")

    # --- Check Circuit Breaker (Global thresholds) ---
    if stats_manager:
        # Check all relevant thresholds
        breached = False
        if max_errors and await stats_manager.check_threshold("errors", max_errors): breached = True
        if max_redirects and await stats_manager.check_threshold("redirects", max_redirects): breached = True
        if max_new_urls and await stats_manager.check_threshold("new_urls", max_new_urls): breached = True
        
        if breached:
             log.warning("🛑 Circuit breaker triggered! Stopping crawler.")
             if crawler_instance:
                 crawler_instance.stop()
             return
    # -------------------------------------------------

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
    if DOMAIN and is_stopped_manually(DOMAIN, historised=False):
         log.warning("🛑 Manual STOP detected via file. Stopping crawler...")
         STOP_REASON = "stoppedManually"
         if crawler_instance:
             crawler_instance.stop()
         return

    # --- Cookie Injection (Point 5) ---
    if DOMAIN:
        try:
            await page.context.add_cookies([{
                "name": "cookieConsent",
                "value": "accepted",
                "domain": DOMAIN,
                "path": "/"
            }])
        except Exception as e:
            log.warning(f"Failed to inject cookie: {e}")
    # ----------------------------------
    
    # --- Deduplication & "Double Check" (Redis) ---
    is_existing = request.user_data.get("is_existing", False)
    
    if dedup_manager and not is_existing:
        # Double check Redis before processing
        is_new = await dedup_manager.add_url(url)
        
        if not is_new:
            log.info(f"Skipping duplicate URL (Redis Double Check): {url}")
            return
            
        # It is genuinely new
        if stats_manager:
             await stats_manager.increment("new_urls")
             if max_new_urls and await stats_manager.check_threshold("new_urls", max_new_urls):
                 log.warning("🛑 Max new URLs limit reached during processing. Stopping.")
                 if crawler_instance:
                     crawler_instance.stop()
                 return
    # -----------------------------------------------

    # Limit Checking (Question Mark / Diez)
    if '?' in url:
        count_question_mark += 1
    if '#' in url:
        count_diez += 1
        
    # Check Stops
    should_stop = False
    stop_reason_log = ""
    
    # Logic: Stop if limit reached AND skip is OFF AND bypass is OFF
    if not SKIP_QUESTION_MARK and not BYPASS_QUESTION_MARK and count_question_mark >= LIMIT_QUESTION_MARK_DIEZ:
         should_stop = True
         stop_reason_log = f"Limit of {LIMIT_QUESTION_MARK_DIEZ} entries with '?' reached."
         STOP_REASON = "limitQuestionMark"
         
    elif not SKIP_DIEZ and not BYPASS_DIEZ and count_diez >= LIMIT_QUESTION_MARK_DIEZ:
         should_stop = True
         stop_reason_log = f"Limit of {LIMIT_QUESTION_MARK_DIEZ} entries with '#' reached."
         STOP_REASON = "limitDiez"
         
    if should_stop:
        log.warning(f"🛑 STOPPING CRAWLER: {stop_reason_log}")
        if crawler_instance:
            crawler_instance.stop()
        return

    log.info(f"Processing {url} (Existing: {is_existing}) ...")

    # --- UPDATE MODE VERIFICATION ---
    if is_existing and stats_manager:
        final_url = page.url
        if final_url != url and final_url.rstrip('/') != url.rstrip('/'):
            log.info(f"Redirect detected: {url} -> {final_url}")
            await stats_manager.increment("redirects")
            
            if max_redirects and await stats_manager.check_threshold("redirects", max_redirects):
                log.warning("🛑 Max redirects reached. Stopping.")
                if crawler_instance:
                    crawler_instance.stop()
                return
    # --------------------------------

    # 1. Process the page (Scroll & Get Content)
    content = await process_page(page, url, log)
    
    # 2. FRENCH LANGUAGE CHECK
    is_main_site = (url == BASE_URL)
    french_detection_method = None
    is_enqueuing_links = False
    
    proxy_info = getattr(context, 'proxy_info', None)
    proxy_url = proxy_info.url if proxy_info else None

    try:
        if is_main_site:
            # Process normally and store the method
            domain_fr.homepage = url
            
            # Check content
            check_page = await domain_fr.check_page_if_french(content, is_check_url=False)
            
            if check_page["ok"]:
                res = manage_french_detection_method(DOMAIN, check_page["method"])
                if isinstance(res, Exception):
                     log.error(f"Failed to store French detection method: {res}")
                     if crawler_instance:
                         crawler_instance.stop()
                     return
                french_detection_method = res
                is_enqueuing_links = True
            else:
                # Content check failed, try URL/Redirect check
                check_url_res = await DomainFR.check_url(url, track_redirect=False, proxy_url=proxy_url)
                if check_url_res and check_url_res.get("ok"):
                     res = manage_french_detection_method(DOMAIN, check_url_res["method"])
                     if isinstance(res, Exception):
                         log.error(f"Failed to store French detection method: {res}")
                         if crawler_instance:
                             crawler_instance.stop()
                         return
                     french_detection_method = res
                     is_enqueuing_links = True

        else:
            # Internal Page: Retrieve stored method
            french_detection_method = manage_french_detection_method(DOMAIN)
            
            if isinstance(french_detection_method, Exception):
                log.error(f"Failed to retrieve French detection method: {french_detection_method}")
                if crawler_instance:
                    crawler_instance.stop()
                return
            
            # Create new instance with forced method
            domain_fr_with_method = DomainFR(url, str(french_detection_method))
            check_page = await domain_fr_with_method.check_page_if_french(content, is_check_url=False)
            
            if check_page["ok"]:
                is_enqueuing_links = True
            else:
                # Fallback URL check
                check_url_res = await DomainFR.check_url(url, track_redirect=False, proxy_url=proxy_url)
                if check_url_res and check_url_res.get("ok") and check_url_res.get("method") == french_detection_method:
                    is_enqueuing_links = True

    except Exception as e:
        log.error(f"Error during French detection: {e}")
        is_enqueuing_links = False

    # 3. Branching Logic based on Language Check
    if is_enqueuing_links:
        # === SUCCESS: Page is French ===
        from crawlee.storages import Dataset
        if CRAWLEE_STORAGE_NAME != "":
            dataset = await Dataset.open(name=CRAWLEE_STORAGE_NAME)
            await dataset.push_data({
                "url": url,
                "title": await page.title(),
                "content": content
            })
        else:
            await context.push_data({
                "url": url,
                "title": await page.title(),
                "content": content 
            })
        
        # Enqueue links (cleaned)
        await context.enqueue_links(
            strategy='same-domain',
            transform_request_function=filter_request
        )
    else:
        # === FAILURE: Page is NOT French ===
        log.warning(f"Le site {url} n'est pas en Français.")
        from crawlee.storages import Dataset
        
        # Format name properly
        nfr_dataset_name = f"nfr-{DOMAIN}".replace('.', '-')
        
        dataset = await Dataset.open(name=nfr_dataset_name)
        await dataset.push_data({"url": url, "content": content})
        
        # Note: We do NOT call enqueue_links here, effectively stopping this branch.


def filter_request(request: RequestOptions) -> RequestOptions | Literal['skip']:
    """
    Filters requests and handles preliminary deduplication check.
    Handles URL Cleaning (Point 1).
    Does NOT add to Redis here - that happens in request_handler for the "Double Check" pattern.
    """
    if isinstance(request, dict):
        url = request.get('url')
    else:
        url = getattr(request, 'url', None)

    if not url: return 'skip'
        
    # 1. Standard Cleaning (Always remove specific params)
    # We pass skip_question_mark=True to force query string parsing/rebuilding in process_url
    cleaned_url = process_url(url, skip_question_mark=True, skip_diez=False, to_remove=PARAMS_TO_REMOVE)

    # 2. Logic for Skip Flags (Point 1: Clean instead of Drop)
    # If SKIP flags are set, we process the cleaned_url further to strip query/hash
    if SKIP_QUESTION_MARK or SKIP_DIEZ:
        cleaned_url = process_url(
            cleaned_url,
            skip_question_mark=SKIP_QUESTION_MARK,
            skip_diez=SKIP_DIEZ,
            to_keep=TO_KEEP_CUSTOM,
            to_remove=TO_REMOVE_CUSTOM
        )
    
    # Update request URL if it changed
    if cleaned_url != url:
        if isinstance(request, dict):
            request['url'] = cleaned_url
        else:
            try:
                request.url = cleaned_url
            except AttributeError:
                pass 
        url = cleaned_url

    parsed = urlparse(url)
    
    # Check extensions
    if IGNORED_EXTENSIONS.match(url):
        return 'skip'
    
    # Check forbidden params (Blocking entire URL if present)
    query = parse_qs(parsed.query)
    for param in FORBIDDEN_PARAMS:
        if param in query:
            return 'skip'
            
    # Check Spider Traps (Path based)
    if '/quotation/cart/' in url or '/cart/cart/' in url or '/catalog/product_compare/' in url:
        return 'skip'
        
    # Check base64 long strings
    if re.search(r'/url/[a-zA-Z0-9]{20,}', url):
        return 'skip'

    # --- Redis Deduplication Check removed (Sync requirement) ---
    # Cannot await dedup_manager.is_known(url) in synchronous filter_request
    # Deduplication is still handled in request_handler via "Double Check"
    # ---------------------------------

    # Construct dict for Crawlee if needed
    if not isinstance(request, dict):
         return {
             "url": url,
             "unique_key": getattr(request, 'unique_key', url),
             "method": getattr(request, 'method', 'GET'),
             "payload": getattr(request, 'payload', None),
             "headers": getattr(request, 'headers', None),
             "user_data": {"is_existing": False}
         }
    
    if 'user_data' not in request:
        request['user_data'] = {}
    request['user_data']['is_existing'] = False

    return request
