import json
import threading
from datetime import datetime

from infrastructure.unit_events_consumer import UnitEventsConsumer
from infrastructure.unit_state import UnitStateHolder
from unit_registry.events import EVENT_CREATED, make_event
from unit_registry.seed import build_seed_units
from unit_registry.types import Unit

NOW = datetime(2026, 10, 6, 12, 0, 0)
SAC = Unit(id="sac", token="sac_ciment", dimension="mass", pint_definition="sac_ciment = 25 * kilogram",
           sort_order=10_000)


class FakeClient:
    def __init__(self, units, version):
        self.units, self.version, self.calls = units, version, 0

    def list_active(self):
        self.calls += 1
        return list(self.units), self.version


def consumer(holder, client, connect=None):
    return UnitEventsConsumer("amqp://unused", "normalization.units", holder, client, connect=connect)


def test_gap_triggers_a_full_resync():
    holder = UnitStateHolder()
    client = FakeClient([*build_seed_units(), SAC], 5)
    result = consumer(holder, client).handle_body(json.dumps(make_event(EVENT_CREATED, 5, SAC, NOW)).encode())
    assert result == "gap" and client.calls == 1
    assert holder.applied_version == 5 and holder.source == "db"


def test_invalid_payloads_are_dropped():
    holder = UnitStateHolder()
    c = consumer(holder, FakeClient([], 1))
    assert c.handle_body(b"not json") == "invalid"
    assert c.handle_body(b'{"event": "unit.created"}') == "invalid"


def test_initial_resync_happens_even_when_rabbitmq_is_down():
    holder = UnitStateHolder()
    client = FakeClient(build_seed_units(), 3)
    stop = threading.Event()

    def connect():
        stop.set()
        raise ConnectionError("rabbitmq down")

    consumer(holder, client, connect=connect).run_forever(stop)
    assert holder.source == "db" and holder.applied_version == 3
