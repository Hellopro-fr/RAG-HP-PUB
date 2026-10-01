"""Tests for embedding-service consumer env tunables (PREFETCH_COUNT / PROCESS_TIMEOUT).

Spec: docs/superpowers/specs/2026-07-02-embedding-livelock-backpressure-design.md
aio_pika / grpc are not installed on dev machines: fake the import surface in
sys.modules and load consumer.py by file path (same pattern as
libs/common-utils/tests/test_embedding_grpc_client.py).
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

CONSUMER_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "messaging" / "consumer.py"
)


def _install_fakes():
    """Fake aio_pika + the service/service-lib modules consumer.py imports."""
    try:
        import aio_pika  # noqa: F401
    except ImportError:
        aio = types.ModuleType("aio_pika")
        aio.Connection = type("Connection", (), {})
        aio.Message = lambda **kw: types.SimpleNamespace(**kw)
        aio.ExchangeType = types.SimpleNamespace(TOPIC="topic")
        aio.DeliveryMode = types.SimpleNamespace(PERSISTENT=2)
        abc_mod = types.ModuleType("aio_pika.abc")
        abc_mod.AbstractChannel = type("AbstractChannel", (), {})
        abc_mod.AbstractIncomingMessage = type("AbstractIncomingMessage", (), {})
        aio.abc = abc_mod
        sys.modules["aio_pika"] = aio
        sys.modules["aio_pika.abc"] = abc_mod

    try:
        from embedding_service.messaging.publisher import Publisher  # noqa: F401
    except ImportError:
        pub_mod = types.ModuleType("embedding_service.messaging.publisher")
        pub_mod.Publisher = type("Publisher", (), {})
        sys.modules["embedding_service.messaging.publisher"] = pub_mod

    try:
        from embedding_service.core.processor import embed_input_data  # noqa: F401
    except ImportError:
        proc_mod = types.ModuleType("embedding_service.core.processor")

        async def embed_input_data(input_data, **kwargs):
            return {"collection": "produits", "data": [{"embedding": [0.1]}]}

        proc_mod.embed_input_data = embed_input_data
        sys.modules["embedding_service.core.processor"] = proc_mod

    try:
        from common_utils.autres.DLQProperties import DLQProperties  # noqa: F401
    except ImportError:
        dlq_mod = types.ModuleType("common_utils.autres.DLQProperties")

        class DLQProperties:
            @staticmethod
            def create_dlq_headers(error, service, retry_count, message):
                return {"error": repr(error)}

        dlq_mod.DLQProperties = DLQProperties
        sys.modules["common_utils.autres.DLQProperties"] = dlq_mod


def _load_consumer():
    _install_fakes()
    spec = importlib.util.spec_from_file_location("consumer_under_test", CONSUMER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prefetch_count_defaults_to_2(monkeypatch):
    monkeypatch.delenv("PREFETCH_COUNT", raising=False)
    mod = _load_consumer()
    assert mod.PREFETCH_COUNT == 2


def test_tunables_read_from_env(monkeypatch):
    monkeypatch.setenv("PREFETCH_COUNT", "7")
    monkeypatch.setenv("PROCESS_TIMEOUT", "33.5")
    mod = _load_consumer()
    assert mod.PREFETCH_COUNT == 7
    assert mod.PROCESS_TIMEOUT == 33.5


class _FakeQueue:
    def __init__(self):
        self.consume_cb = None

    async def bind(self, *a, **kw):
        return None

    async def consume(self, cb):
        self.consume_cb = cb


class _FakeChannel:
    def __init__(self):
        self.qos_kwargs = None
        self.queue = _FakeQueue()

    async def set_qos(self, **kw):
        self.qos_kwargs = kw

    async def declare_exchange(self, *a, **kw):
        return types.SimpleNamespace()

    async def declare_queue(self, *a, **kw):
        return self.queue


class _FakeConnection:
    def __init__(self, channel):
        self._channel = channel

    async def channel(self):
        return self._channel


@pytest.mark.asyncio
async def test_start_consuming_applies_prefetch_env(monkeypatch):
    monkeypatch.setenv("PREFETCH_COUNT", "5")
    mod = _load_consumer()
    channel = _FakeChannel()
    consumer = mod.Consumer(_FakeConnection(channel), publisher=None)

    task = asyncio.ensure_future(consumer.start_consuming())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert channel.qos_kwargs == {"prefetch_count": 5}
    assert channel.queue.consume_cb is not None


class _FakeProcessCM:
    """Mimics message.process(requeue=False): re-raises whatever the block raises."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessage:
    headers = None
    body = b'{"collection": "produits", "data": {"text": "x"}}'

    def process(self, requeue=False):
        return _FakeProcessCM()


@pytest.mark.asyncio
async def test_process_timeout_env_drives_wait_for(monkeypatch):
    monkeypatch.setenv("PROCESS_TIMEOUT", "0.05")
    mod = _load_consumer()

    async def slow_embed(input_data, **kwargs):
        await asyncio.sleep(1.0)

    monkeypatch.setattr(mod, "embed_input_data", slow_embed)
    consumer = mod.Consumer(_FakeConnection(_FakeChannel()), publisher=None)

    with pytest.raises(Exception, match="Timeout de traitement"):
        await consumer._process_message_task(_FakeMessage())
