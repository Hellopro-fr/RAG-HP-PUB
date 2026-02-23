import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def scrape_html(url: str, timeout: int = 30) -> Optional[str]:
    """
    Récupère le contenu HTML d'une URL en utilisant un navigateur headless (Playwright).

    Cette méthode est utilisée comme fallback quand le fetch HTTP simple échoue
    (403, 503, JavaScript-rendered pages, bot protection).

    Args:
        url: URL à scraper
        timeout: Timeout en secondes pour le chargement de la page

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

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                ]
            )

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
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)

            # Attendre un court instant pour le rendu JavaScript
            await page.wait_for_timeout(2000)

            # Récupérer le HTML complet rendu par le navigateur
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
