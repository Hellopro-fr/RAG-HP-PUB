from datetime import datetime

import pytest

from unit_registry.events import EVENT_CREATED, make_event, parse_event
from unit_registry.types import Unit


def test_event_round_trip():
    unit = Unit(id="u1", token="sac", dimension="mass")
    payload = make_event(EVENT_CREATED, 7, unit, datetime(2026, 10, 6, 12, 0, 0))
    assert payload["occurred_at"] == "2026-10-06T12:00:00Z"
    assert parse_event(payload) == (EVENT_CREATED, 7, unit)


@pytest.mark.parametrize("payload", [
    {},
    {"event": "unit.created"},
    {"event": "nope", "registry_version": 1, "unit": {"id": "u", "token": "t", "status": "ACTIVE", "source": "manual"}},
])
def test_malformed_events_raise_value_error(payload):
    with pytest.raises(ValueError):
        parse_event(payload)
