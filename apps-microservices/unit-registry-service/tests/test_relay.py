import json
import threading

import pytest
from sqlalchemy import select

from application.unit_service import UnitDraft, UnitService
from infrastructure.db.models import UnitEventRow
from infrastructure.messaging.relay import OutboxRelay
from unit_registry.types import RegressionSample

from .conftest import NOW


class FakePublisher:
    def __init__(self, fail_on_call: int | None = None):
        self.bodies: list[dict] = []
        self.calls = 0
        self.fail_on_call = fail_on_call
        self.resets = 0

    def publish(self, body: bytes) -> None:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ConnectionError("broker nack")
        self.bodies.append(json.loads(body))

    def heartbeat(self) -> None:
        pass

    def reset(self) -> None:
        self.resets += 1


@pytest.fixture
def three_events(seeded):
    service = UnitService(seeded, clock=lambda: NOW)
    for n, factor in enumerate((25, 30, 35)):
        service.register(UnitDraft(
            token=f"sac_{n}", dimension="mass", pint_definition=f"sac_{n} = {factor} * kilogram",
            regression_sample=RegressionSample(label="Poids", value="1", expected_canonical_value=float(factor),
                                               expected_canonical_unit="kilogram")), "tester")
    return seeded


def published_versions(factory):
    with factory() as s:
        return [r.registry_version for r in s.execute(select(UnitEventRow).order_by(UnitEventRow.id)).scalars()
                if r.published_at is not None]


def test_publishes_in_version_order_and_marks_rows(three_events):
    publisher = FakePublisher()
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 3
    assert [b["registry_version"] for b in publisher.bodies] == [2, 3, 4]
    assert published_versions(three_events) == [2, 3, 4]
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 0


def test_a_failed_publish_leaves_the_rest_for_the_next_run(three_events):
    with pytest.raises(ConnectionError):
        OutboxRelay(three_events, FakePublisher(fail_on_call=2), clock=lambda: NOW).run_once()
    assert published_versions(three_events) == [2]
    publisher = FakePublisher()
    assert OutboxRelay(three_events, publisher, clock=lambda: NOW).run_once() == 2
    assert [b["registry_version"] for b in publisher.bodies] == [3, 4]


def test_run_forever_resets_the_publisher_after_a_failure(three_events):
    stop = threading.Event()
    publisher = FakePublisher(fail_on_call=1)
    original_reset = publisher.reset

    def reset_then_stop():
        original_reset()
        stop.set()

    publisher.reset = reset_then_stop
    OutboxRelay(three_events, publisher, clock=lambda: NOW).run_forever(stop, poll_seconds=0.01)
    assert publisher.resets == 1
