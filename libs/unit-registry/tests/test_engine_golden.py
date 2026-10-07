import json
from pathlib import Path

import pytest

from unit_registry.bundle import legacy_bundle
from unit_registry.engine import Normalizer

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


def run_case(normalizer: Normalizer, case: dict) -> dict:
    if case["kind"] == "q":
        return normalizer.normalize(case["label"], case["unit"], case["value"], case["data_type"])
    return normalizer.normalize_range(case["label"], case["unit"], case["min"], case["max"])


@pytest.fixture(scope="module")
def legacy_normalizer() -> Normalizer:
    bundle = legacy_bundle()
    return Normalizer(lambda: bundle)


def test_moved_engine_reproduces_every_golden_case(legacy_normalizer):
    mismatches = []
    for case in GOLDEN["cases"]:
        got = run_case(legacy_normalizer, case)
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
