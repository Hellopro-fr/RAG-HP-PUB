from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.router import Router
import re
from urllib.parse import urlparse, parse_qs
import logging
from utils import process_page

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

@router.default_handler
async def request_handler(context: PlaywrightCrawlingContext) -> None:
    page = context.page
    request = context.request
    log = context.log
    
    url = request.url
    log.info(f"Processing {url} ...")

    # Block resources (Images, Fonts, CSS)
    # Note: In Python Playwright, this is usually done via context.route, 
    # but Crawlee might handle it via browser pool options. 
    # For now, we do it per page if needed, or rely on headless default savings.
    
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
