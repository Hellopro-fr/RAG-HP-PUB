import asyncio
import httpx
import logging
from typing import Optional
from app.core.config import settings

# Erreurs non-retryables (échecs permanents — inutile de réessayer)
# Note : les erreurs SSL (ERR_CERT_*) sont gérées par ignore_https_errors=True
# dans Playwright, donc elles ne devraient plus apparaître.
_NON_RETRYABLE_ERRORS = (
    'ERR_NAME_NOT_RESOLVED',   # Le domaine n'existe pas
    'Proxy non configuré',     # Erreur de configuration
    'Proxy obligatoire',       # Erreur de configuration
    'Proxy invalide',          # Erreur de configuration
)

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


def _is_retryable_error(error_msg: str) -> bool:
    """Détermine si une erreur est retryable (transitoire) ou permanente."""
    for non_retryable in _NON_RETRYABLE_ERRORS:
        if non_retryable in error_msg:
            return False
    return True


async def fetch_html(url: str, proxy: Optional[str] = None) -> Optional[tuple[str, str]]:
    """
    Récupère le contenu HTML d'une URL via Playwright avec proxy obligatoire.

    Inclut un mécanisme de retry automatique pour les erreurs transitoires
    (proxy lent, IP bloquée, timeout). Les erreurs permanentes (DNS, config)
    ne sont pas retryées.

    Returns:
        Tuple (contenu_html, url_finale) ou None en cas d'erreur.
        url_finale est l'URL après redirections (peut différer de l'URL d'entrée).
    """
    effective_proxy = proxy or settings.APIFY_PROXY
    if not effective_proxy:
        logger.error(f"Proxy obligatoire pour fetch_html: {url}. "
                     f"Configurez APIFY_PROXY ou passez proxy_url.")
        return None

    max_retries = settings.HTTP_MAX_RETRIES
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            from app.services.scraper import scrape_html
            result = await scrape_html(url, proxy=effective_proxy)
            if result:
                content, final_url = result
                if attempt > 1:
                    logger.info(f"Récupération réussie pour {url} à la tentative {attempt}/{max_retries}")
                return (content, final_url)

            # Contenu vide/trop court — retryable
            last_error = "Contenu vide ou trop court"

        except Exception as e:
            last_error = str(e)

            # Vérifier si l'erreur est permanente
            if not _is_retryable_error(last_error):
                logger.error(f"Erreur non-retryable pour {url}: {last_error}")
                return None

        if attempt < max_retries:
            wait_time = attempt * 2  # 2s, 4s entre les tentatives
            logger.warning(
                f"Tentative {attempt}/{max_retries} échouée pour {url} "
                f"({last_error}), nouvelle tentative dans {wait_time}s..."
            )
            await asyncio.sleep(wait_time)

    logger.error(f"Échec de récupération HTML pour {url} après {max_retries} tentatives ({last_error})")
    return None
