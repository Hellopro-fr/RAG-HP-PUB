from datetime import datetime

from unit_registry.proto_codec import unit_from_proto, unit_to_proto
from unit_registry.types import RegressionSample, Unit, UnitSource, UnitStatus


def test_unit_proto_round_trip_keeps_every_field():
    unit = Unit(
        id="u1", token="sac", dimension="mass", pint_definition="sac_c = 25 * kilogram",
        aliases=("sacs",), depends_on=("kilogram",), status=UnitStatus.DISABLED,
        source=UnitSource.MANUAL, sort_order=300,
        regression_sample=RegressionSample(label="Poids", value="1", value_max="2",
                                           data_type="numeric_range", expected_canonical_value=25.0,
                                           expected_canonical_max=50.0, expected_canonical_unit="kilogram"),
        created_by="mcp:test", created_at=datetime(2026, 10, 6, 12, 0, 1),
        updated_at=datetime(2026, 10, 6, 12, 0, 2),
    )
    message = unit_to_proto(unit, registry_version=9, types=["CAPACITY"])
    assert message.registry_version == 9 and list(message.types) == ["CAPACITY"]
    assert unit_from_proto(message) == unit


def test_empty_optional_fields_map_to_none():
    message = unit_to_proto(Unit(id="u2", token="galette", dimension=None))
    back = unit_from_proto(message)
    assert back.dimension is None and back.pint_definition is None and back.regression_sample is None
