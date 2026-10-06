import pytest

from infrastructure.messaging import publisher as publisher_module
from infrastructure.messaging.publisher import PikaPublisher


class FakeChannel:
    def __init__(self, fail_on: str | None):
        self.fail_on = fail_on
        self.is_closed = False

    def exchange_declare(self, **_):
        if self.fail_on == "declare":
            raise RuntimeError("declare refused")

    def confirm_delivery(self):
        if self.fail_on == "confirm":
            raise RuntimeError("confirm refused")


class FakeConnection:
    instances: list["FakeConnection"] = []

    def __init__(self, fail_on: str | None):
        self.is_open = True
        self.closed = False
        self._channel = FakeChannel(fail_on)
        FakeConnection.instances.append(self)

    def channel(self):
        return self._channel

    def close(self):
        self.closed = True
        self.is_open = False


@pytest.fixture
def fake_pika(monkeypatch):
    FakeConnection.instances = []
    state = {"fail_on": None}
    monkeypatch.setattr(publisher_module.pika, "BlockingConnection",
                        lambda params: FakeConnection(state["fail_on"]))
    return state


@pytest.mark.parametrize("fail_on", ["declare", "confirm"])
def test_a_failed_channel_setup_closes_the_connection_and_keeps_nothing(fake_pika, fail_on):
    fake_pika["fail_on"] = fail_on
    pub = PikaPublisher("amqp://x", "normalization.units")
    with pytest.raises(RuntimeError):
        pub._ensure_channel()
    assert FakeConnection.instances[0].closed
    assert pub._connection is None and pub._channel is None


def test_a_successful_setup_keeps_the_channel(fake_pika):
    pub = PikaPublisher("amqp://x", "normalization.units")
    channel = pub._ensure_channel()
    assert pub._channel is channel and pub._connection is FakeConnection.instances[0]
    assert pub._ensure_channel() is channel and len(FakeConnection.instances) == 1
