import asyncio
import logging
import random
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sémaphore global limitant le nombre de navigateurs Playwright simultanés.
# Protège contre l'épuisement mémoire en cas de requêtes /detect ou /detect-batch concurrentes.
_BROWSER_SEMAPHORE = asyncio.Semaphore(10)


# Pool de User-Agents réalistes — rotation aléatoire à chaque requête
# Aligné sur la configuration du crawler-service (Firefox, Chrome, Safari × Windows, macOS, Linux)
_USER_AGENTS = [
    # Chrome — Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome — Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Firefox — Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    # Firefox — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Firefox — Linux
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari — macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
]

# Extensions de fichiers lourds à bloquer (aligné sur crawler-service)
_BLOCKED_RESOURCE_EXTENSIONS = (
    '.pdf', '.zip', '.rar', '.doc', '.docx', '.xls', '.xlsx',
    '.exe', '.bin', '.iso', '.dmg', '.7z', '.bz2', '.tar', '.xz',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.svg', '.ico',
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.mp3', '.wav', '.ogg', '.aac', '.mid',
    '.ppt', '.pptx', '.apk', '.css', '.rss',
)


def _parse_proxy(proxy: str) -> Optional[dict]:
    """
    Convertit une URL proxy httpx vers le format Playwright.

    Args:
        proxy: URL proxy au format http://user:pass@host:port

    Returns:
        Dict Playwright proxy ou None en cas d'erreur
    """
    try:
        parsed = urlparse(proxy)
        playwright_proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
        if parsed.username:
            playwright_proxy["username"] = parsed.username
        if parsed.password:
            playwright_proxy["password"] = parsed.password
        return playwright_proxy
    except Exception:
        logger.warning(f"Échec parsing URL proxy pour Playwright: {proxy}")
        return None


async def _setup_resource_blocking(page) -> None:
    """
    Configure le blocage des ressources lourdes sur une page Playwright.

    Bloque images, media, fonts, stylesheets et fichiers binaires —
    aligné sur la configuration du crawler-service pour réduire la
    bande passante et accélérer le chargement.
    """
    async def _route_handler(route):
        request = route.request
        resource_type = request.resource_type

        # Bloquer les types de ressources lourdes
        if resource_type in ('image', 'media', 'font', 'stylesheet'):
            await route.abort()
            return

        # Bloquer les fichiers binaires par extension
        req_url = request.url.lower()
        if any(req_url.endswith(ext) for ext in _BLOCKED_RESOURCE_EXTENSIONS):
            await route.abort()
            return

        # Bloquer les patterns connus du crawler-service
        if 'download.php' in req_url or 'imp=1' in req_url:
            await route.abort()
            return

        await route.continue_()

    await page.route('**/*', _route_handler)


async def _inject_cookie_consent(context, url: str) -> None:
    """
    Injecte un cookie de consentement accepté — aligné sur le crawler-service.

    Évite les bannières cookies qui peuvent masquer le contenu réel
    et biaiser la détection de langue.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.hostname
        if domain:
            await context.add_cookies([{
                'name': 'cookieConsent',
                'value': 'accepted',
                'domain': domain,
                'path': '/',
            }])
    except Exception:
        pass


async def scrape_html(url: str, timeout: int = 90, proxy: Optional[str] = None) -> Optional[str]:
    """
    Récupère le contenu HTML d'une URL via Playwright avec proxy obligatoire.

    Configuration alignée sur le crawler-service :
    - Rotation de User-Agent (Firefox, Chrome, Safari × Windows, macOS, Linux)
    - Blocage des ressources lourdes (images, media, fonts, stylesheets)
    - Acceptation automatique des cookies
    - Attente networkidle pour le rendu JavaScript complet
    - Timeout de navigation à 90s (identique crawler-service)

    Args:
        url: URL à scraper
        timeout: Timeout en secondes pour le chargement de la page (défaut: 90)
        proxy: Proxy URL obligatoire (format: http://user:pass@host:port)

    Returns:
        Le contenu HTML rendu par le navigateur, ou None en cas d'erreur.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error(
            "Playwright non installé. Installez-le avec: "
            "pip install playwright && python -m playwright install chromium"
        )
        return None

    if not proxy:
        logger.error(f"Proxy obligatoire pour scrape_html: {url}")
        return None

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        logger.error(f"Proxy invalide pour {url}: {proxy}")
        return None

    # Rotation aléatoire du User-Agent
    user_agent = random.choice(_USER_AGENTS)

    browser = None
    try:
        async with _BROWSER_SEMAPHORE:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=playwright_proxy,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-blink-features=AutomationControlled',
                    ],
                )

                context = await browser.new_context(
                    user_agent=user_agent,
                    locale='fr-FR',
                    ignore_https_errors=True,  # Gère ERR_CERT_DATE_INVALID, ERR_SSL_PROTOCOL_ERROR
                    extra_http_headers={
                        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                    }
                )

                # Injection cookie de consentement (comme crawler-service)
                await _inject_cookie_consent(context, url)

                page = await context.new_page()

                # Blocage des ressources lourdes (comme crawler-service)
                await _setup_resource_blocking(page)

                # Navigation en deux phases :
                # Phase 1 : domcontentloaded (rapide, DOM prêt)
                # Phase 2 : networkidle avec timeout court (bonus JS rendering)
                # Évite d'attendre 90s sur des sites qui ne deviennent jamais idle
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                except Exception as nav_e:
                    err_str = str(nav_e)
                    # Erreurs permanentes — inutile de continuer
                    if "ERR_CONNECTION_REFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                        logger.error(f"Site inaccessible (Refused/DNS): {url}")
                        await context.close()
                        await browser.close()
                        return None

                    # Erreurs transitoires (proxy, timeout) — on tente l'extraction partielle
                    logger.warning(f"Timeout/Erreur navigation pour {url} (extraction partielle tentée): {nav_e}")

                # Phase 2 : attendre networkidle avec un timeout court (5s bonus)
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass

                # Récupérer le HTML — avec retry si la page est en cours de navigation
                content = None
                for content_attempt in range(3):
                    try:
                        content = await page.content()
                        break
                    except Exception as content_e:
                        if 'navigating and changing the content' in str(content_e):
                            logger.warning(f"Page en navigation pour {url}, attente 1s (tentative {content_attempt + 1}/3)")
                            await page.wait_for_timeout(1000)
                        else:
                            logger.warning(f"Erreur page.content() pour {url}: {content_e}")
                            break

                await context.close()
                await browser.close()

                if content and len(content) > 100:
                    logger.info(f"Scraping réussi pour {url} ({len(content)} caractères)")
                    return content
                else:
                    logger.warning(f"Contenu trop court pour {url}")
                    return None

    except Exception as e:
        logger.error(f"Erreur scraping Playwright pour {url}: {e}")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return None


