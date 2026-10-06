from dataclasses import replace
from datetime import datetime

import pytest

from infrastructure.unit_state import UnitStateHolder
from unit_registry.bundle import BundleBuildError
from unit_registry.engine import Normalizer
from unit_registry.events import EVENT_CREATED, EVENT_DISABLED, make_event
from unit_registry.seed import build_seed_units
from unit_registry.types import Unit, UnitStatus

NOW = datetime(2026, 10, 6, 12, 0, 0)
SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def poids(holder, unit="sac_ciment"):
    return Normalizer(holder.current).normalize("Poids", unit, "2")


def test_starts_on_the_fallback_tables():
    holder = UnitStateHolder()
    assert holder.source == "fallback" and holder.applied_version == 0
    assert poids(holder, "kg") == {"valeur_canonique": 2.0, "unite_canonique": "kilogram"}


def test_event_on_fallback_requests_resync():
    holder = UnitStateHolder()
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "gap"
    assert poids(holder) == {}


def test_load_then_apply_create_duplicate_gap_and_disable(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    assert holder.source == "db" and holder.applied_version == 1
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "applied"
    assert poids(holder) == {"valeur_canonique": 50.0, "unite_canonique": "kilogram"}
    assert holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW)) == "duplicate"
    assert holder.apply_event(make_event(EVENT_CREATED, 4, SAC, NOW)) == "gap"
    disabled = replace(SAC, status=UnitStatus.DISABLED)
    assert holder.apply_event(make_event(EVENT_DISABLED, 3, disabled, NOW)) == "applied"
    assert poids(holder) == {}


def test_a_build_failure_keeps_the_last_good_bundle(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    before = holder.current()
    clash = Unit(id="x", token="clash", dimension="volume", aliases=("kg",))
    with pytest.raises(BundleBuildError):
        holder.apply_event(make_event(EVENT_CREATED, 2, clash, NOW))
    assert holder.current() is before and holder.applied_version == 1


def test_a_request_keeps_the_bundle_it_started_with(seed):
    holder = UnitStateHolder()
    holder.load_full(seed, 1)
    old = holder.current()
    holder.apply_event(make_event(EVENT_CREATED, 2, SAC, NOW))
    assert Normalizer(lambda: old).normalize("Poids", "sac_ciment", "2") == {}
    assert poids(holder)["valeur_canonique"] == 50.0
