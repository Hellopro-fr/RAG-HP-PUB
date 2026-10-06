"""
Tests unitaires pour infrastructure/referentiel_loader.py.

Couvre :
  - Referentiel.from_payload : parsing de chaque section, tri défensif sur ordre/priorite
  - Referentiel.from_payload : robustesse (sections absentes, lignes vides/invalides)
  - Referentiel.validate() : rejette les structures cœur vides, accepte un référentiel minimal
  - fetch_referentiel_from_bo() : simulation via monkeypatch httpx, payload malformé lève ValueError
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.referentiel_loader import (
    PreprocessingRule,
    Referentiel,
    RewriteRule,
    fetch_referentiel_from_bo,
)
from scripts.legacy_referentiel import build_legacy_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_payload() -> Dict[str, Any]:
    """Payload valide minimal (passe validate() sans lever)."""
    return {
        "definitions": [{"definition": "kg = kilogram", "ordre": 0}],
        "unite_dimension": [{"unite": "kg", "dimension": "mass"}],
        "label_dimension": [{"label": "poids", "dimension": "mass", "priorite": 0}],
        "dimension_canonique": [{"dimension": "mass", "unite_canonique": "kilogram"}],
        "preprocessing": [],
        "reecriture": [],
    }


# ===========================================================================
# from_payload — parsing correct de chaque section
# ===========================================================================


class TestFromPayloadDefinitions:
    def test_definitions_sorted_by_ordre(self):
        payload = {
            "definitions": [
                {"definition": "tonne = 1000 * kilogram = t", "ordre": 2},
                {"definition": "kg = kilogram", "ordre": 0},
                {"definition": "mm = millimeter", "ordre": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.definitions == [
            "kg = kilogram",
            "mm = millimeter",
            "tonne = 1000 * kilogram = t",
        ]

    def test_definitions_strips_whitespace(self):
        payload = {
            "definitions": [
                {"definition": "  kg = kilogram  ", "ordre": 0},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.definitions == ["kg = kilogram"]

    def test_definitions_blank_entries_dropped(self):
        payload = {
            "definitions": [
                {"definition": "", "ordre": 0},
                {"definition": "   ", "ordre": 1},
                {"definition": "kg = kilogram", "ordre": 2},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.definitions == ["kg = kilogram"]

    def test_definitions_ordre_zero_treated_as_int(self):
        # ordre absent defaults to 0 — should not raise
        payload = {
            "definitions": [
                {"definition": "kg = kilogram"},
                {"definition": "mm = millimeter", "ordre": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert len(ref.definitions) == 2


class TestFromPayloadUniteDimension:
    def test_unite_dimension_lowercased_keys(self):
        payload = {
            "unite_dimension": [
                {"unite": "KG", "dimension": "mass"},
                {"unite": "Mm", "dimension": "length"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "kg" in ref.unit_to_dimension
        assert "mm" in ref.unit_to_dimension
        assert "KG" not in ref.unit_to_dimension

    def test_unite_dimension_values_preserved(self):
        payload = {
            "unite_dimension": [
                {"unite": "kg", "dimension": "mass"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.unit_to_dimension["kg"] == "mass"

    def test_unite_dimension_blank_unite_skipped(self):
        payload = {
            "unite_dimension": [
                {"unite": "", "dimension": "mass"},
                {"unite": "  ", "dimension": "length"},
                {"unite": "kg", "dimension": "mass"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert len(ref.unit_to_dimension) == 1
        assert "kg" in ref.unit_to_dimension

    def test_unite_dimension_blank_dimension_skipped(self):
        payload = {
            "unite_dimension": [
                {"unite": "kg", "dimension": ""},
                {"unite": "mm", "dimension": "length"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "kg" not in ref.unit_to_dimension
        assert "mm" in ref.unit_to_dimension


class TestFromPayloadLabelDimension:
    def test_label_dimension_sorted_by_priorite(self):
        payload = {
            "label_dimension": [
                {"label": "Capacite", "dimension": "mass", "priorite": 2},
                {"label": "Capacite d accueil", "dimension": "count", "priorite": 0},
                {"label": "Poids", "dimension": "mass", "priorite": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        labels_in_order = [label for label, _ in ref.label_to_dimension]
        assert labels_in_order == [
            "capacite d accueil",
            "poids",
            "capacite",
        ]

    def test_label_dimension_is_list_of_tuples(self):
        payload = {
            "label_dimension": [
                {"label": "poids", "dimension": "mass", "priorite": 0},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert isinstance(ref.label_to_dimension, list)
        assert isinstance(ref.label_to_dimension[0], tuple)
        assert ref.label_to_dimension[0] == ("poids", "mass")

    def test_label_dimension_lowercased_labels(self):
        payload = {
            "label_dimension": [
                {"label": "Poids", "dimension": "mass", "priorite": 0},
                {"label": "HAUTEUR", "dimension": "length", "priorite": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        labels = [label for label, _ in ref.label_to_dimension]
        assert "poids" in labels
        assert "hauteur" in labels

    def test_label_dimension_order_out_of_order_input(self):
        """Rows given in reverse priorite order must come out sorted ascending."""
        payload = {
            "label_dimension": [
                {"label": "generic", "dimension": "mass", "priorite": 99},
                {"label": "specific", "dimension": "count", "priorite": 1},
                {"label": "more specific", "dimension": "length", "priorite": 0},
            ]
        }
        ref = Referentiel.from_payload(payload)
        labels = [label for label, _ in ref.label_to_dimension]
        assert labels == ["more specific", "specific", "generic"]

    def test_label_dimension_blank_label_skipped(self):
        payload = {
            "label_dimension": [
                {"label": "", "dimension": "mass", "priorite": 0},
                {"label": "poids", "dimension": "mass", "priorite": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert len(ref.label_to_dimension) == 1


class TestFromPayloadDimensionCanonique:
    def test_canonical_units_parsed(self):
        payload = {
            "dimension_canonique": [
                {"dimension": "mass", "unite_canonique": "kilogram"},
                {"dimension": "length", "unite_canonique": "meter"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.canonical_units == {"mass": "kilogram", "length": "meter"}

    def test_canonical_units_blank_dimension_skipped(self):
        payload = {
            "dimension_canonique": [
                {"dimension": "", "unite_canonique": "kilogram"},
                {"dimension": "mass", "unite_canonique": "kilogram"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "" not in ref.canonical_units
        assert "mass" in ref.canonical_units

    def test_canonical_units_blank_unite_canonique_skipped(self):
        payload = {
            "dimension_canonique": [
                {"dimension": "mass", "unite_canonique": ""},
                {"dimension": "length", "unite_canonique": "meter"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "mass" not in ref.canonical_units
        assert "length" in ref.canonical_units


class TestFromPayloadPreprocessing:
    def test_preprocessing_parsed_into_PreprocessingRule(self):
        payload = {
            "preprocessing": [
                {
                    "type": "nfkc",
                    "phase": "pre_snapshot",
                    "pattern": None,
                    "remplacement": "",
                    "ordre": 0,
                },
                {
                    "type": "regex_sub",
                    "phase": "pre_snapshot",
                    "pattern": r"\s*\([^)]*\)\s*$",
                    "remplacement": "",
                    "ordre": 1,
                },
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert len(ref.preprocessing) == 2
        rule0 = ref.preprocessing[0]
        assert isinstance(rule0, PreprocessingRule)
        assert rule0.type == "nfkc"
        assert rule0.phase == "pre_snapshot"

    def test_preprocessing_phase_preserved(self):
        payload = {
            "preprocessing": [
                {
                    "type": "str_replace",
                    "phase": "post_snapshot",
                    "pattern": "³",
                    "remplacement": "3",
                    "ordre": 0,
                },
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.preprocessing[0].phase == "post_snapshot"

    def test_preprocessing_pattern_and_remplacement_preserved(self):
        payload = {
            "preprocessing": [
                {
                    "type": "str_replace",
                    "phase": "pre_snapshot",
                    "pattern": "·",
                    "remplacement": ".",
                    "ordre": 0,
                },
            ]
        }
        ref = Referentiel.from_payload(payload)
        rule = ref.preprocessing[0]
        assert rule.pattern == "·"
        assert rule.remplacement == "."

    def test_preprocessing_sorted_by_ordre_out_of_order_input(self):
        """Rows given in reverse ordre must come out sorted ascending."""
        payload = {
            "preprocessing": [
                {"type": "str_replace", "phase": "post_snapshot", "pattern": "²", "remplacement": "2", "ordre": 4},
                {"type": "str_replace", "phase": "post_snapshot", "pattern": "³", "remplacement": "3", "ordre": 3},
                {"type": "str_replace", "phase": "pre_snapshot",  "pattern": "·",  "remplacement": ".", "ordre": 2},
                {"type": "regex_sub",   "phase": "pre_snapshot",  "pattern": r"\([^)]*\)", "remplacement": "", "ordre": 1},
                {"type": "nfkc",        "phase": "pre_snapshot",  "pattern": None, "remplacement": "", "ordre": 0},
            ]
        }
        ref = Referentiel.from_payload(payload)
        types_in_order = [r.type for r in ref.preprocessing]
        assert types_in_order == ["nfkc", "regex_sub", "str_replace", "str_replace", "str_replace"]

    def test_preprocessing_rule_without_type_dropped(self):
        payload = {
            "preprocessing": [
                {"phase": "pre_snapshot", "pattern": None, "remplacement": "", "ordre": 0},
                {"type": "nfkc", "phase": "pre_snapshot", "ordre": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        # only the rule with a type survives
        assert len(ref.preprocessing) == 1
        assert ref.preprocessing[0].type == "nfkc"


class TestFromPayloadReecriture:
    def test_rewrite_parsed_into_RewriteRule(self):
        payload = {
            "reecriture": [
                {"unite_source": "Tonnes", "kind": "rewrite", "value": "tonne"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "tonnes" in ref.rewrites
        rule = ref.rewrites["tonnes"]
        assert isinstance(rule, RewriteRule)
        assert rule.kind == "rewrite"
        assert rule.value == "tonne"

    def test_rewrite_key_lowercased(self):
        payload = {
            "reecriture": [
                {"unite_source": "DB(A)", "kind": "rewrite", "value": "dBA"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "db(a)" in ref.rewrites
        assert "DB(A)" not in ref.rewrites

    def test_rewrite_bypass_kind_preserved(self):
        payload = {
            "reecriture": [
                {"unite_source": "%", "kind": "bypass", "value": "count"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert ref.rewrites["%"].kind == "bypass"
        assert ref.rewrites["%"].value == "count"

    def test_rewrite_empty_value_dropped(self):
        """Rows with empty value must be silently discarded."""
        payload = {
            "reecriture": [
                {"unite_source": "tonnes", "kind": "rewrite", "value": ""},
                {"unite_source": "pieds",  "kind": "rewrite", "value": "pieds"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "tonnes" not in ref.rewrites
        assert "pieds" in ref.rewrites

    def test_rewrite_empty_source_dropped(self):
        payload = {
            "reecriture": [
                {"unite_source": "", "kind": "rewrite", "value": "tonne"},
                {"unite_source": "pieds", "kind": "rewrite", "value": "pieds"},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert "" not in ref.rewrites
        assert len(ref.rewrites) == 1


# ===========================================================================
# from_payload — robustesse : sections absentes
# ===========================================================================


class TestFromPayloadRobustness:
    def test_empty_payload_produces_empty_referentiel_no_exception(self):
        ref = Referentiel.from_payload({})
        assert ref.definitions == []
        assert ref.unit_to_dimension == {}
        assert ref.label_to_dimension == []
        assert ref.canonical_units == {}
        assert ref.preprocessing == []
        assert ref.rewrites == {}

    def test_missing_definitions_section(self):
        payload = _minimal_payload()
        del payload["definitions"]
        ref = Referentiel.from_payload(payload)
        assert ref.definitions == []

    def test_missing_unite_dimension_section(self):
        payload = _minimal_payload()
        del payload["unite_dimension"]
        ref = Referentiel.from_payload(payload)
        assert ref.unit_to_dimension == {}

    def test_missing_label_dimension_section(self):
        payload = _minimal_payload()
        del payload["label_dimension"]
        ref = Referentiel.from_payload(payload)
        assert ref.label_to_dimension == []

    def test_missing_dimension_canonique_section(self):
        payload = _minimal_payload()
        del payload["dimension_canonique"]
        ref = Referentiel.from_payload(payload)
        assert ref.canonical_units == {}

    def test_missing_preprocessing_section(self):
        payload = _minimal_payload()
        del payload["preprocessing"]
        ref = Referentiel.from_payload(payload)
        assert ref.preprocessing == []

    def test_missing_reecriture_section(self):
        payload = _minimal_payload()
        del payload["reecriture"]
        ref = Referentiel.from_payload(payload)
        assert ref.rewrites == {}

    def test_none_ordre_treated_as_zero(self):
        """ordre=None must not crash (cast to 0 via `int(r.get('ordre', 0) or 0)`)."""
        payload = {
            "definitions": [
                {"definition": "kg = kilogram", "ordre": None},
                {"definition": "mm = millimeter", "ordre": 1},
            ]
        }
        ref = Referentiel.from_payload(payload)
        assert len(ref.definitions) == 2


# ===========================================================================
# validate()
# ===========================================================================


class TestValidate:
    def test_validate_raises_when_unit_to_dimension_empty(self):
        payload = _minimal_payload()
        payload["unite_dimension"] = []
        ref = Referentiel.from_payload(payload)
        with pytest.raises(ValueError, match="unit_to_dimension"):
            ref.validate()

    def test_validate_raises_when_label_to_dimension_empty(self):
        payload = _minimal_payload()
        payload["label_dimension"] = []
        ref = Referentiel.from_payload(payload)
        with pytest.raises(ValueError, match="label_to_dimension"):
            ref.validate()

    def test_validate_raises_when_canonical_units_empty(self):
        payload = _minimal_payload()
        payload["dimension_canonique"] = []
        ref = Referentiel.from_payload(payload)
        with pytest.raises(ValueError, match="canonical_units"):
            ref.validate()

    def test_validate_raises_when_all_three_empty(self):
        ref = Referentiel.from_payload({})
        with pytest.raises(ValueError) as exc_info:
            ref.validate()
        message = str(exc_info.value)
        assert "unit_to_dimension" in message
        assert "label_to_dimension" in message
        assert "canonical_units" in message

    def test_validate_does_not_raise_on_complete_minimal_payload(self):
        ref = Referentiel.from_payload(_minimal_payload())
        ref.validate()  # must not raise

    def test_validate_does_not_raise_on_legacy_payload(self):
        ref = Referentiel.from_payload(build_legacy_payload())
        ref.validate()  # must not raise


# ===========================================================================
# fetch_referentiel_from_bo() — simulation httpx via monkeypatch
# ===========================================================================


class TestFetchReferentielFromBo:
    def _run(self, coro):
        # asyncio.run : crée/ferme une boucle dédiée (get_event_loop() est cassé sans
        # boucle courante sur Python 3.12+).
        return asyncio.run(coro)

    def _make_mock_response(self, payload: Dict[str, Any]):
        """Returns a mock httpx.Response whose .json() gives payload and raise_for_status() is a no-op."""
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status = MagicMock()
        return response

    def _patch_httpx_post(self, monkeypatch, payload: Dict[str, Any]):
        """Patches httpx.AsyncClient so that POST returns a mock with the given payload."""
        response = self._make_mock_response(payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=response)

        monkeypatch.setattr(
            "infrastructure.referentiel_loader.httpx.AsyncClient",
            MagicMock(return_value=mock_client),
        )

    def test_fetch_returns_referentiel_matching_legacy_payload_counts(self, monkeypatch):
        legacy_payload = build_legacy_payload()
        self._patch_httpx_post(monkeypatch, legacy_payload)

        referentiel = self._run(fetch_referentiel_from_bo())

        expected = Referentiel.from_payload(legacy_payload).counts()
        assert referentiel.counts() == expected

    def test_fetch_returned_referentiel_passes_validate(self, monkeypatch):
        self._patch_httpx_post(monkeypatch, build_legacy_payload())

        referentiel = self._run(fetch_referentiel_from_bo())

        referentiel.validate()  # must not raise

    def test_fetch_malformed_payload_raises_ValueError(self, monkeypatch):
        """A payload with the wrong shape produces empty core structures → validate() raises."""
        self._patch_httpx_post(monkeypatch, {"wrong": "shape"})

        with pytest.raises(ValueError):
            self._run(fetch_referentiel_from_bo())

    def test_fetch_empty_payload_raises_ValueError(self, monkeypatch):
        self._patch_httpx_post(monkeypatch, {})

        with pytest.raises(ValueError):
            self._run(fetch_referentiel_from_bo())

    def test_fetch_calls_post_with_correct_body(self, monkeypatch):
        """The function must POST the expected BO v2 webhook body."""
        legacy_payload = build_legacy_payload()
        response = self._make_mock_response(legacy_payload)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=response)

        monkeypatch.setattr(
            "infrastructure.referentiel_loader.httpx.AsyncClient",
            MagicMock(return_value=mock_client),
        )

        self._run(fetch_referentiel_from_bo())

        called_kwargs = mock_client.post.call_args
        # second positional arg or json kwarg must contain the expected body
        body = called_kwargs.kwargs.get("json") or called_kwargs.args[1]
        assert body == {"etape": "normalisation", "field": "referentiel", "action": "get", "data": {}}
