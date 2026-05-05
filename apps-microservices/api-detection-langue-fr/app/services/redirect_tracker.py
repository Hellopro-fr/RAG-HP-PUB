import asyncio
import httpx
import logging
from typing import Optional
from urllib.parse import urlparse
from app.core.config import settings
from app.services.scraper import ScrapeResult, scrape_html, build_proxy_url

# Erreurs non-retryables pour la MÊME URL (inutile de réessayer la même URL)
# mais qui DOIVENT déclencher Phase 2 (variantes http/https, www/sans-www).
# Ex: ERR_NAME_NOT_RESOLVED sur www.example.com → essayer example.com
# Ex: ERR_SSL_PROTOCOL_ERROR sur https → essayer http
_VARIANT_ELIGIBLE_ERRORS = (
    'ERR_NAME_NOT_RESOLVED',     # DNS échoue — le sous-domaine www peut ne pas exister
    'ERR_CERT_DATE_INVALID',     # Certificat SSL expiré — http pourrait fonctionner
    'ERR_SSL_PROTOCOL_ERROR',    # Protocole SSL incompatible — http pourrait fonctionner
)

# Erreurs fatales — arrêt immédiat, Phase 2 inutile (problème de configuration)
_FATAL_ERRORS = (
    'Proxy non configuré',       # Erreur de configuration
    'Proxy obligatoire',         # Erreur de configuration
    'Proxy invalide',            # Erreur de configuration
)

# Union des deux pour la fonction _is_retryable_error (rétrocompatibilité)
_NON_RETRYABLE_ERRORS = _VARIANT_ELIGIBLE_ERRORS + _FATAL_ERRORS

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


def _generate_url_variants(url: str) -> list[str]:
    """
    Génère les variantes d'URL à essayer quand l'URL originale échoue.

    Bascule entre https/http et www/sans-www pour couvrir les cas où :
    - Le certificat SSL est mal configuré (https échoue, http fonctionne)
    - Le sous-domaine www n'est pas configuré (www échoue, sans-www fonctionne)
    - Ou l'inverse (sans-www redirige vers www mais n'est pas configuré)

    Returns:
        Liste d'URLs variantes (excluant l'URL originale).
    """
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme  # http ou https
        hostname = parsed.hostname or ''
        path = parsed.path or '/'
        query = f'?{parsed.query}' if parsed.query else ''

        # Déterminer les variantes de scheme et hostname
        alt_scheme = 'http' if scheme == 'https' else 'https'
        has_www = hostname.startswith('www.')
        if has_www:
            alt_hostname = hostname[4:]  # Retirer www.
        else:
            alt_hostname = f'www.{hostname}'  # Ajouter www.

        port_str = f':{parsed.port}' if parsed.port and parsed.port not in (80, 443) else ''

        # Générer les 3 variantes (excluant l'originale)
        # Ordre optimisé : www toggle d'abord (cause #1 de DNS failure sur .fr),
        # puis scheme toggle (SSL mal configuré), puis les deux combinés.
        variants = [
            f'{scheme}://{alt_hostname}{port_str}{path}{query}',          # Même scheme, autre host (www toggle)
            f'{alt_scheme}://{hostname}{port_str}{path}{query}',          # Même host, autre scheme (http/https)
            f'{alt_scheme}://{alt_hostname}{port_str}{path}{query}',      # Autre scheme + autre host
        ]

        # Nettoyer : dédupliquer et exclure l'originale
        original_normalized = url.rstrip('/')
        seen = set()
        unique_variants = []
        for v in variants:
            v_normalized = v.rstrip('/')
            if v_normalized != original_normalized and v_normalized not in seen:
                seen.add(v_normalized)
                unique_variants.append(v)

        return unique_variants
    except Exception as e:
        logger.warning(f"Erreur génération variantes pour {url}: {e}")
        return []


