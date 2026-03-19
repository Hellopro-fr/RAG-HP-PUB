import httpx
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedirectTracker:
    """
    Gère le suivi des redirections HTTP avec fallback.
    """

    def __init__(self):
        self.redirects: list = []
        self.final_url: Optional[str] = None

    async def get_url_redirection(
        self,
        url: str,
        proxy: Optional[str] = None
    ) -> dict:
        """
        Suit les redirections et retourne l'URL finale avec les métadonnées.

        Utilise Playwright pour suivre les redirections (cohérent avec fetch_html).
        """
        self.redirects = []
        self.final_url = None

        effective_proxy = proxy or settings.APIFY_PROXY
        if not effective_proxy:
            logger.error(f"Proxy obligatoire pour le suivi de redirections: {url}")
            return {
                'success': False,
                'status_code': 0,
                'error': 'Proxy non configuré (APIFY_PROXY ou proxy_url requis)',
                'final_url': url
            }

        try:
            from app.services.scraper import scrape_html_with_redirects
            result = await scrape_html_with_redirects(url, proxy=effective_proxy)

            if result and result.get('success'):
                self.final_url = result.get('final_url', url)
                self.redirects = result.get('redirects', [])
                return {
                    'success': True,
                    'status_code': result.get('status_code', 200),
                    'final_url': self.final_url,
                    'content_type': result.get('content_type', ''),
                    'redirects': self.redirects
                }

            return {
                'success': False,
                'status_code': 0,
                'error': result.get('error', 'Échec Playwright') if result else 'Échec Playwright',
                'final_url': url
            }

        except Exception as e:
            logger.error(f"Erreur suivi redirections Playwright pour {url}: {e}")
            return {
                'success': False,
                'status_code': 0,
                'error': str(e),
                'final_url': url
            }

    @staticmethod
    async def get_url_redirection_pemavor(urls: list[str]) -> dict:
        """
        Fallback via API Pemavor pour la résolution de redirections.
        À implémenter si l'API Pemavor est disponible.
        """
        if not settings.PEMAVOR_API_URL or not settings.PEMAVOR_API_KEY:
            return {
                'success': False,
                'error': 'Pemavor API not configured'
            }

        try:
            async with httpx.AsyncClient(
                timeout=30,
                proxy=settings.APIFY_PROXY
            ) as client:
                response = await client.post(
                    settings.PEMAVOR_API_URL,
                    json={'urls': urls},
                    headers={'Authorization': f'Bearer {settings.PEMAVOR_API_KEY}'}
                )
                return {
                    'success': True,
                    'data': response.json()
                }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


async def fetch_html(url: str, proxy: Optional[str] = None) -> Optional[str]:
    """
    Récupère le contenu HTML d'une URL via Playwright avec proxy obligatoire.

    Utilise un navigateur headless Playwright avec fingerprinting, blocage de
    ressources lourdes et acceptation automatique des cookies — configuration
    alignée sur le crawler-service pour des résultats cohérents.
    """
    effective_proxy = proxy or settings.APIFY_PROXY
    if not effective_proxy:
        logger.error(f"Proxy obligatoire pour fetch_html: {url}. "
                     f"Configurez APIFY_PROXY ou passez proxy_url.")
        return None

    try:
        from app.services.scraper import scrape_html
        content = await scrape_html(url, proxy=effective_proxy)
        if content:
            return content
    except Exception as e:
        logger.error(f"Erreur Playwright pour {url}: {e}")

    logger.error(f"Échec de récupération HTML pour {url}")
    return None
