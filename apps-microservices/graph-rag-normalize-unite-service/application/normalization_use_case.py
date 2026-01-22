from typing import Dict, Any, Optional
from infrastructure.unit_normalization_service import unit_normalizer


class NormalizationUseCase:
    """
    Application layer Use Case for Unit Normalization.
    Orchestrates calls to the infrastructure service.
    """

    def __init__(self):
        self.normalizer = unit_normalizer

    def normalize_quantity(
        self, label: str, unit: str, value: Any, data_type: str
    ) -> Dict[str, Any]:
        """
        Normalize a single quantity.
        """
        # Clean inputs
        if unit == "null" or unit is None:
            unit = None

        return self.normalizer.normalize(label, unit, value, data_type)

    def normalize_range(
        self, label: str, unit: str, min_value: float, max_value: float
    ) -> Dict[str, Any]:
        """
        Normalize a range.
        """
        if unit == "null" or unit is None:
            unit = None

        return self.normalizer.normalize_range(label, unit, min_value, max_value)
