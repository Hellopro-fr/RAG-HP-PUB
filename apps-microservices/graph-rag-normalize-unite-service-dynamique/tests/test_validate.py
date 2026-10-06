"""Tests de la validation fidèle (Gate 1 du learner) : merged_with + validate_proposed + /admin/validate.
Inclut un test de CONTRAT (symbiose) : toutes les sections émises par le learner sont consommées."""

from types import SimpleNamespace

import infrastructure.rest_api as rest_api_module
from application.normalization_use_case import NormalizationUseCase
from fastapi.testclient import TestClient
from infrastructure.referentiel_loader import Referentiel
from infrastructure.rest_api import create_app
from infrastructure.unit_normalization_service import UnitNormalizationService
from scripts.legacy_referentiel import build_legacy_payload


def _normalizer() -> UnitNormalizationService:
    return UnitNormalizationService(Referentiel.from_payload(build_legacy_payload()))


# Proposition : 'quintal' (inconnu) = 100 kg, dimension mass existante
_PROPOSED_QUINTAL = {
    "unite_dimension": [{"unite": "quintal", "dimension": "mass"}],
    "definitions": [{"definition": "quintal = 100 * kilogram", "ordre": 9000}],
}


def test_merged_with_adds_new_unit():
    base = Referentiel.from_payload(build_legacy_payload())
    merged = base.merged_with(_PROPOSED_QUINTAL)
    assert "quintal" in merged.unit_to_dimension
    assert merged.unit_to_dimension["quintal"] == "mass"
    assert "quintal = 100 * kilogram" in merged.definitions
    assert "quintal" not in base.unit_to_dimension  # base inchangé (immutabilité)


def test_validate_proposed_ok():
    result = _normalizer().validate_proposed(_PROPOSED_QUINTAL, "Poids", "quintal", [3])
    assert result["ok"] is True
    assert result["unite_canonique"] == "kilogram"
    assert result["valeur_canonique"] == 300.0


def test_validate_proposed_no_values_is_nok():
    assert _normalizer().validate_proposed(_PROPOSED_QUINTAL, "Poids", "quintal", [])["ok"] is False


def test_validate_proposed_all_values_must_pass():
    # Plage : si UNE valeur ne se normalise pas, ok=False (ici les deux passent -> ok)
    result = _normalizer().validate_proposed(_PROPOSED_QUINTAL, "Poids", "quintal", [3, 9])
    assert result["ok"] is True


def test_validate_proposed_wrong_dimension_fails():
    bad = {"unite_dimension": [{"unite": "machinchose", "dimension": "power"}]}
    assert _normalizer().validate_proposed(bad, "Bidon", "machinchose", [5])["ok"] is False


def test_validate_proposed_uses_preprocessing_and_rewrites():
    # Réécriture -> prouve que Gate 1 est FIDÈLE au vrai moteur (pipeline complet)
    proposed = {
        "unite_dimension": [{"unite": "knm2", "dimension": "pressure"}],
        "reecriture": [{"unite_source": "knm2", "kind": "rewrite", "value": "kilonewton / meter ** 2"}],
    }
    result = _normalizer().validate_proposed(proposed, "Charge", "knm2", [10])
    assert result["ok"] is True
    assert result["unite_canonique"] == "bar"


def test_symbiose_all_learner_sections_are_consumed():
    """CONTRAT : un payload utilisant TOUTES les sections émises par le learner
    (unite_dimension, definitions, dimension_canonique, reecriture, label_dimension)
    est intégralement consommé par le moteur dynamique -> nouvelle dimension normalisable."""
    proposed = {
        "unite_dimension": [{"unite": "glorb", "dimension": "gloubiness"}],
        "dimension_canonique": [{"dimension": "gloubiness", "unite_canonique": "kilogram"}],
        "definitions": [{"definition": "glorb = 2 * kilogram", "ordre": 9000}],
        "label_dimension": [{"label": "gloubitude", "dimension": "gloubiness", "priorite": 9000}],
        "reecriture": [{"unite_source": "glorb", "kind": "rewrite", "value": "glorb"}],
    }
    result = _normalizer().validate_proposed(proposed, "Gloubitude", "glorb", [4])
    assert result["ok"] is True
    assert result["unite_canonique"] == "kilogram"
    assert result["valeur_canonique"] == 8.0   # 4 glorb * 2 kg


def test_admin_validate_endpoint_value_and_values(monkeypatch):
    monkeypatch.setattr(rest_api_module, "settings",
                        SimpleNamespace(REFERENTIEL_TTL_SECONDS=0, RELOAD_AUTH_TOKEN=""))
    use_case = NormalizationUseCase(_normalizer())

    async def reload_fn():
        return {}

    client = TestClient(create_app(use_case, reload_fn))

    # rétro-compat : 'value' simple
    r1 = client.post("/admin/validate", json={
        "proposed": _PROPOSED_QUINTAL, "label": "Poids", "unit": "quintal", "value": 3})
    assert r1.status_code == 200 and r1.json()["ok"] is True
    assert r1.json()["valeur_canonique"] == 300.0

    # liste de valeurs (min + max)
    r2 = client.post("/admin/validate", json={
        "proposed": _PROPOSED_QUINTAL, "label": "Poids", "unit": "quintal", "values": [3, 9]})
    assert r2.status_code == 200 and r2.json()["ok"] is True
