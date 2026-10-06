"""Production path parity: SQLite bootstrap -> ListUnits(ACTIVE) -> proto round trip -> bundle -> golden."""
import json
from pathlib import Path

from application.unit_service import UnitService
from unit_registry.bundle import bundle_from_units
from unit_registry.engine import Normalizer
from unit_registry.proto_codec import unit_from_proto, unit_to_proto
from unit_registry.types import UnitStatus

GOLDEN_PATH = Path(__file__).resolve().parents[3] / "libs" / "unit-registry" / "tests" / "golden" / "golden.json"


def run_case(normalizer: Normalizer, case: dict) -> dict:
    if case["kind"] == "q":
        return normalizer.normalize(case["label"], case["unit"], case["value"], case["data_type"])
    return normalizer.normalize_range(case["label"], case["unit"], case["min"], case["max"])


def test_bootstrapped_registry_replays_the_golden_cases(seeded):
    units, _ = UnitService(seeded).list(status=UnitStatus.ACTIVE)
    assert len(units) == 233
    round_tripped = [unit_from_proto(unit_to_proto(u)) for u in units]
    bundle = bundle_from_units(round_tripped)
    normalizer = Normalizer(lambda: bundle)
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    mismatches = [{"case": c, "got": got} for c in golden["cases"]
                  if (got := run_case(normalizer, c)) != c["out"]]
    assert not mismatches, mismatches[:5]
