import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def scrape_html(url: str, timeout: int = 30, proxy: Optional[str] = None) -> Optional[str]:
    """
    Récupère le contenu HTML d'une URL en utilisant un navigateur headless (Playwright).

    Cette méthode est utilisée comme fallback quand le fetch HTTP simple échoue
    (403, 503, JavaScript-rendered pages, bot protection).

    Args:
        url: URL à scraper
        timeout: Timeout en secondes pour le chargement de la page
        proxy: Proxy URL (format httpx: http://user:pass@host:port)

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

    # Convert httpx proxy URL to Playwright format if provided
    playwright_proxy = None
    if proxy:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy)
            playwright_proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
            if parsed.username:
                playwright_proxy["username"] = parsed.username
            if parsed.password:
                playwright_proxy["password"] = parsed.password
        except Exception:
            logger.warning(f"Failed to parse proxy URL for Playwright: {proxy}")

    browser = None
    try:
        async with async_playwright() as p:
            launch_args = {
                "headless": True,
                "args": [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ],
            }
            if playwright_proxy:
                launch_args["proxy"] = playwright_proxy
            browser = await p.chromium.launch(**launch_args)

            context = await browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                locale='fr-FR',
                extra_http_headers={
                    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                }
            )

            page = await context.new_page()

            # Naviguer vers l'URL et attendre le chargement du DOM
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
                # Attendre un court instant pour le rendu JavaScript
                await page.wait_for_timeout(2000)
            except Exception as nav_e:
                err_str = str(nav_e)
                if "ERR_CONNECTION_REFUSED" in err_str or "ERR_NAME_NOT_RESOLVED" in err_str:
                    logger.error(f"Scraping Playwright impossible, site inaccessible (Refused/DNS): {url}")
                    await context.close()
                    await browser.close()
                    return None
                    
                logger.warning(f"Timeout/Erreur navigation Playwright pour {url} (extraction partielle tentée): {nav_e}")
                # On continue pour tenter d'extraire le contenu partiellement chargé

            # Récupérer le HTML complet rendu par le navigateur (même partiel)
            content = await page.content()

            await context.close()
            await browser.close()

            if content and len(content) > 100:
                logger.info(f"Scraping réussi pour {url} ({len(content)} caractères)")
                return content
            else:
                logger.warning(f"Scraping retourne un contenu trop court pour {url}")
                return None

    except Exception as e:
        logger.error(f"Erreur scraping Playwright pour {url}: {e}")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return None
