import httpx
import json
import logging
import uuid
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class RedirectTracker:
    def __init__(self):
        self._redirects: List[Dict[str, Any]] = []
        self._final_url: Optional[str] = None

    @property
    def redirects(self) -> List[Dict[str, Any]]:
        return self._redirects

    @redirects.setter
    def redirects(self, value: List[Dict[str, Any]]):
        self._redirects = value

    @property
    def final_url(self) -> Optional[str]:
        return self._final_url

    @final_url.setter
    def final_url(self, value: Optional[str]):
        self._final_url = value

    def get_redirects(self) -> List[Dict[str, Any]]:
        return self._redirects

    def get_final_url(self) -> Optional[str]:
        return self._final_url

    def get_initial_url(self) -> Optional[str]:
        return self._redirects[0]['from'] if self._redirects else None

    def get_redirect_chain(self) -> List[str]:
        return [r['to'] for r in self._redirects]

    async def get_url_redirection(
        self,
        url: str,
        proxy_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tracks redirects for a given URL using httpx.
        Mimics got-scraping behavior from Node.js.
        """
        self._redirects = []
        self._final_url = None

        try:
            # Configure proxies if provided
            mounts = {}
            if proxy_url:
                mounts = {
                    "http://": httpx.AsyncHTTPTransport(proxy=proxy_url),
                    "https://": httpx.AsyncHTTPTransport(proxy=proxy_url),
                }

            async with httpx.AsyncClient(mounts=mounts, timeout=5.0, follow_redirects=True, max_redirects=10) as client:
                response = await client.get(url)
                
                # Process redirect history
                current_url = url
                
                # response.history contains the list of responses (3xx) that led to the final response
                for resp in response.history:
                    # Determine target URL from next_request or Location header
                    target_url = ""
                    if hasattr(resp, 'next_request') and resp.next_request:
                         target_url = str(resp.next_request.url)
                    
                    if not target_url:
                        target_url = resp.headers.get("Location", "")
                        # Handle relative redirects if needed (httpx usually resolves this but just in case)
                        if target_url.startswith("/"):
                            # This is a simplification; httpx next_request is preferred
                            pass 

                    self._redirects.append({
                        "from": str(resp.url),
                        "to": target_url,
                    })
                
                self._final_url = str(response.url)
                
                return {
                    "success": True,
                    "initial_url": self.get_initial_url(),
                    "final_url": self._final_url if self._final_url else url,
                    "redirects": self.get_redirects(),
                    "redirect_chain": self.get_redirect_chain(),
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                }

        except Exception as e:
            logger.error(f"Error in get_url_redirection: {e}")
            raise Exception(json.dumps({
                "success": False,
                "error": str(e),
                "redirects": self.get_redirects(),
                "redirect_chain": self.get_redirect_chain(),
                "status_code": 0,
            }))

    @staticmethod
    async def get_url_redirection_pemavor(
        urls: List[str],
        internal: str = "no"
    ) -> Dict[str, Any]:
        """
        Uses Pemavor external service to check redirects.
        Used as a fallback when local check fails.
        """
        try:
            # We use the 'files' parameter to force multipart/form-data encoding
            # even though we are sending text fields.
            files = {
                'url': (None, json.dumps(urls)),
                'internal': (None, internal)
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://europe-west1-pemavor-free-tools.cloudfunctions.net/HttpStatusCodeChecker",
                    files=files
                )
                
                if response.status_code == 200:
                    response_data = response.json()
                    return {
                        "success": True,
                        "data": response_data,
                        "status_code": response.status_code
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}",
                        "status_code": response.status_code
                    }

        except Exception as e:
            logger.error(f"Error in get_url_redirection_pemavor: {e}")
            raise Exception(json.dumps({
                "success": False,
                "error": str(e),
                "status_code": 0,
            }))
