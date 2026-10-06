"""Client HTTP vers le service de normalisation dynamique.

Gate 1 FIDÈLE : on délègue la validation au VRAI moteur via /admin/validate
(préprocessing + réécritures + désambiguïsation inclus), au lieu d'une ré-implémentation
pint partielle. Source unique de vérité = le moteur dynamique.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class DynamicValidationError(Exception):
    """Échec d'APPEL à /admin/validate (réseau/HTTP) — distinct d'une validation 'nok'.

    `permanent` :
      - True  -> 4xx : corps/contrat invalide (bug à corriger, ne se résoudra pas en réessayant)
      - False -> 5xx / timeout / réseau : transitoire (réessayer à un prochain run)
    """

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


async def validate(proposed: Dict[str, Any], label: str, unit: Optional[str], values: List[Any]) -> Dict[str, Any]:
    """Appelle /admin/validate avec TOUTES les valeurs (min ET max) en un seul appel.
    Retourne {ok, valeur_canonique, unite_canonique} (ok ssi toutes se normalisent).

    Lève DynamicValidationError (permanent=True sur 4xx, False sinon) — traité comme une
    ERREUR DE TRAITEMENT (pas comme une validation 'nok')."""
    url = settings.DYNAMIC_SERVICE_URL.rstrip("/") + "/admin/validate"
    body = {"proposed": proposed, "label": label, "unit": unit, "values": values}
    try:
        async with httpx.AsyncClient(timeout=settings.DYNAMIC_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        permanent = 400 <= status < 500
        logger.error("/admin/validate HTTP %s (%s)", status, "contrat" if permanent else "transitoire")
        raise DynamicValidationError(f"HTTP {status} sur /admin/validate", permanent=permanent) from exc
    except Exception as exc:
        logger.error("Appel /admin/validate échoué (transitoire): %s", exc)
        raise DynamicValidationError(str(exc), permanent=False) from exc
