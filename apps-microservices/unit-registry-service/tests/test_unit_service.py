import pytest
from sqlalchemy import select

from application.errors import AlreadyExists, FailedPrecondition, InvalidArgument, NotFound
from application.unit_service import UnitDraft, UnitService
from infrastructure.db.models import UnitEventRow
from unit_registry.types import RegressionSample, UnitStatus

from .conftest import NOW


def sample(expected=50.0, value="2"):
    return RegressionSample(label="Poids", value=value, expected_canonical_value=expected,
                            expected_canonical_unit="kilogram")


def draft(**overrides) -> UnitDraft:
    base = dict(token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
                regression_sample=sample())
    base.update(overrides)
    return UnitDraft(**base)


@pytest.fixture
def service(seeded):
    ids = iter(f"id-{n}" for n in range(1000))
    return UnitService(seeded, clock=lambda: NOW, new_id=lambda: next(ids))


def events(seeded):
    with seeded() as s:
        return [(r.registry_version, r.payload["event"], r.payload["unit"]["token"])
                for r in s.execute(select(UnitEventRow).order_by(UnitEventRow.registry_version)).scalars()]


def test_register_commits_row_version_and_outbox_event(service, seeded):
    unit, version = service.register(draft(), "tester")
    assert version == 2 and unit.status is UnitStatus.ACTIVE and unit.created_by == "tester"
    assert events(seeded) == [(2, "unit.created", "sac_ciment")]
    assert service.get(token="sac_ciment").id == unit.id


def test_register_without_sample_is_invalid(service):
    with pytest.raises(InvalidArgument, match="G4"):
        service.register(draft(regression_sample=None), "tester")


def test_register_without_dimension_is_invalid(service):
    with pytest.raises(InvalidArgument, match="dimension"):
        service.register(draft(dimension=None), "tester")


def test_register_an_existing_token_already_exists(service):
    with pytest.raises(AlreadyExists, match="kg"):
        service.register(draft(token="kg", pint_definition=None), "tester")


def test_register_lazy_bad_define_fails_g1(service, seeded):
    with pytest.raises(InvalidArgument, match="G1"):
        service.register(draft(token="baz_x", pint_definition="baz_x = 3 * nonexistent_y"), "tester")
    assert events(seeded) == []


def test_register_alias_clash_already_exists(service):
    with pytest.raises(AlreadyExists, match="G6"):
        service.register(draft(aliases=("kg",)), "tester")


def test_update_revalidates_and_emits_an_event(service, seeded):
    unit, _ = service.register(draft(), "tester")
    updated, version = service.update(
        unit.id, {"pint_definition": "sac_ciment = 20 * kilogram", "regression_sample": sample(40.0)}, "editor")
    assert version == 3 and updated.pint_definition == "sac_ciment = 20 * kilogram"
    assert events(seeded)[-1] == (3, "unit.updated", "sac_ciment")


def test_update_of_a_seed_unit_needs_a_sample(service):
    kg = service.get(token="kg")
    with pytest.raises(InvalidArgument, match="G4"):
        service.update(kg.id, {"aliases": ("kilo",)}, "editor")


def test_update_rejects_unknown_fields(service):
    kg = service.get(token="kg")
    with pytest.raises(InvalidArgument, match="token"):
        service.update(kg.id, {"token": "kgs"}, "editor")


def test_update_unknown_unit_is_not_found(service):
    with pytest.raises(NotFound):
        service.update("missing", {"aliases": ()}, "editor")


def test_disable_is_idempotent(service, seeded):
    unit, _ = service.register(draft(), "tester")
    disabled, version = service.disable(unit.id, "editor")
    assert disabled.status is UnitStatus.DISABLED and version == 3
    again, version_again = service.disable(unit.id, "editor")
    assert again.status is UnitStatus.DISABLED and version_again == 3
    assert [e[1] for e in events(seeded)] == ["unit.created", "unit.disabled"]


def test_disable_refuses_when_other_units_depend_on_it(service):
    cheval_vapeur = service.get(token="cheval_vapeur")
    with pytest.raises(FailedPrecondition, match="CV"):
        service.disable(cheval_vapeur.id, "editor")


def test_register_reactivates_a_disabled_token(service, seeded):
    unit, _ = service.register(draft(), "tester")
    service.disable(unit.id, "editor")
    revived, version = service.register(draft(), "tester")
    assert revived.id == unit.id and revived.status is UnitStatus.ACTIVE and version == 4
    assert events(seeded)[-1] == (4, "unit.created", "sac_ciment")


def test_validate_is_read_only(service, seeded):
    outcome = service.validate(draft())
    assert outcome.ok
    assert service.registry_status()[0] == 1 and events(seeded) == []


def test_list_filters_and_reports_the_version(service):
    units, version = service.list(status=UnitStatus.ACTIVE, dimension="length")
    assert version == 1 and units and all(u.dimension == "length" for u in units)


def test_get_requires_id_or_token(service):
    with pytest.raises(InvalidArgument):
        service.get()
    with pytest.raises(NotFound):
        service.get(token="nope")


def test_disable_refuses_when_removal_changes_another_unit(service):
    # "pieds = foot = pied": no define references pieds, but the lookup-only row 'pied'
    # only resolves through the pint alias, so removing it would change 'pied' (F2).
    pieds = service.get(token="pieds")
    with pytest.raises(FailedPrecondition, match=r"cannot deactivate 'pieds': it would change 'pied'"):
        service.disable(pieds.id, "editor")
    assert service.get(token="pieds").status is UnitStatus.ACTIVE
