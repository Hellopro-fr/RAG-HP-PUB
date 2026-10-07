import json
from pathlib import Path

from unit_registry.legacy import (
    CANONICAL_UNITS,
    LABEL_TO_DIMENSION,
    LEGACY_DEFINES,
    LEGACY_UNIT_TO_DIMENSION,
)

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


def test_defines_match_the_recorded_order():
    assert list(LEGACY_DEFINES) == GOLDEN["defines"]


def test_unit_to_dimension_matches():
    assert LEGACY_UNIT_TO_DIMENSION == GOLDEN["unit_to_dimension"]


def test_label_rules_match_in_order():
    assert [list(p) for p in LABEL_TO_DIMENSION.items()] == GOLDEN["label_to_dimension"]


def test_canonical_units_match():
    assert CANONICAL_UNITS == GOLDEN["canonical_units"]
