from sqlalchemy import func, select

from infrastructure.db.bootstrap import bootstrap
from infrastructure.db.models import UnitDimensionRow, UnitEventRow, UnitRow, UnitTypeRow
from infrastructure.db.repository import TypeRepository, UnitRepository
from unit_registry.legacy import CANONICAL_UNITS
from unit_registry.seed import build_seed_units
from unit_registry.types import UnitStatus

from .conftest import NOW


def count(session, row):
    return session.scalar(select(func.count()).select_from(row))


def test_bootstrap_seeds_dimensions_units_types_and_version(seeded):
    with seeded() as s:
        assert count(s, UnitDimensionRow) == len(CANONICAL_UNITS)
        assert count(s, UnitRow) == len(build_seed_units())
        assert {t.code for t in TypeRepository(s).list_types()} == {"DIMENSION", "CAPACITY"}
        assert UnitRepository(s).current_version() == 1
        assert count(s, UnitEventRow) == 0


def test_bootstrap_is_idempotent(seeded):
    with seeded.begin() as s:
        bootstrap(s, NOW)
    with seeded() as s:
        assert count(s, UnitRow) == len(build_seed_units())
        assert count(s, UnitTypeRow) == 2


def test_units_round_trip_through_the_database(seeded):
    expected = {(u.token, u.pint_definition, u.dimension, u.sort_order) for u in build_seed_units()}
    with seeded() as s:
        got = {(u.token, u.pint_definition, u.dimension, u.sort_order)
               for u in UnitRepository(s).list_units(status=UnitStatus.ACTIVE)}
    assert got == expected


def test_token_lookup_is_exact(seeded):
    with seeded() as s:
        repo = UnitRepository(s)
        assert repo.get_unit_by_token("Litres").token == "Litres"
        assert repo.get_unit_by_token("litres").token == "litres"
        assert repo.get_unit_by_token("LITRES") is None


def test_bump_version_increments(seeded):
    with seeded.begin() as s:
        assert UnitRepository(s).bump_version("tester", NOW) == 2
    with seeded() as s:
        assert UnitRepository(s).current_version() == 2


def test_dimension_filter(seeded):
    with seeded() as s:
        units = UnitRepository(s).list_units(dimensions={"length"})
    assert units and all(u.dimension == "length" for u in units)