async def scrape_html_with_redirects(
    url: str,
    timeout: int = 90,
    proxy: Optional[str] = None
) -> Optional[dict]:
    """
    Récupère le contenu HTML et suit les redirections via Playwright.

    Utilisé par RedirectTracker pour le suivi de redirections avec la
    même qualité de rendu que scrape_html.

    Args:
        url: URL à suivre
        timeout: Timeout en secondes (défaut: 90)
        proxy: Proxy URL obligatoire (format: http://user:pass@host:port)

    Returns:
        Dict avec success, final_url, status_code, content_type, redirects, html
        ou None en cas d'erreur critique.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright non installé.")
        return {'success': False, 'error': 'Playwright non installé'}

    if not proxy:
        return {'success': False, 'error': 'Proxy obligatoire'}

    playwright_proxy = _parse_proxy(proxy)
    if not playwright_proxy:
        return {'success': False, 'error': f'Proxy invalide: {proxy}'}

    user_agent = random.choice(_USER_AGENTS)
    redirects = []

    browser = None
    try:
        async with _BROWSER_SEMAPHORE:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=playwright_proxy,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-blink-features=AutomationControlled',
                    ],
                )

                context = await browser.new_context(
                    user_agent=user_agent,
                    locale='fr-FR',
                    ignore_https_errors=True,  # Gère ERR_CERT_DATE_INVALID, ERR_SSL_PROTOCOL_ERROR
                    extra_http_headers={
                        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                    }
                )

                await _inject_cookie_consent(context, url)

                page = await context.new_page()
                await _setup_resource_blocking(page)

                # Capturer les redirections via événement response
                def on_response(response):
                    status = response.status
                    if 300 <= status < 400:
                        redirects.append({
                            'url': response.url,
                            'status_code': status
                        })

                page.on('response', on_response)

                # Navigation deux phases (cohérent avec scrape_html)
                try:
                    response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                except Exception as nav_e:
                    err_str = str(nav_e)
                    if "ERR_CONNECTION_REFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                        await context.close()
                        await browser.close()
                        return {'success': False, 'error': f'Site inaccessible: {err_str}'}

                    logger.warning(f"Timeout/Erreur navigation pour {url}: {nav_e}")
                    response = None

                # Phase 2 : bonus networkidle (5s)
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception:
                    pass

                final_url = page.url
                status_code = response.status if response else 0
                content_type = ''
                if response:
                    content_type = response.headers.get('content-type', '')

                await context.close()
                await browser.close()

                return {
                    'success': True,
                    'final_url': final_url,
                    'status_code': status_code,
                    'content_type': content_type,
                    'redirects': redirects,
                }

    except Exception as e:
        logger.error(f"Erreur suivi redirections Playwright pour {url}: {e}")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return {'success': False, 'error': str(e)}
