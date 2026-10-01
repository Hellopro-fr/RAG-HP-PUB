"""Tests for common_utils.grpc_clients.embedding_client channel sizing.

Incident 2026-07: a ~957k-char page produced ~1035 chunks; the GetEmbeddings
response (1035 x 1024 float32 vectors ~= 4.24 MB) exceeded the gRPC default
grpc.max_receive_message_length of 4 MiB -> RESOURCE_EXHAUSTED on the CLIENT,
classified transient, retried 3x deterministically, then DLQ'd.
The shared channel must therefore raise its receive limit.
"""
import sys
import types

import pytest


def _ensure_fake_grpc():
    """Install minimal grpc / grpc_stubs fakes when the real ones are absent.

    Mirrors test_embedding_grpc_client.py: grpc_stubs are generated at Docker
    build time and grpcio may be absent on dev machines. If another test file
    already installed compatible fakes, the imports below succeed and we keep
    them (augment, don't replace).
    """
    try:
        import grpc  # noqa: F401
    except ImportError:
        grpc_mod = types.ModuleType("grpc")

        class _AioRpcError(Exception):
            def details(self):
                return "fake"

        grpc_mod.aio = types.SimpleNamespace(
            AioRpcError=_AioRpcError,
            insecure_channel=lambda url, options=None: object(),
        )
        sys.modules["grpc"] = grpc_mod

    try:
        from grpc_stubs import embedding_pb2  # noqa: F401
    except ImportError:
        pkg = types.ModuleType("grpc_stubs")
        pkg.__path__ = []
        pb2 = types.ModuleType("grpc_stubs.embedding_pb2")
        for name in (
            "ChunkRequest",
            "EmbeddingsRequest",
            "TokenizeRequest",
            "DetokenizeRequest",
            "TokenizedOutput",
        ):
            setattr(pb2, name, lambda **kw: types.SimpleNamespace(**kw))
        pb2_grpc = types.ModuleType("grpc_stubs.embedding_pb2_grpc")
        pb2_grpc.EmbeddingServiceStub = None
        pkg.embedding_pb2 = pb2
        pkg.embedding_pb2_grpc = pb2_grpc
        sys.modules["grpc_stubs"] = pkg
        sys.modules["grpc_stubs.embedding_pb2"] = pb2
        sys.modules["grpc_stubs.embedding_pb2_grpc"] = pb2_grpc


_ensure_fake_grpc()

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "common_utils"
    / "grpc_clients"
    / "embedding_client.py"
)
_spec = importlib.util.spec_from_file_location(
    "embedding_client_options_under_test", _MODULE_PATH
)
embedding_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(embedding_client)

_64MB = 64 * 1024 * 1024


def test_channel_options_raise_receive_limit_to_64mb():
    options = dict(embedding_client._CHANNEL_OPTIONS)
    assert options.get("grpc.max_receive_message_length") == _64MB


def test_channel_is_created_with_the_raised_limit(monkeypatch):
    channel_calls = []

    def _fake_insecure_channel(url, options=None):
        channel_calls.append({"url": url, "options": options})
        return object()

    class _StubOK:
        def __init__(self, channel):
            pass

        async def GetEmbeddings(self, request, timeout=None):
            return types.SimpleNamespace(
                embeddings=[types.SimpleNamespace(vector=[0.1])]
            )

    monkeypatch.setattr(
        embedding_client.grpc.aio, "insecure_channel", _fake_insecure_channel
    )
    monkeypatch.setattr(
        embedding_client.embedding_pb2_grpc, "EmbeddingServiceStub", _StubOK
    )

    async def _run():
        await embedding_client._reset_channel_for_tests()
        await embedding_client.get_embeddings(["x"])
        await embedding_client._reset_channel_for_tests()

    import asyncio

    asyncio.run(_run())

    assert len(channel_calls) == 1
    options = dict(channel_calls[0]["options"])
    assert options.get("grpc.max_receive_message_length") == _64MB
