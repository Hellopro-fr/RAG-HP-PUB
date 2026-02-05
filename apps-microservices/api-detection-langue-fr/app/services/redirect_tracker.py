import httpx
from typing import Optional
from app.core.config import settings


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
                headers={'User-Agent': settings.USER_AGENT}
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
    """
    transport = None
    if proxy:
        transport = httpx.AsyncHTTPTransport(proxy=proxy)
    
    try:
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            follow_redirects=True,
            transport=transport,
            headers={'User-Agent': settings.USER_AGENT}
        ) as client:
            response = await client.get(url)
            
            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                return None
            
            return response.text
            
    except Exception:
        return None
