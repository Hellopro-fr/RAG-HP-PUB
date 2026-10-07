import pytest
from sqlalchemy import func, select

from application.errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from application.types_service import TypeService
from application.unit_service import UnitService
from infrastructure.db.models import UnitEventRow
from unit_registry.types import UnitStatus

from .conftest import NOW


@pytest.fixture
def types(seeded):
    ids = iter(f"t-{n}" for n in range(1000))
    return TypeService(seeded, clock=lambda: NOW, new_id=lambda: next(ids))


@pytest.fixture
def units(seeded):
    return UnitService(seeded, clock=lambda: NOW)


def test_seed_types_exist_without_links(types):
    assert {(t.code, t.dimensions) for t in types.list()} == {("DIMENSION", ()), ("CAPACITY", ())}


def test_create_type(types):
    created = types.create("POIDS", "Poids", "Masse d'un objet", "tester")
    assert created.code == "POIDS" and created.is_active and types.get(code="POIDS").id == created.id


@pytest.mark.parametrize("code", ["capacity", "X", "CAPACITÉ", "1ABC", "A-B"])
def test_create_rejects_bad_codes(types, code):
    with pytest.raises(InvalidArgument):
        types.create(code, "label", None, "tester")


def test_create_rejects_near_duplicates(types):
    with pytest.raises(AlreadyExists, match="CAPACITY"):
        types.create("CAPA_CITY", "Capacité", None, "tester")


def test_create_rejects_an_active_duplicate(types):
    with pytest.raises(AlreadyExists):
        types.create("CAPACITY", "Capacité", None, "tester")


def test_update_label_but_never_code(types):
    capacity = types.get(code="CAPACITY")
    assert types.update(capacity.id, {"label": "Contenance"}, "editor").label == "Contenance"
    with pytest.raises(InvalidArgument, match="immutable"):
        types.update(capacity.id, {"code": "VOLUME"}, "editor")


def test_deactivate_hides_but_keeps_links_and_create_reactivates(types, units):
    types.set_dimension_types("volume", ["CAPACITY"], "editor")
    capacity = types.get(code="CAPACITY")
    types.deactivate(capacity.id, "editor")
    litre = units.get(token="l")
    assert units.types_for([litre])[litre.id] == []
    assert [t.code for t in types.list()] == ["DIMENSION"]
    assert types.get(code="CAPACITY").dimensions == ("volume",)
    revived = types.create("CAPACITY", "Capacité", None, "editor")
    assert revived.is_active and units.types_for([litre])[litre.id] == ["CAPACITY"]


def test_set_dimension_types_replaces_and_is_idempotent(types, units):
    assert types.set_dimension_types("length", ["DIMENSION"], "editor") == ["DIMENSION"]
    assert types.set_dimension_types("length", ["DIMENSION", "DIMENSION"], "editor") == ["DIMENSION"]
    mm = units.get(token="mm")
    assert units.types_for([mm])[mm.id] == ["DIMENSION"]
    found, _ = units.list(status=UnitStatus.ACTIVE, type_code="DIMENSION")
    assert found and all(u.dimension == "length" for u in found)
    assert types.set_dimension_types("length", [], "editor") == []
    assert units.types_for([mm])[mm.id] == []


def test_set_dimension_types_rejects_unknown_and_inactive(types):
    with pytest.raises(NotFound, match="create_unit_type"):
        types.set_dimension_types("length", ["NOPE"], "editor")
    with pytest.raises(InvalidArgument, match="unknown dimension"):
        types.set_dimension_types("weight", ["DIMENSION"], "editor")
    types.deactivate(types.get(code="DIMENSION").id, "editor")
    with pytest.raises(FailedPrecondition):
        types.set_dimension_types("length", ["DIMENSION"], "editor")


def test_type_writes_never_touch_the_registry_version(types, units, seeded):
    types.create("POIDS", "Poids", None, "tester")
    types.set_dimension_types("mass", ["POIDS"], "tester")
    assert units.registry_status()[0] == 1
    with seeded() as s:
        assert s.scalar(select(func.count()).select_from(UnitEventRow)) == 0
