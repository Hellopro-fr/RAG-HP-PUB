"""
Tests du caractère DYNAMIQUE : une unité inconnue échoue, puis devient
normalisable après ajout au référentiel + reload (swap atomique).
Simule ce que produira la boucle learner (Lot 5).
"""

import pytest

from infrastructure.referentiel_loader import Referentiel
from infrastructure.unit_normalization_service import UnitNormalizationService


def _base_payload():
    return {
        "definitions": [
            {"definition": "kg = kilogram", "ordre": 0},
            {"definition": "tonne = 1000 * kilogram = t", "ordre": 1},
        ],
        "unite_dimension": [{"unite": "kg", "dimension": "mass"}],
        "label_dimension": [{"label": "poids", "dimension": "mass", "priorite": 0}],
        "dimension_canonique": [{"dimension": "mass", "unite_canonique": "kilogram"}],
    }


def test_unknown_unit_fails_then_learned_after_reload():
    normalizer = UnitNormalizationService(Referentiel.from_payload(_base_payload()))

    # 'quintal' inconnu au départ → échec (dict vide pour cette clé)
    assert normalizer.normalize("Poids", "quintal", 3, "numeric") == {}

    # Le learner enseigne : define alias + mapping unité→dimension existante
    payload = _base_payload()
    payload["definitions"].append({"definition": "quintal = 100 * kilogram", "ordre": 2})
    payload["unite_dimension"].append({"unite": "quintal", "dimension": "mass"})

    counts = normalizer.reload(Referentiel.from_payload(payload))
    assert counts["define_errors"] == 0

    # Après reload : 3 quintaux = 300 kg
    result = normalizer.normalize("Poids", "quintal", 3, "numeric")
    assert result.get("unite_canonique") == "kilogram"
    assert result.get("valeur_canonique") == 300.0


def test_label_priority_specific_before_generic():
    payload = {
        "definitions": [],
        "unite_dimension": [],
        # 'capacité d'accueil' (count) AVANT 'capacité' (mass) — priorite croissante
        "label_dimension": [
            {"label": "capacité d'accueil", "dimension": "count", "priorite": 0},
            {"label": "capacité", "dimension": "mass", "priorite": 1},
        ],
        "dimension_canonique": [
            {"dimension": "count", "unite_canonique": "count"},
            {"dimension": "mass", "unite_canonique": "kilogram"},
        ],
    }
    normalizer = UnitNormalizationService(Referentiel.from_payload(payload))

    # Le label spécifique doit gagner (count), pas 'capacité' générique (mass)
    res = normalizer.normalize("Capacité d'accueil", None, 50, "numeric")
    assert res.get("unite_canonique") == "count"


def test_validate_rejects_empty_referentiel():
    # Payload BO mal formé (mauvaise enveloppe) -> from_payload ne lève pas mais produit
    # un référentiel vide ; validate() doit le rejeter (sinon panne totale silencieuse).
    ref = Referentiel.from_payload({})
    with pytest.raises(ValueError):
        ref.validate()


def test_validate_accepts_minimal_referentiel():
    Referentiel.from_payload(_base_payload()).validate()  # ne doit pas lever


def test_bad_preprocessing_rule_is_dropped_not_crashing():
    payload = _base_payload()
    payload["preprocessing"] = [
        {"type": "regex_sub", "phase": "pre_snapshot", "pattern": "(unbalanced", "remplacement": "", "ordre": 0},
        {"type": "regex_sub", "phase": "pre_snapshot", "pattern": None, "remplacement": "", "ordre": 1},
        {"type": "nfkc", "phase": "pre_snapshot", "ordre": 2},
    ]
    normalizer = UnitNormalizationService(Referentiel.from_payload(payload))
    counts = normalizer.reload(Referentiel.from_payload(payload))
    # regex invalide + regex_sub sans pattern -> 2 ignorées (le nfkc reste valide)
    assert counts["preprocessing_errors"] == 2
    # Aucune exception au runtime, la normalisation fonctionne toujours
    assert normalizer.normalize("Poids", "kg", 10, "numeric").get("valeur_canonique") == 10.0


def test_bad_define_does_not_break_reload():
    payload = _base_payload()
    payload["definitions"].append({"definition": "definition_sans_egal_invalide", "ordre": 2})  # corrompu (pas de '=')
    normalizer = UnitNormalizationService(Referentiel.from_payload(payload))
    counts = normalizer.reload(Referentiel.from_payload(payload))
    # Le define corrompu est ignoré, le reste fonctionne
    assert counts["define_errors"] >= 1
    assert normalizer.normalize("Poids", "kg", 10, "numeric").get("valeur_canonique") == 10.0
