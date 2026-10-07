"""The service (use case + wired engine on fallback tables) still matches the pre-move golden output."""
import json
from pathlib import Path

from application.normalization_use_case import NormalizationUseCase

GOLDEN = Path(__file__).resolve().parents[3] / "libs" / "unit-registry" / "tests" / "golden" / "golden.json"


def test_use_case_reproduces_golden_cases():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    use_case = NormalizationUseCase()
    mismatches = []
    for case in golden["cases"]:
        if case["kind"] == "q":
            got = use_case.normalize_quantity(case["label"], case["unit"], case["value"], case["data_type"])
        else:
            got = use_case.normalize_range(case["label"], case["unit"], case["min"], case["max"])
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