async def fetch_html(url: str, proxy: Optional[str] = None) -> Optional[ScrapeResult]:
    """
    Récupère le contenu HTML d'une URL via Playwright avec proxy obligatoire.

    Stratégie en deux phases :
    Phase 1 — Retry sur l'URL originale (3 tentatives, rotation proxy) :
      - Tentative 1 : auto (rotation intelligente Apify, pool large)
      - Tentative 2 : country-FR (IP française, meilleure compatibilité géo)
      - Tentative 3 : auto (fallback, rotation intelligente sur autre IP)

    Phase 2 — Fallback sur variantes d'URL (si Phase 1 échoue) :
      Bascule http/https et www/sans-www pour couvrir les cas de mauvaise
      configuration SSL ou DNS. Chaque variante est testée une seule fois.
      Ex: https://www.example.com → http://www.example.com → https://example.com → http://example.com

    Returns:
        ScrapeResult (html, final_url, status_code, headers) ou None en cas d'erreur totale.
        ScrapeResult.final_url est l'URL après redirections (peut différer de l'URL d'entrée).
    """
    effective_proxy = proxy or settings.APIFY_PROXY
    if not effective_proxy:
        logger.error(f"Proxy obligatoire pour fetch_html: {url}. "
                     f"Configurez APIFY_PROXY ou passez proxy_url.")
        return None

    max_retries = settings.HTTP_MAX_RETRIES
    last_error = None

    for attempt in range(1, max_retries + 1):
        # Toutes les tentatives utilisent auto (rotation intelligente Apify, pool large)
        # country-FR retiré : pool plus petit, risque d'épuisement (erreur "no usable proxies"),
        # et inutile car Accept-Language + hreflang/NLP détectent le français sans IP française.
        attempt_proxy = build_proxy_url(effective_proxy, country=None)

        logger.warning(f"[{attempt}/{max_retries}] Fetch {url} avec proxy auto (rotation intelligente)")

        try:
            result = await scrape_html(url, proxy=attempt_proxy)
            if result:
                if attempt > 1:
                    logger.info(f"Récupération réussie pour {url} à la tentative {attempt}/{max_retries}")
                return result

            # Contenu vide/trop court — retryable
            last_error = "Contenu vide ou trop court"

        except Exception as e:
            last_error = str(e)

            # Erreur fatale (config proxy) → arrêt immédiat, Phase 2 inutile
            if any(fatal in last_error for fatal in _FATAL_ERRORS):
                logger.error(f"Erreur fatale pour {url}: {last_error}")
                return None

            # Erreur non-retryable sur la même URL (DNS, SSL) → skip retries, passer à Phase 2
            if any(err in last_error for err in _VARIANT_ELIGIBLE_ERRORS):
                logger.warning(f"Erreur non-retryable pour {url}: {last_error} — passage aux variantes")
                break

        if attempt < max_retries:
            wait_time = attempt * 2  # 2s, 4s entre les tentatives
            logger.warning(
                f"Tentative {attempt}/{max_retries} échouée pour {url} "
                f"({last_error}), nouvelle tentative dans {wait_time}s..."
            )
            await asyncio.sleep(wait_time)

    logger.warning(f"Échec de récupération HTML pour {url} après {max_retries} tentatives ({last_error})")

    # Phase 2 : Fallback sur variantes d'URL (http/https, www/sans-www)
    # Couvre les cas de mauvaise configuration SSL ou DNS côté serveur.
    # Chaque variante est testée une seule fois avec proxy auto.
    variants = _generate_url_variants(url)
    if variants:
        logger.warning(
            f"[VARIANTES] Tentative de fallback pour {url} — "
            f"{len(variants)} variante(s) à tester: {', '.join(variants)}"
        )
        for variant in variants:
            try:
                variant_proxy = build_proxy_url(effective_proxy, country=None)
                logger.warning(f"[VARIANTE] Test {variant}")
                result = await scrape_html(variant, proxy=variant_proxy)
                if result:
                    logger.warning(
                        f"[VARIANTE] Succès avec {variant} → {result.final_url} "
                        f"({len(result.html)} caractères)"
                    )
                    return result
            except Exception as e:
                if not _is_retryable_error(str(e)):
                    logger.warning(f"[VARIANTE] Erreur permanente pour {variant}: {e}")
                    continue
                logger.warning(f"[VARIANTE] Échec pour {variant}: {e}")
                continue

        logger.error(f"Échec de récupération HTML pour {url} — toutes les variantes ont échoué")
    else:
        logger.error(f"Échec de récupération HTML pour {url} — aucune variante à tester")

    return None
