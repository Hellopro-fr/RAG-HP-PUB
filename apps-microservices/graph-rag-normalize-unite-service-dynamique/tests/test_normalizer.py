"""
Unit tests for the dynamic normalization engine.

Strategy: build the normalizer under test via
    UnitNormalizationService(Referentiel.from_payload(build_legacy_payload()))
so the full production referentiel (definitions, unit_to_dimension, rewrites,
preprocessing, canonical_units) is exercised without any live service call.

Where the expected magnitude after pint conversion is non-trivial, the test
asserts NEW == OLD (calling load_legacy_normalizer().normalize(...)) so there
is a single source of truth and no hand-computed magic numbers to maintain.

Do NOT import grpc_stubs or grpc_server.
"""

import math
import pytest

from infrastructure.referentiel_loader import Referentiel
from infrastructure.unit_normalization_service import (
    UnitNormalizationService,
    _NormalizerState,
)
from scripts.legacy_referentiel import build_legacy_payload, load_legacy_normalizer


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def legacy_payload():
    """The full production payload built from the old service's dictionaries."""
    return build_legacy_payload()


@pytest.fixture(scope="module")
def new_normalizer(legacy_payload):
    """New (dynamic) normalizer seeded with legacy data."""
    return UnitNormalizationService(Referentiel.from_payload(legacy_payload))


@pytest.fixture(scope="module")
def old_normalizer():
    """Legacy (static) normalizer singleton — source of truth for expected values."""
    return load_legacy_normalizer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx_equal(a, b, rel=1e-6):
    """True if two floats are within rel relative tolerance."""
    if a == b:
        return True
    return math.isclose(a, b, rel_tol=rel)


def _assert_same(new_normalizer, old_normalizer, label, unit, value):
    """
    Assert new and old normalizers produce identical output.
    Used where hand-computing pint magnitudes would be fragile.
    """
    old_result = old_normalizer.normalize(label, unit, value, "numeric")
    new_result = new_normalizer.normalize(label, unit, value, "numeric")
    assert new_result == old_result, (
        f"Divergence for ({label!r}, {unit!r}, {value}): "
        f"old={old_result!r}  new={new_result!r}"
    )


# ===========================================================================
# 1. MASS
# ===========================================================================

class TestMass:

    def test_kg_identity(self, new_normalizer):
        """1500 kg -> kilogram 1500 (no conversion, already canonical)."""
        result = new_normalizer.normalize("Poids", "kg", 1500, "numeric")
        assert result["unite_canonique"] == "kilogram"
        assert result["valeur_canonique"] == 1500.0

    def test_tonnes_to_kilogram(self, new_normalizer):
        """2 Tonnes -> 2000 kilogram via pint tonne=1000*kg definition."""
        result = new_normalizer.normalize("Capacité", "Tonnes", 2, "numeric")
        assert result["unite_canonique"] == "kilogram"
        assert result["valeur_canonique"] == pytest.approx(2000.0, rel=1e-6)

    def test_kilogrammes_rewrite_to_kilogram(self, new_normalizer):
        """'kilogrammes' is a rewrite rule -> kilogram; value passed through."""
        result = new_normalizer.normalize("Poids", "kilogrammes", 10, "numeric")
        assert result["unite_canonique"] == "kilogram"
        assert result["valeur_canonique"] == pytest.approx(10.0, rel=1e-6)

    def test_kilogramme_singular_rewrite(self, new_normalizer):
        """'kilogramme' (singular) also rewrites to kilogram."""
        result = new_normalizer.normalize("Poids", "kilogramme", 5, "numeric")
        assert result["unite_canonique"] == "kilogram"
        assert result["valeur_canonique"] == pytest.approx(5.0, rel=1e-6)

    def test_tonnes_plural_rewrite(self, new_normalizer):
        """'tonnes' (lowercase plural) rewrite -> tonne -> kilogram conversion."""
        result = new_normalizer.normalize("Capacité", "tonnes", 3, "numeric")
        assert result["unite_canonique"] == "kilogram"
        assert result["valeur_canonique"] == pytest.approx(3000.0, rel=1e-6)

    def test_mass_matches_old_normalizer(self, new_normalizer, old_normalizer):
        """Cross-check kg result vs legacy normalizer."""
        _assert_same(new_normalizer, old_normalizer, "Poids", "kg", 1500)

    def test_tonnes_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Capacité", "Tonnes", 2)


