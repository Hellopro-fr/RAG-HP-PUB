"""
Test de parité : le moteur DYNAMIQUE alimenté avec les données du service
HISTORIQUE doit produire des sorties canoniques STRICTEMENT identiques.

C'est le filet de sécurité go/no-go du cutover (Lot 3 du plan).
"""

from infrastructure.referentiel_loader import Referentiel
from infrastructure.unit_normalization_service import (
    _STATIC_DISAMBIGUATIONS,
    UnitNormalizationService,
)
from scripts.legacy_referentiel import (
    REWRITE_RULES,
    build_legacy_payload,
    load_legacy_normalizer,
)


def _build_new_normalizer() -> UnitNormalizationService:
    referentiel = Referentiel.from_payload(build_legacy_payload())
    return UnitNormalizationService(referentiel)


# Cas réels représentatifs (au-delà du balayage exhaustif des clés)
_EXTRA_CASES = [
    ("Poids", "kg", 1500),
    ("Hauteur", "mm", 2500),
    ("Puissance", "CV", 3),
    ("Puissance", "KW", 7.5),
    ("Capacité", "Tonnes", 2),
    ("Niveau sonore", "dB(A)", 72),
    ("Vitesse de rotation", "tr/min", 1450),
    ("Débit", "m3/h", 12),
    ("Surface", "m²", 18),
    ("Épaisseur", "nm", 250),                  # désambiguïsation nm → length via label
    ("Capacité de production", "t/min", 5),    # désambiguïsation t/min → mass_flow via label
    ("Humidité", "%", 60),
    ("Dureté", "Mohs", 7),
    ("Volume cuve", "litres", 200),
    ("Température", "°C", 21),
    ("Tolérance", "mm", "+/- 2"),              # préfixe tolérance ±
]


def _corpus():
    old = load_legacy_normalizer()
    cases = []
    # Balayage : chaque clé d'unité (label vide)
    for unite in old.UNIT_TO_DIMENSION:
        cases.append(("", unite, 100.0))
    # Balayage : chaque mot-clé de label (unité absente)
    for label in old.LABEL_TO_DIMENSION:
        cases.append((label, None, 100.0))
    # Balayage : chaque clé de réécriture/bypass (exercice direct des branches elif)
    for rule in REWRITE_RULES:
        cases.append(("", rule["unite_source"], 100.0))
        cases.append(("Mesure", rule["unite_source"], 100.0))
    # Balayage : désambiguïsations (statiques en code), AVEC et SANS indicateur de label
    for rule in _STATIC_DISAMBIGUATIONS:
        unite = rule.unite_source
        cases.append(("", unite, 100.0))                              # sans label
        cases.append(("Caractéristique générique", unite, 100.0))    # label neutre
        for ind in rule.indicateurs:
            cases.append((f"{ind} machin", unite, 100.0))             # label avec indicateur
    cases.extend(_EXTRA_CASES)
    return cases


def test_parity_quantity():
    old = load_legacy_normalizer()
    new = _build_new_normalizer()

    divergences = []
    for label, unite, valeur in _corpus():
        o = old.normalize(label, unite, valeur, "numeric")
        n = new.normalize(label, unite, valeur, "numeric")
        if o != n:
            divergences.append((label, unite, valeur, o, n))

    assert not divergences, f"{len(divergences)} divergence(s): {divergences[:10]}"


def test_parity_range():
    old = load_legacy_normalizer()
    new = _build_new_normalizer()

    range_cases = [
        ("Hauteur", "mm", 100, 2500),
        ("Poids", "kg", 50, 1500),
        ("Puissance", "CV", 2, 8),
        ("Température", "°C", -10, 40),
    ]
    for label, unite, vmin, vmax in range_cases:
        assert old.normalize_range(label, unite, vmin, vmax) == new.normalize_range(
            label, unite, vmin, vmax
        ), (label, unite, vmin, vmax)
