from datetime import datetime

from unit_registry.types import (
    RegressionSample,
    Unit,
    UnitSource,
    UnitStatus,
    unit_from_dict,
    unit_to_dict,
)


def make_unit(**overrides) -> Unit:
    base = dict(
        id="u1",
        token="Sac",
        dimension="mass",
        pint_definition="sac_ciment = 25 * kilogram = sacs",
        aliases=("SACS",),
        depends_on=(),
        status=UnitStatus.ACTIVE,
        source=UnitSource.MANUAL,
        sort_order=7,
        regression_sample=RegressionSample(
            label="Poids", value="2", expected_canonical_value=50.0, expected_canonical_unit="kilogram"
        ),
        created_by="tester",
        created_at=datetime(2026, 10, 6, 12, 0, 0),
        updated_at=datetime(2026, 10, 6, 12, 0, 0),
    )
    base.update(overrides)
    return Unit(**base)


def test_define_name_is_the_text_before_the_first_equals():
    assert make_unit().define_name == "sac_ciment"
    assert make_unit(pint_definition=None).define_name is None


def test_lookup_keys_are_token_and_aliases_lowercased():
    assert make_unit().lookup_keys() == ["sac", "sacs"]


def test_dict_round_trip_is_lossless():
    unit = make_unit()
    assert unit_from_dict(unit_to_dict(unit)) == unit


def test_dict_round_trip_without_sample_or_dates():
    unit = make_unit(regression_sample=None, created_at=None, updated_at=None)
    assert unit_from_dict(unit_to_dict(unit)) == unit


def test_define_names_lists_the_name_and_every_pint_alias():
    assert make_unit(pint_definition="cheval_vapeur = 735.49875 * watt = cv").define_names == (
        "cheval_vapeur", "cv")
    assert make_unit(pint_definition="decibel = [sound] = dB = dBA").define_names == (
        "decibel", "dB", "dBA")
    assert make_unit(pint_definition="foo_u = 3 * meter = _ = fu").define_names == ("foo_u", "fu")
    assert make_unit(pint_definition="kg = kilogram").define_names == ("kg",)
    assert make_unit(pint_definition=None).define_names == ()