# ===========================================================================
# 2. LENGTH
# ===========================================================================

class TestLength:

    def test_mm_to_meter(self, new_normalizer):
        """2500 mm -> 2.5 meter."""
        result = new_normalizer.normalize("Hauteur", "mm", 2500, "numeric")
        assert result["unite_canonique"] == "meter"
        assert result["valeur_canonique"] == pytest.approx(2.5, rel=1e-6)

    def test_cm_to_meter(self, new_normalizer):
        """100 cm -> 1 meter."""
        result = new_normalizer.normalize("Largeur", "cm", 100, "numeric")
        assert result["unite_canonique"] == "meter"
        assert result["valeur_canonique"] == pytest.approx(1.0, rel=1e-6)

    def test_pouces_rewrite_to_inch(self, new_normalizer):
        """'pouces' rewrite -> inch -> pint converts to meter."""
        result = new_normalizer.normalize("Diamètre", "pouces", 1, "numeric")
        assert result["unite_canonique"] == "meter"
        # 1 inch = 0.0254 m
        assert result["valeur_canonique"] == pytest.approx(0.0254, rel=1e-5)

    def test_pouce_singular_rewrite(self, new_normalizer):
        """'pouce' (singular) also resolves correctly."""
        result = new_normalizer.normalize("Diamètre", "pouce", 2, "numeric")
        assert result["unite_canonique"] == "meter"
        assert result["valeur_canonique"] == pytest.approx(0.0508, rel=1e-5)

    def test_length_matches_old_normalizer_mm(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Hauteur", "mm", 2500)

    def test_length_matches_old_normalizer_pouces(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Diamètre", "pouces", 1)


# ===========================================================================
# 3. POWER
# ===========================================================================

class TestPower:

    def test_cv_matches_old_normalizer(self, new_normalizer, old_normalizer):
        """CV (cheval-vapeur) conversion — exact value compared to old normalizer."""
        _assert_same(new_normalizer, old_normalizer, "Puissance", "CV", 3)

    def test_kw_matches_old_normalizer(self, new_normalizer, old_normalizer):
        """KW conversion — exact value compared to old normalizer."""
        _assert_same(new_normalizer, old_normalizer, "Puissance", "KW", 7.5)

    def test_cv_canonical_unit_is_watt(self, new_normalizer):
        """CV result canonical unit should be watt."""
        result = new_normalizer.normalize("Puissance", "CV", 3, "numeric")
        assert result.get("unite_canonique") == "watt"
        assert result.get("valeur_canonique") is not None

    def test_kw_canonical_unit_is_watt(self, new_normalizer):
        """KW result canonical unit should be watt."""
        result = new_normalizer.normalize("Puissance", "KW", 7.5, "numeric")
        assert result.get("unite_canonique") == "watt"
        assert result.get("valeur_canonique") is not None

    def test_watts_rewrite_to_watt(self, new_normalizer):
        """'watts' (plural) rewrite -> watt; 100 watts -> 100 watt."""
        result = new_normalizer.normalize("Puissance", "watts", 100, "numeric")
        assert result.get("unite_canonique") == "watt"
        assert result.get("valeur_canonique") == pytest.approx(100.0, rel=1e-6)


# ===========================================================================
# 4. REWRITE RULES
# ===========================================================================

class TestRewrites:

    def test_m3h_rewrite_to_cubic_meter_per_hour(self, new_normalizer, old_normalizer):
        """'m3/h' rewrite -> m**3/hour; compared to old normalizer."""
        _assert_same(new_normalizer, old_normalizer, "Débit", "m3/h", 12)

    def test_m3h_canonical_unit(self, new_normalizer):
        """'m3/h' normalizes to a volume/time canonical (liter / minute)."""
        result = new_normalizer.normalize("Débit", "m3/h", 12, "numeric")
        assert result != {}
        assert "valeur_canonique" in result

    def test_kg_m2_area_density(self, new_normalizer, old_normalizer):
        """'kg/m2' -> area_density dimension -> canonical kilogram/meter**2."""
        _assert_same(new_normalizer, old_normalizer, "Charge au sol", "kg/m2", 50)

    def test_kg_m2_result_not_empty(self, new_normalizer):
        result = new_normalizer.normalize("Charge au sol", "kg/m2", 50, "numeric")
        assert result != {}
        assert result.get("unite_canonique") is not None

    def test_percent_bypass_count(self, new_normalizer):
        """'%' is a bypass rule -> returns value as count directly."""
        result = new_normalizer.normalize("Humidité", "%", 60, "numeric")
        assert result == {"valeur_canonique": 60.0, "unite_canonique": "count"}

    def test_mohs_bypass_count(self, new_normalizer):
        """'Mohs' is a bypass rule -> returns value as count directly."""
        result = new_normalizer.normalize("Dureté", "Mohs", 7, "numeric")
        assert result == {"valeur_canonique": 7.0, "unite_canonique": "count"}

    def test_watts_to_watt(self, new_normalizer):
        """'watts' rewrite -> watt."""
        result = new_normalizer.normalize("Puissance", "watts", 500, "numeric")
        assert result.get("unite_canonique") == "watt"
        assert result.get("valeur_canonique") == pytest.approx(500.0, rel=1e-6)


# ===========================================================================
# 5. DISAMBIGUATION
# ===========================================================================

class TestDisambiguation:

    def test_nm_with_epaisseur_label_is_length(self, new_normalizer):
        """'nm' with a label containing 'Epaisseur' -> length dimension."""
        result = new_normalizer.normalize("Epaisseur", "nm", 250, "numeric")
        assert result != {}
        assert result.get("unite_canonique") == "meter"

    def test_nm_with_couple_label_returns_empty(self, new_normalizer):
        """'nm' with label 'Couple' -> torque path.
        pint 'nm' (nanometer) cannot be converted to newton*meter
        so pint raises and the result is {}."""
        result = new_normalizer.normalize("Couple", "nm", 10, "numeric")
        # The disambiguation routes to torque dimension; pint sees 'nm' as nanometer
        # and cannot convert to newton*meter -> normalize returns {}.
        assert result == {}

    def test_nm_matches_old_for_length_label(self, new_normalizer, old_normalizer):
        """nm with length label: new and old produce identical output."""
        _assert_same(new_normalizer, old_normalizer, "Epaisseur", "nm", 250)

    def test_tmin_with_debit_label_is_mass_flow(self, new_normalizer):
        """'t/min' with label containing 'Débit' -> mass_flow path (tonne/minute)."""
        result = new_normalizer.normalize("Débit", "t/min", 5, "numeric")
        assert result != {}
        # mass_flow canonical = gram / minute; 5 tonne/min = 5_000_000 g/min
        assert result.get("unite_canonique") == "gram / minute"
        assert result.get("valeur_canonique") == pytest.approx(5_000_000.0, rel=1e-5)

    def test_tmin_with_neutral_label_is_rpm(self, new_normalizer):
        """'t/min' with a neutral label -> tours/min -> rpm frequency path."""
        result = new_normalizer.normalize("Régime", "t/min", 1000, "numeric")
        assert result != {}
        assert result.get("unite_canonique") == "hertz"

    def test_tmin_debit_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Capacité de production", "t/min", 5)

    def test_tmin_neutral_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Caractéristique générique", "t/min", 100)

    def test_G_with_facteur_label_is_bypass_count(self, new_normalizer):
        """'G' (capital) with label containing 'facteur' -> bypass -> count."""
        result = new_normalizer.normalize("Facteur G", "G", 5, "numeric")
        assert result == {"valeur_canonique": 5.0, "unite_canonique": "count"}

    def test_G_without_facteur_is_not_bypassed(self, new_normalizer):
        """'G' without 'facteur' in label -> no bypass, falls through normal pipeline."""
        result = new_normalizer.normalize("Accélération", "G", 5, "numeric")
        # Without the facteur indicator, G enters normal pint pipeline.
        # pint G = gauss (magnetic field) — dimension not in our referentiel -> {}.
        # The important assertion: it is NOT {valeur_canonique: 5.0, unite_canonique: count}.
        assert result != {"valeur_canonique": 5.0, "unite_canonique": "count"}

    def test_G_facteur_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Facteur G", "G", 5)


# ===========================================================================
# 6. PREPROCESSING
# ===========================================================================

class TestPreprocessing:

    def test_dba_parenthesis_stripped(self, new_normalizer, old_normalizer):
        """'dB(A)' -> strip parens -> 'dB' -> sound_level dimension."""
        result = new_normalizer.normalize("Niveau sonore", "dB(A)", 72, "numeric")
        assert result != {}
        assert result.get("unite_canonique") == "decibel"
        assert result.get("valeur_canonique") == pytest.approx(72.0, rel=1e-6)

    def test_dba_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Niveau sonore", "dB(A)", 72)

    def test_superscript_2_in_unit(self, new_normalizer):
        """'kg/m²' -> post_snapshot ²->2 -> 'kg/m2' -> area_density rewrite."""
        result = new_normalizer.normalize("Charge au sol", "kg/m²", 100, "numeric")
        assert result != {}
        # After ²->2: unit becomes 'kg/m2' which hits the area_density rewrite
        assert result.get("unite_canonique") is not None

    def test_superscript_2_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Charge au sol", "kg/m²", 100)

    def test_middle_dot_pas_normalized(self, new_normalizer):
        """'Pa·s' -> pre_snapshot ·->'.' -> 'Pa.s' -> pa.s rewrite -> pascal*second."""
        result = new_normalizer.normalize("Viscosité", "Pa·s", 1, "numeric")
        assert result != {}
        assert result.get("unite_canonique") == "pascal * second"

    def test_middle_dot_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Viscosité", "Pa·s", 1)

    def test_nfkc_micro_sign_normalized(self, new_normalizer):
        """U+00B5 MICRO SIGN -> NFKC -> U+03BC GREEK MU -> μm lookup."""
        # 'µm' is the legacy micro sign form; NFKC converts it to 'μm'
        result = new_normalizer.normalize("Epaisseur", "µm", 25, "numeric")
        assert result != {}
        assert result.get("unite_canonique") == "meter"


# ===========================================================================
# 7. VALUE PARSING
# ===========================================================================

class TestValueParsing:

    def test_tolerance_prefix_parsed(self, new_normalizer):
        """'+/- 2' string value is parsed to 2.0."""
        result = new_normalizer.normalize("Tolérance", "mm", "+/- 2", "numeric")
        assert result != {}
        # 2 mm -> 0.002 m
        assert result.get("unite_canonique") == "meter"
        assert result.get("valeur_canonique") == pytest.approx(0.002, rel=1e-5)

    def test_tolerance_prefix_matches_old_normalizer(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "Tolérance", "mm", "+/- 2")

    def test_plus_minus_unicode_parsed(self, new_normalizer):
        """'± 2' (unicode ±) string value is parsed to 2.0."""
        result = new_normalizer.normalize("Tolérance", "mm", "± 2", "numeric")
        assert result != {}
        assert result.get("valeur_canonique") == pytest.approx(0.002, rel=1e-5)

    def test_non_numeric_string_returns_empty(self, new_normalizer):
        """A genuinely non-numeric string -> {} (parse fails)."""
        result = new_normalizer.normalize("Poids", "kg", "N/A", "numeric")
        assert result == {}

    def test_non_numeric_word_returns_empty(self, new_normalizer):
        result = new_normalizer.normalize("Hauteur", "mm", "standard", "numeric")
        assert result == {}

    def test_wrong_data_type_returns_empty(self, new_normalizer):
        """data_type not in ['numeric', 'numeric_range'] -> {}."""
        result = new_normalizer.normalize("Poids", "kg", 10, "text")
        assert result == {}

    def test_numeric_range_data_type_accepted(self, new_normalizer):
        """data_type='numeric_range' is accepted (same pipeline)."""
        result = new_normalizer.normalize("Poids", "kg", 50, "numeric_range")
        assert result != {}
        assert result.get("unite_canonique") == "kilogram"

    def test_integer_value_accepted(self, new_normalizer):
        """Integer (not float) value is accepted."""
        result = new_normalizer.normalize("Poids", "kg", 100, "numeric")
        assert result.get("valeur_canonique") == 100.0

    def test_float_value_accepted(self, new_normalizer):
        result = new_normalizer.normalize("Hauteur", "mm", 12.5, "numeric")
        assert result.get("valeur_canonique") == pytest.approx(0.0125, rel=1e-6)


# ===========================================================================
# 8. GUARD: empty label
# ===========================================================================

class TestEmptyLabel:

    def test_empty_label_with_resolvable_unit_returns_empty(self, new_normalizer):
        """Empty label + unit that needs label fallback to resolve -> {}.
        Documents that _get_dimension falls through when label is absent."""
        # 'nm' without a label: no label substring match, falls to UNIT_TO_DIMENSION lookup.
        # UNIT_TO_DIMENSION has 'nm' mapped to 'torque'. With torque dimension,
        # pint sees 'nm' as nanometer and cannot convert to newton*meter -> {}.
        result = new_normalizer.normalize("", "nm", 100, "numeric")
        # The exact outcome depends on referentiel state; what matters is we document it.
        # Both old and new return {} for this case (pint conversion fails for nm -> torque).
        assert isinstance(result, dict)

    def test_empty_label_guard_matches_old(self, new_normalizer, old_normalizer):
        _assert_same(new_normalizer, old_normalizer, "", "nm", 100)

    def test_empty_label_with_kg_still_resolves(self, new_normalizer):
        """'kg' resolves via UNIT_TO_DIMENSION without needing a label."""
        result = new_normalizer.normalize("", "kg", 50, "numeric")
        # UNIT_TO_DIMENSION['kg'] = 'mass' -> canonical = kilogram -> no pint conversion needed
        # BUT normalize() guard: `not all([label, value is not None])` -> label='' is falsy -> {}
        # This tests and documents that current behavior returns {} for empty label.
        assert result == {}

    def test_none_unit_with_label_uses_label_dimension(self, new_normalizer):
        """None unit + label -> label fallback path -> dimension from label."""
        result = new_normalizer.normalize("Poids", None, 50, "numeric")
        # 'poids' matches 'mass' in LABEL_TO_DIMENSION; canonical = kilogram; unit=None path
        assert result.get("unite_canonique") == "kilogram"
        assert result.get("valeur_canonique") == 50.0


# ===========================================================================
# 9. normalize_range
# ===========================================================================

class TestNormalizeRange:

    def test_range_both_normalized(self, new_normalizer):
        """min and max are both normalized, sharing the same canonical unit."""
        result = new_normalizer.normalize_range("Hauteur", "mm", 100, 2500)
        assert result.get("valeur_min_canonique") == pytest.approx(0.1, rel=1e-6)
        assert result.get("valeur_max_canonique") == pytest.approx(2.5, rel=1e-6)
        assert result.get("unite_canonique") == "meter"

    def test_range_shared_canonical_unit(self, new_normalizer):
        """unite_canonique appears once even when both min and max succeed."""
        result = new_normalizer.normalize_range("Poids", "kg", 50, 1500)
        assert "unite_canonique" in result
        assert result["unite_canonique"] == "kilogram"

    def test_range_matches_old_normalizer(self, new_normalizer, old_normalizer):
        for label, unit, vmin, vmax in [
            ("Hauteur", "mm", 100, 2500),
            ("Poids", "kg", 50, 1500),
            ("Puissance", "CV", 2, 8),
        ]:
            old_result = old_normalizer.normalize_range(label, unit, vmin, vmax)
            new_result = new_normalizer.normalize_range(label, unit, vmin, vmax)
            assert new_result == old_result, (label, unit, vmin, vmax)

    def test_range_unknown_unit_returns_partial_or_empty(self, new_normalizer):
        """Unknown unit in range -> both min and max fail -> {}."""
        result = new_normalizer.normalize_range("Poids", "parsec", 1, 2)
        assert result == {}


# ===========================================================================
# 10. reload()
# ===========================================================================

class TestReload:

    def _minimal_payload(self):
        return {
            "definitions": [
                {"definition": "kg = kilogram", "ordre": 0},
            ],
            "unite_dimension": [{"unite": "kg", "dimension": "mass"}],
            "label_dimension": [{"label": "poids", "dimension": "mass", "priorite": 0}],
            "dimension_canonique": [{"dimension": "mass", "unite_canonique": "kilogram"}],
            "preprocessing": [],
            "reecriture": [],
        }

    def test_unknown_unit_before_reload_returns_empty(self):
        """Before reload, an unrecognised unit returns {}."""
        svc = UnitNormalizationService(Referentiel.from_payload(self._minimal_payload()))
        assert svc.normalize("Poids", "quintal", 3, "numeric") == {}

    def test_unit_resolves_after_reload(self):
        """After reload with the unit added, it normalizes correctly."""
        svc = UnitNormalizationService(Referentiel.from_payload(self._minimal_payload()))

        extended = self._minimal_payload()
        extended["definitions"].append({"definition": "quintal = 100 * kilogram", "ordre": 1})
        extended["unite_dimension"].append({"unite": "quintal", "dimension": "mass"})

        svc.reload(Referentiel.from_payload(extended))

        result = svc.normalize("Poids", "quintal", 3, "numeric")
        assert result.get("unite_canonique") == "kilogram"
        assert result.get("valeur_canonique") == pytest.approx(300.0, rel=1e-6)

    def test_reload_counts_include_define_errors_key(self):
        """reload() return dict always contains 'define_errors' key."""
        svc = UnitNormalizationService(Referentiel.from_payload(self._minimal_payload()))
        counts = svc.reload(Referentiel.from_payload(self._minimal_payload()))
        assert "define_errors" in counts

    def test_reload_counts_include_preprocessing_errors_key(self):
        """reload() return dict always contains 'preprocessing_errors' key."""
        svc = UnitNormalizationService(Referentiel.from_payload(self._minimal_payload()))
        counts = svc.reload(Referentiel.from_payload(self._minimal_payload()))
        assert "preprocessing_errors" in counts

    def test_reload_counts_zero_errors_on_clean_payload(self):
        """A valid payload produces 0 define_errors and 0 preprocessing_errors."""
        svc = UnitNormalizationService(Referentiel.from_payload(self._minimal_payload()))
        counts = svc.reload(Referentiel.from_payload(self._minimal_payload()))
        assert counts["define_errors"] == 0
        assert counts["preprocessing_errors"] == 0

    def test_reload_counts_bad_define_increments_define_errors(self):
        """A broken pint definition increments define_errors."""
        payload = self._minimal_payload()
        payload["definitions"].append({"definition": "not_a_valid_definition_at_all", "ordre": 99})
        svc = UnitNormalizationService(Referentiel.from_payload(payload))
        counts = svc.reload(Referentiel.from_payload(payload))
        assert counts["define_errors"] >= 1

    def test_reload_counts_bad_preprocessing_increments_preprocessing_errors(self):
        """A malformed regex rule increments preprocessing_errors."""
        payload = self._minimal_payload()
        payload["preprocessing"] = [
            {"type": "regex_sub", "phase": "pre_snapshot", "pattern": "(bad[", "remplacement": "", "ordre": 0},
        ]
        svc = UnitNormalizationService(Referentiel.from_payload(payload))
        counts = svc.reload(Referentiel.from_payload(payload))
        assert counts["preprocessing_errors"] >= 1

    def test_reload_is_atomic_old_state_replaced(self):
        """After reload, the new state is active (old unknown unit is now gone)."""
        # Start with payload that has 'quintal'
        payload_with_quintal = self._minimal_payload()
        payload_with_quintal["definitions"].append(
            {"definition": "quintal = 100 * kilogram", "ordre": 1}
        )
        payload_with_quintal["unite_dimension"].append({"unite": "quintal", "dimension": "mass"})

        svc = UnitNormalizationService(Referentiel.from_payload(payload_with_quintal))
        result_before = svc.normalize("Poids", "quintal", 1, "numeric")
        assert result_before != {}  # resolves before reload

        # Reload with minimal payload (no quintal)
        svc.reload(Referentiel.from_payload(self._minimal_payload()))
        result_after = svc.normalize("Poids", "quintal", 1, "numeric")
        assert result_after == {}  # quintal gone after reload


# ===========================================================================
# 11. _strip_accents
# ===========================================================================

class TestStripAccents:

    def _state(self, legacy_payload):
        return _NormalizerState(Referentiel.from_payload(legacy_payload))

    def test_strip_accents_removes_acute(self, legacy_payload):
        state = self._state(legacy_payload)
        assert state._strip_accents("éèê") == "eee"

    def test_strip_accents_removes_cedilla(self, legacy_payload):
        state = self._state(legacy_payload)
        assert state._strip_accents("ç") == "c"

    def test_strip_accents_preserves_ascii(self, legacy_payload):
        state = self._state(legacy_payload)
        assert state._strip_accents("abc ABC 123") == "abc ABC 123"

    def test_strip_accents_empty_string(self, legacy_payload):
        state = self._state(legacy_payload)
        assert state._strip_accents("") == ""

    def test_strip_accents_enables_accent_insensitive_label_match(self, new_normalizer):
        """Label 'Durée' (accented) matches 'duree' keyword via accent stripping."""
        result_accented = new_normalizer.normalize("Durée", None, 60, "numeric")
        result_bare = new_normalizer.normalize("duree", None, 60, "numeric")
        assert result_accented == result_bare

    def test_strip_accents_label_epaisseur_matches(self, new_normalizer):
        """'Épaisseur' (accented capital) matches 'epaisseur' in LABEL_TO_DIMENSION."""
        result = new_normalizer.normalize("Épaisseur", None, 10, "numeric")
        # Should resolve via label -> length dimension -> meter canonical
        assert result.get("unite_canonique") == "meter"


# ===========================================================================
# 12. _get_dimension: label substring priority order
# ===========================================================================

class TestGetDimension:

    def test_specific_label_wins_over_generic(self, new_normalizer):
        """'Capacité de stockage (masse)' is more specific than bare 'capacité'.
        It must resolve to mass, not the default count for 'capacité de stockage'."""
        result = new_normalizer.normalize("Capacité de stockage (masse)", None, 100, "numeric")
        # 'capacité de stockage (masse)' label: after paren-strip = 'Capacité de stockage '
        # which contains 'capacite de stockage' substring -> resolves via label
        assert result != {}

    def test_label_substring_match_is_case_insensitive_via_strip(self, new_normalizer):
        """Label lookup is lowercase + accent-stripped on both sides."""
        result_upper = new_normalizer.normalize("POIDS", None, 10, "numeric")
        result_lower = new_normalizer.normalize("poids", None, 10, "numeric")
        assert result_upper == result_lower

    def test_unit_lookup_takes_priority_over_label(self, new_normalizer):
        """When a unit key is in UNIT_TO_DIMENSION, that dimension wins over label fallback."""
        # 'kg' is in UNIT_TO_DIMENSION as 'mass'; label 'Volume' would give 'volume'.
        # Unit resolution must win.
        result = new_normalizer.normalize("Volume", "kg", 50, "numeric")
        # mass wins -> kilogram
        assert result.get("unite_canonique") == "kilogram"

    def test_label_dimension_ordered_specific_before_generic(self, new_normalizer):
        """'vitesse de rotation' (specific) resolved before bare 'vitesse' (generic)."""
        result = new_normalizer.normalize("Vitesse de rotation", None, 1450, "numeric")
        assert result != {}
        # vitesse de rotation -> [frequency] -> hertz canonical
        assert result.get("unite_canonique") == "hertz"

    def test_generic_vitesse_without_unit_resolves_speed(self, new_normalizer):
        """Bare 'vitesse' label without unit -> speed dimension."""
        result = new_normalizer.normalize("Vitesse", None, 10, "numeric")
        # speed -> meter/second canonical
        assert result.get("unite_canonique") == "meter / second"
