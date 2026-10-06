"""
Tests unitaires pour application/normalization_use_case.py.

Couvre :
  - normalize_quantity / normalize_range délèguent au normalizer injecté
  - unit == "null" est converti en None avant la délégation
  - unit is None reste None (pass-through)
  - Les deux méthodes transmettent tous les autres arguments sans les modifier
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from application.normalization_use_case import NormalizationUseCase
from infrastructure.referentiel_loader import Referentiel
from infrastructure.unit_normalization_service import UnitNormalizationService
from scripts.legacy_referentiel import build_legacy_payload


# ---------------------------------------------------------------------------
# Stub normalizer — enregistre les arguments reçus sans vraiment normaliser
# ---------------------------------------------------------------------------

class _RecordingNormalizer:
    """Remplace UnitNormalizationService : enregistre les appels pour inspection."""

    def __init__(self):
        self.normalize_calls = []
        self.normalize_range_calls = []
        self._normalize_return = {"valeur_canonique": 1.0, "unite_canonique": "kilogram"}
        self._range_return = {
            "valeur_min_canonique": 1.0,
            "valeur_max_canonique": 2.0,
            "unite_canonique": "kilogram",
        }

    def normalize(
        self, label: str, unit: Optional[str], value: Any, data_type: str
    ) -> Dict[str, Any]:
        self.normalize_calls.append(
            {"label": label, "unit": unit, "value": value, "data_type": data_type}
        )
        return self._normalize_return

    def normalize_range(
        self, label: str, unit: Optional[str], min_val: float, max_val: float
    ) -> Dict[str, Any]:
        self.normalize_range_calls.append(
            {"label": label, "unit": unit, "min_val": min_val, "max_val": max_val}
        )
        return self._range_return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _use_case_with_stub() -> tuple["NormalizationUseCase", "_RecordingNormalizer"]:
    stub = _RecordingNormalizer()
    uc = NormalizationUseCase(stub)
    return uc, stub


def _use_case_with_real_normalizer() -> "NormalizationUseCase":
    referentiel = Referentiel.from_payload(build_legacy_payload())
    normalizer = UnitNormalizationService(referentiel)
    return NormalizationUseCase(normalizer)


# ===========================================================================
# normalize_quantity — délégation
# ===========================================================================


class TestNormalizeQuantityDelegation:
    def test_delegates_to_normalizer(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "kg", 10.0, "numeric")
        assert len(stub.normalize_calls) == 1

    def test_delegates_label_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Hauteur", "mm", 500, "numeric")
        assert stub.normalize_calls[0]["label"] == "Hauteur"

    def test_delegates_value_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "kg", 42.5, "numeric")
        assert stub.normalize_calls[0]["value"] == 42.5

    def test_delegates_data_type_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "kg", 1, "numeric")
        assert stub.normalize_calls[0]["data_type"] == "numeric"

    def test_returns_normalizer_result(self):
        uc, stub = _use_case_with_stub()
        stub._normalize_return = {"valeur_canonique": 99.0, "unite_canonique": "meter"}
        result = uc.normalize_quantity("Hauteur", "mm", 99000, "numeric")
        assert result == {"valeur_canonique": 99.0, "unite_canonique": "meter"}

    def test_delegates_normal_unit_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "kg", 10.0, "numeric")
        assert stub.normalize_calls[0]["unit"] == "kg"


# ===========================================================================
# normalize_quantity — conversion unit "null" / None -> None
# ===========================================================================


class TestNormalizeQuantityNullHandling:
    def test_unit_string_null_converted_to_none_before_delegation(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "null", 10.0, "numeric")
        assert stub.normalize_calls[0]["unit"] is None

    def test_unit_none_stays_none_before_delegation(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", None, 10.0, "numeric")
        assert stub.normalize_calls[0]["unit"] is None

    def test_unit_null_not_confused_with_real_unit(self):
        """Ensure a unit literally named 'null' is not forwarded as the string 'null'."""
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "null", 10.0, "numeric")
        received_unit = stub.normalize_calls[0]["unit"]
        assert received_unit != "null"

    def test_unit_null_uppercase_not_converted(self):
        """'NULL' (uppercase) is a different string — must NOT be converted to None."""
        uc, stub = _use_case_with_stub()
        uc.normalize_quantity("Poids", "NULL", 10.0, "numeric")
        assert stub.normalize_calls[0]["unit"] == "NULL"

    def test_unit_null_with_real_normalizer_does_not_raise(self):
        """Integration: passing 'null' with the real normalizer must not raise."""
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_quantity("Poids", "null", 10.0, "numeric")
        assert isinstance(result, dict)

    def test_unit_none_with_real_normalizer_does_not_raise(self):
        """Integration: passing None with the real normalizer must not raise."""
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_quantity("Poids", None, 10.0, "numeric")
        assert isinstance(result, dict)


# ===========================================================================
# normalize_range — délégation
# ===========================================================================


class TestNormalizeRangeDelegation:
    def test_delegates_to_normalizer(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", "mm", 100.0, 2500.0)
        assert len(stub.normalize_range_calls) == 1

    def test_delegates_label_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", "mm", 100.0, 2500.0)
        assert stub.normalize_range_calls[0]["label"] == "Hauteur"

    def test_delegates_min_max_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", "mm", 100.0, 2500.0)
        call = stub.normalize_range_calls[0]
        assert call["min_val"] == 100.0
        assert call["max_val"] == 2500.0

    def test_returns_normalizer_result(self):
        uc, stub = _use_case_with_stub()
        stub._range_return = {
            "valeur_min_canonique": 0.1,
            "valeur_max_canonique": 2.5,
            "unite_canonique": "meter",
        }
        result = uc.normalize_range("Hauteur", "mm", 100.0, 2500.0)
        assert result == {
            "valeur_min_canonique": 0.1,
            "valeur_max_canonique": 2.5,
            "unite_canonique": "meter",
        }

    def test_delegates_normal_unit_unchanged(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Poids", "kg", 50.0, 200.0)
        assert stub.normalize_range_calls[0]["unit"] == "kg"


# ===========================================================================
# normalize_range — conversion unit "null" / None -> None
# ===========================================================================


class TestNormalizeRangeNullHandling:
    def test_unit_string_null_converted_to_none(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", "null", 100.0, 2500.0)
        assert stub.normalize_range_calls[0]["unit"] is None

    def test_unit_none_stays_none(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", None, 100.0, 2500.0)
        assert stub.normalize_range_calls[0]["unit"] is None

    def test_unit_null_not_forwarded_as_string(self):
        uc, stub = _use_case_with_stub()
        uc.normalize_range("Hauteur", "null", 100.0, 2500.0)
        assert stub.normalize_range_calls[0]["unit"] != "null"

    def test_unit_null_with_real_normalizer_does_not_raise(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_range("Hauteur", "null", 100.0, 2500.0)
        assert isinstance(result, dict)

    def test_unit_none_with_real_normalizer_does_not_raise(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_range("Hauteur", None, 100.0, 2500.0)
        assert isinstance(result, dict)


# ===========================================================================
# Concrete value assertions using the real normalizer (not stub)
# ===========================================================================


class TestNormalizeQuantityConcreteValues:
    """Vérifie des valeurs canoniques concrètes avec le vrai moteur."""

    def test_kg_to_kilogram_canonical(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_quantity("Poids", "kg", 5.0, "numeric")
        assert result.get("unite_canonique") == "kilogram"
        assert result.get("valeur_canonique") == pytest.approx(5.0)

    def test_mm_to_meter_canonical(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_quantity("Hauteur", "mm", 1000.0, "numeric")
        assert result.get("unite_canonique") == "meter"
        assert result.get("valeur_canonique") == pytest.approx(1.0)

    def test_percent_bypass_returns_count(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_quantity("Humidite", "%", 60.0, "numeric")
        assert result.get("unite_canonique") == "count"
        assert result.get("valeur_canonique") == pytest.approx(60.0)

    def test_null_unit_with_label_resolves_via_label(self):
        """When unit is 'null', dimension must resolve via label fallback."""
        uc = _use_case_with_real_normalizer()
        result_null = uc.normalize_quantity("Poids", "null", 10.0, "numeric")
        result_none = uc.normalize_quantity("Poids", None, 10.0, "numeric")
        # Both paths must produce the same result (both convert 'null'/None to None)
        assert result_null == result_none


class TestNormalizeRangeConcreteValues:
    def test_range_mm_produces_meter_range(self):
        uc = _use_case_with_real_normalizer()
        result = uc.normalize_range("Hauteur", "mm", 100.0, 2000.0)
        assert result.get("unite_canonique") == "meter"
        assert result.get("valeur_min_canonique") == pytest.approx(0.1)
        assert result.get("valeur_max_canonique") == pytest.approx(2.0)

    def test_range_null_unit_equals_none_unit(self):
        uc = _use_case_with_real_normalizer()
        result_null = uc.normalize_range("Poids", "null", 50.0, 200.0)
        result_none = uc.normalize_range("Poids", None, 50.0, 200.0)
        assert result_null == result_none
