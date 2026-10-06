import json
from pathlib import Path

import pytest

from unit_registry.bundle import active_defines, bundle_from_units, explode_lookup_keys
from unit_registry.engine import Normalizer
from unit_registry.legacy import LEGACY_DEFINES, LEGACY_UNIT_TO_DIMENSION
from unit_registry.seed import build_seed_units
from unit_registry.types import UnitSource, UnitStatus

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def test_every_define_becomes_one_row_in_order(seed):
    assert sum(1 for u in seed if u.pint_definition) == len(LEGACY_DEFINES)
    assert active_defines(seed) == list(LEGACY_DEFINES)


def test_row_count_is_defines_plus_unmatched_keys(seed):
    names = {d.split("=", 1)[0].strip() for d in LEGACY_DEFINES}
    unmatched = [k for k in LEGACY_UNIT_TO_DIMENSION if k not in names]
    assert len(seed) == len(LEGACY_DEFINES) + len(unmatched)


def test_exploded_lookup_index_equals_the_legacy_dict(seed):
    assert explode_lookup_keys(seed) == LEGACY_UNIT_TO_DIMENSION


def test_seed_rows_are_active_seed_rows_with_unique_tokens(seed):
    assert all(u.status is UnitStatus.ACTIVE and u.source is UnitSource.SEED for u in seed)
    assert len({u.token for u in seed}) == len(seed)
    assert len({u.id for u in seed}) == len(seed)


def test_seed_is_deterministic(seed):
    assert build_seed_units() == seed


def test_seed_built_bundle_reproduces_every_golden_case(seed):
    bundle = bundle_from_units(seed)
    normalizer = Normalizer(lambda: bundle)
    mismatches = []
    for case in GOLDEN["cases"]:
        if case["kind"] == "q":
            got = normalizer.normalize(case["label"], case["unit"], case["value"], case["data_type"])
        else:
            got = normalizer.normalize_range(case["label"], case["unit"], case["min"], case["max"])
        if got != case["out"]:
            mismatches.append({"case": case, "got": got})
    assert not mismatches, mismatches[:5]
