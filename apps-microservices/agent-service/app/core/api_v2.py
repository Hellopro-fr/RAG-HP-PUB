"""Client de l'étape « agents » de l'API v2 PHP : fiches et journal (aucun accès MySQL direct)."""
import logging
import threading
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


class ErreurApiV2(Exception):
    pass


class ClientApiV2:
    """La version publiée est gardée ttl_cache_s en cache : une publication s'applique en moins d'une minute."""

    def __init__(self, url: str, jeton: str, ttl_cache_s: int = 60,
                 client_http: Optional[httpx.Client] = None, horloge: Callable[[], float] = time.time):
        self._url = url
        self._entetes = {"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"}
        self._http = client_http or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self._ttl = ttl_cache_s
        self._horloge = horloge
        self._cache = {}
        self._verrou = threading.Lock()

    def _appeler(self, field: str, action: str, data: dict):
        charge = {"etape": "agents", "field": field, "action": action, "data": data}
        try:
            corps = self._http.post(self._url, json=charge, headers=self._entetes).json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ErreurApiV2(f"API v2 injoignable : {exc}") from exc
        if corps.get("code") != 200:
            raise ErreurApiV2(f"API v2 agents/{field}/{action} : code {corps.get('code')} {corps.get('error', '')}")
        return corps.get("response")

    def lire_fiche(self, code: str, version: str = "publiee") -> dict:
        cle = (code, version)
        if version == "publiee":
            with self._verrou:
                en_cache = self._cache.get(cle)
                if en_cache and self._horloge() - en_cache[0] < self._ttl:
                    return en_cache[1]
        fiche = self._appeler("config", "get", {"code": code, "version": version}) or {}
        if version == "publiee" and fiche.get("trouve"):
            with self._verrou:
                self._cache[cle] = (self._horloge(), fiche)
        return fiche

    def enregistrer_execution(self, execution: dict) -> dict:
        """Ne lève jamais : un journal perdu ne doit pas faire échouer l'appel de l'agent."""
        try:
            resultat = self._appeler("execution", "save", execution) or {}
        except ErreurApiV2 as exc:
            logger.error("journal non écrit : %s", exc)
            return {"id_execution": None, "cout": None}
        if not resultat.get("enregistre"):
            logger.error("journal refusé : %s", resultat.get("erreur"))
            return {"id_execution": None, "cout": None}
        return {"id_execution": resultat.get("id_execution"), "cout": resultat.get("cout")}
