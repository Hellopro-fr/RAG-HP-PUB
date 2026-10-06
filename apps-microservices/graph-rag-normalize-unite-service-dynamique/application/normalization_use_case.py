from typing import Any, Dict

from infrastructure.unit_normalization_service import UnitNormalizationService


class NormalizationUseCase:
    """
    Use Case applicatif pour la normalisation d'unités.
    Le normalizer (état rechargeable) est INJECTÉ : il n'existe pas de singleton
    construit à l'import, car il dépend du référentiel chargé au démarrage.
    """

    def __init__(self, normalizer: UnitNormalizationService):
        self.normalizer = normalizer

    def normalize_quantity(
        self, label: str, unit: str, value: Any, data_type: str
    ) -> Dict[str, Any]:
        if unit == "null" or unit is None:
            unit = None
        return self.normalizer.normalize(label, unit, value, data_type)

    def normalize_range(
        self, label: str, unit: str, min_value: float, max_value: float
    ) -> Dict[str, Any]:
        if unit == "null" or unit is None:
            unit = None
        return self.normalizer.normalize_range(label, unit, min_value, max_value)
