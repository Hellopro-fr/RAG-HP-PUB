"""JWT de la gateway MCP HelloPro (client_credentials), gardé en cache."""
import threading
import time
from typing import Callable, Optional

import httpx


class ErreurJetonMcp(Exception):
    pass


class JetonMcp:
    """POST {gateway}/token ; renouvelé 60 s avant expiration (durée de vie 3600 s par défaut)."""

    MARGE_S = 60

    def __init__(self, url_gateway: str, client_id: str, client_secret: str,
                 client_http: Optional[httpx.Client] = None, horloge: Callable[[], float] = time.time):
        self._url = url_gateway.rstrip("/") + "/token"
        self._identifiants = {"grant_type": "client_credentials", "client_id": client_id,
                              "client_secret": client_secret}
        self._http = client_http or httpx.Client(timeout=15)
        self._horloge = horloge
        self._jeton: Optional[str] = None
        self._expire_a = 0.0
        self._verrou = threading.Lock()

    def obtenir(self) -> str:
        with self._verrou:
            if self._jeton and self._horloge() < self._expire_a - self.MARGE_S:
                return self._jeton
            try:
                reponse = self._http.post(self._url, data=self._identifiants)
                reponse.raise_for_status()
                corps = reponse.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ErreurJetonMcp(f"jeton MCP indisponible : {exc}") from exc
            if not corps.get("access_token"):
                raise ErreurJetonMcp("jeton MCP absent de la réponse de /token")
            self._jeton = corps["access_token"]
            self._expire_a = self._horloge() + float(corps.get("expires_in", 3600))
            return self._jeton
