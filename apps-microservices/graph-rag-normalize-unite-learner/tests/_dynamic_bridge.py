"""
Pont in-process learner → VRAI moteur de normalisation dynamique (pour tests de symbiose).

Au lieu d'appeler /admin/validate par HTTP, on instancie le **vrai** moteur
(`UnitNormalizationService.validate_proposed`) du service dynamique, alimenté par le
référentiel test simulé. Le learner branche ce moteur comme `validate_fn` → la Gate 1
exécutée pendant le test est EXACTEMENT celle de la prod.

Import cross-service : le service dynamique a les packages `infrastructure` / `scripts`
(absents du learner), et `app` (présent des 2 côtés). On APPEND la racine du service
dynamique à sys.path : `app` reste résolu côté learner (inséré en tête par son conftest),
`infrastructure`/`scripts` ne résolvent que côté dynamique. `referentiel_loader` importe
`from app.config import settings` mais ne l'utilise PAS sur le chemin from_payload/validate.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_DYNAMIC_ROOT = (
    Path(__file__).resolve().parents[2] / "graph-rag-normalize-unite-service-dynamique"
)
if str(_DYNAMIC_ROOT) not in sys.path:
    sys.path.append(str(_DYNAMIC_ROOT))

from infrastructure.referentiel_loader import Referentiel  # noqa: E402  (dynamique)
from infrastructure.unit_normalization_service import UnitNormalizationService  # noqa: E402
from scripts.legacy_referentiel import (  # noqa: E402
    simulate_get_apprentissage_unite,
    simulate_get_referentiel_normalisation,
)

__all__ = [
    "simulate_get_referentiel_normalisation",
    "simulate_get_apprentissage_unite",
    "make_real_validate_fn",
    "build_real_normalizer",
]


def build_real_normalizer(referentiel_payload: Optional[Dict[str, Any]] = None) -> UnitNormalizationService:
    """Construit le VRAI moteur dynamique à partir du référentiel test (par défaut : seed complet)."""
    payload = referentiel_payload if referentiel_payload is not None else simulate_get_referentiel_normalisation()
    return UnitNormalizationService(Referentiel.from_payload(payload))


def make_real_validate_fn(referentiel_payload: Optional[Dict[str, Any]] = None):
    """Retourne une `validate_fn` (signature de dynamic_client.validate) branchée sur le VRAI moteur.
    C'est la Gate 1 réelle : preprocessing + réécritures + désambiguïsation du service dynamique."""
    normalizer = build_real_normalizer(referentiel_payload)

    async def validate_fn(proposed: Dict[str, Any], label: str, unit: Optional[str], values: List[Any]) -> Dict[str, Any]:
        return normalizer.validate_proposed(proposed, label, unit, values)

    return validate_fn
