"""Capture the CURRENT normalizer's behaviour as the parity oracle (golden.json).

Run ONCE, in plan Task 1, before the engine moves into libs/unit-registry:
    docker exec -w /repo unit-registry-test python libs/unit-registry/tests/golden/make_golden.py

It imports the normalizer service module directly, records every string passed to
UnitRegistry.define while the singleton is built (pint's own __init__ never calls
define, verified on 0.24.4), then replays a corpus of inputs through the engine.
"""
import json
import sys
from pathlib import Path

import pint

REPO = Path(__file__).resolve().parents[4]
SERVICE = REPO / "apps-microservices" / "graph-rag-normalize-unite-service"
OUT = Path(__file__).with_name("golden.json")

recorded: list[str] = []
_original_define = pint.UnitRegistry.define


def _recording_define(self, definition, *args, **kwargs):
    if isinstance(definition, str):
        recorded.append(definition)
    return _original_define(self, definition, *args, **kwargs)


pint.UnitRegistry.define = _recording_define
sys.path.insert(0, str(SERVICE))
from infrastructure.unit_normalization_service import unit_normalizer as legacy  # noqa: E402

pint.UnitRegistry.define = _original_define

LABEL = "Caractéristique technique"

# (label, unit, value[, data_type]) — every special path of normalize().
SPECIAL_QUANTITIES = [
    ("Longueur d'onde", "nm", "532"),
    ("Couple de serrage", "nm", "40"),
    ("Débit", "t/min", "2"),
    ("Régime moteur", "t/min", "1500"),
    ("Niveau sonore", "dB(A)", "65"),
    ("Niveau sonore", "Décibels (dB)", "70"),
    ("Débit d'air", "m³/h", "120"),
    ("Débit d'air", "m3/h", "120"),
    ("Surface", "m²", "3"),
    ("Surface", "m2", "3"),
    ("Densité", "kg/m³", "800"),
    ("Poids", "kg", "+/- 2"),
    ("Poids", "kg", "± 3.5"),
    ("Poids", "kg", "+5"),
    ("Poids", "kg", "abc"),
    ("Poids", "kg", "2", "text"),
    ("Poids", None, "2"),
    ("", "kg", "2"),
    ("Facteur G", "G", "3000"),
    ("Champ magnétique", "G", "3"),
    ("Humidité", "%", "45"),
    ("IRC", "Ra", "80"),
    ("Dureté", "Mohs", "7"),
    ("Epaisseur", "µm", "25"),
    ("Epaisseur", "μm", "25"),
    ("Couple", "N·m", "12"),
    ("Viscosité", "mPa·s", "300"),
    ("Puissance", "KW", "3"),
    ("Puissance", "Watts", "1500"),
    ("Volume", "Litres", "20"),
    ("Poids", "Tonnes", "2"),
    ("Hauteur", "Pieds", "3"),
    ("Vitesse de rotation", "tr/min", "1400"),
    ("Capacité de production", "kg/24h", "500"),
    ("Consommation", "kWh/24h", "1.2"),
    ("Capacité de la batterie", "mAh", "5000"),
    ("Autonomie de la batterie", "heures", "8"),
    ("Mémoire", "Go", "16"),
    ("Charge", "décibels", "3"),
    ("Inconnu", "zzz", "1"),
]

SPECIAL_RANGES = [
    ("Température d'utilisation", "°C", -10.0, 40.0),
    ("Longueur", "cm", 10.0, 50.0),
    ("Poids", "kg", None, 5.0),
    ("Poids", "kg", 1.0, None),
    ("Inconnu", "zzz", 1.0, 2.0),
]


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def q(label, unit, value, data_type="numeric"):
        cases.append(
            {"kind": "q", "label": label, "unit": unit, "value": value, "data_type": data_type}
        )

    for definition in recorded:
        q(LABEL, definition.split("=", 1)[0].strip(), "2.5")
    for key in legacy.UNIT_TO_DIMENSION:
        q(LABEL, key, "2.5")
    for keyword in legacy.LABEL_TO_DIMENSION:
        q(keyword, None, "2.5")
    for args in SPECIAL_QUANTITIES:
        q(*args)
    for label, unit, low, high in SPECIAL_RANGES:
        cases.append({"kind": "r", "label": label, "unit": unit, "min": low, "max": high})
    return cases


def run(case: dict) -> dict:
    if case["kind"] == "q":
        return legacy.normalize(case["label"], case["unit"], case["value"], case["data_type"])
    return legacy.normalize_range(case["label"], case["unit"], case["min"], case["max"])


def main() -> None:
    cases = build_cases()
    for case in cases:
        case["out"] = run(case)
    golden = {
        "pint_version": pint.__version__,
        "defines": recorded,
        "unit_to_dimension": legacy.UNIT_TO_DIMENSION,
        "label_to_dimension": list(legacy.LABEL_TO_DIMENSION.items()),
        "canonical_units": legacy.CANONICAL_UNITS,
        "cases": cases,
    }
    OUT.write_text(json.dumps(golden, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(recorded)} defines, {len(cases)} cases")


if __name__ == "__main__":
    main()
