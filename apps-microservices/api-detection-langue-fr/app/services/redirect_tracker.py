import httpx
import ssl
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


# Headers réalistes pour éviter le blocage par les WAF/bot protection
BROWSER_HEADERS = {
    'User-Agent': settings.USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}


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
        """
        self.redirects = []
        self.final_url = None
        
        transport = None
        if proxy:
            transport = httpx.AsyncHTTPTransport(proxy=proxy)
        
        try:
            async with httpx.AsyncClient(
                timeout=settings.HTTP_TIMEOUT,
                follow_redirects=True,
                transport=transport,
                headers=BROWSER_HEADERS,
                verify=False  # Certains sites ont des certificats SSL invalides
            ) as client:
                response = await client.get(url)
                
                # Collecter les redirections
                for hist in response.history:
                    self.redirects.append({
                        'url': str(hist.url),
                        'status_code': hist.status_code
                    })
                
                self.final_url = str(response.url)
                
                return {
                    'success': True,
                    'status_code': response.status_code,
                    'final_url': self.final_url,
                    'content_type': response.headers.get('content-type', ''),
                    'redirects': self.redirects
                }
                
        except httpx.TimeoutException:
            return {
                'success': False,
                'status_code': 0,
                'error': 'timeout',
                'final_url': url
            }
        except httpx.RequestError as e:
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
            async with httpx.AsyncClient(timeout=30) as client:
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
    Récupère le contenu HTML d'une URL.
    
    Utilise des headers réalistes de navigateur pour éviter le blocage
    par les WAF (Cloudflare, etc.) et les protections anti-bot.
    Inclut un mécanisme de retry avec des stratégies différentes.
    """
    transport = None
    if proxy:
        transport = httpx.AsyncHTTPTransport(proxy=proxy)
    
    # Stratégie 1 : Requête normale avec headers réalistes
    try:
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            follow_redirects=True,
            transport=transport,
            headers=BROWSER_HEADERS,
            verify=False  # Certains sites ont des certificats SSL invalides
        ) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                    return None
                return response.text
            
            # Si 403/503, on essaie la stratégie 2
            if response.status_code in (403, 503):
                logger.warning(f"Réponse {response.status_code} pour {url}, tentative avec headers alternatifs")
            else:
                logger.warning(f"Réponse {response.status_code} pour {url}")
                return None
                
    except Exception as e:
        logger.warning(f"Erreur première tentative pour {url}: {e}")
    
    # Stratégie 2 : Headers alternatifs (Googlebot-like)
    # Certains sites autorisent les crawlers de moteurs de recherche
    googlebot_headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'fr-FR,fr;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    }
    
    try:
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            follow_redirects=True,
            transport=transport,
            headers=googlebot_headers,
            verify=False
        ) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                    return None
                return response.text
            
            logger.warning(f"Réponse {response.status_code} pour {url} (tentative Googlebot)")
                
    except Exception as e:
        logger.warning(f"Erreur deuxième tentative pour {url}: {e}")
    
    # Stratégie 3 : User-Agent minimal (curl-like)
    # Parfois les sites n'aiment pas les UA trop sophistiqués
    minimal_headers = {
        'User-Agent': 'curl/8.4.0',
        'Accept': '*/*',
    }
    
    try:
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            follow_redirects=True,
            transport=transport,
            headers=minimal_headers,
            verify=False
        ) as client:
            response = await client.get(url)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                    return None
                return response.text
                
    except Exception:
        pass
    
    logger.error(f"Échec de récupération HTML pour {url} après 3 tentatives")
    return None
