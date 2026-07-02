"""Tests for common_utils.grpc_clients.embedding_client error contract.

chunk_text must re-raise AioRpcError (like get_embeddings) so callers can
classify the failure as transient and retry, instead of receiving [] which
downstream (embedding-service processor) misclassifies as a permanent
"no valid text" error and sends straight to the DLQ.
"""
import sys
import types

import pytest


def _ensure_fake_grpc():
    """Install minimal grpc / grpc_stubs fakes when the real ones are absent.

    grpc_stubs are generated at Docker build time and grpcio is not installed
    on dev machines; CI/Docker environments with the real modules skip this.
    """
    try:
        import grpc  # noqa: F401
    except ImportError:
        grpc_mod = types.ModuleType("grpc")

        class _AioRpcError(Exception):
            def details(self):
                return "fake"

        class _ChannelCM:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *exc):
                return False

        grpc_mod.aio = types.SimpleNamespace(
            AioRpcError=_AioRpcError,
            insecure_channel=lambda url: _ChannelCM(),
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
        pb2_grpc.EmbeddingServiceStub = None  # replaced per-test via monkeypatch
        pkg.embedding_pb2 = pb2
        pkg.embedding_pb2_grpc = pb2_grpc
        sys.modules["grpc_stubs"] = pkg
        sys.modules["grpc_stubs.embedding_pb2"] = pb2
        sys.modules["grpc_stubs.embedding_pb2_grpc"] = pb2_grpc


_ensure_fake_grpc()

# Load embedding_client.py directly: the grpc_clients package __init__ eagerly
# imports every client (database, llm, ...) whose pb2 stubs we did not fake.
import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "common_utils"
    / "grpc_clients"
    / "embedding_client.py"
)
_spec = importlib.util.spec_from_file_location("embedding_client_under_test", _MODULE_PATH)
embedding_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(embedding_client)


def _rpc_error():
    base = embedding_client.grpc.aio.AioRpcError

    class _Boom(base):
        def __init__(self):
            Exception.__init__(self)

        def details(self):
            return "boom"

    return _Boom()


class _StubRaising:
    """EmbeddingServiceStub whose RPCs all fail with AioRpcError."""

    def __init__(self, channel):
        pass

    async def ChunkText(self, request, timeout=None):
        raise _rpc_error()

    async def GetEmbeddings(self, request, timeout=None):
        raise _rpc_error()


@pytest.mark.asyncio
async def test_chunk_text_reraises_grpc_error(monkeypatch):
    monkeypatch.setattr(
        embedding_client.embedding_pb2_grpc, "EmbeddingServiceStub", _StubRaising
    )
    with pytest.raises(embedding_client.grpc.aio.AioRpcError):
        await embedding_client.chunk_text("some text", 500, 100)


@pytest.mark.asyncio
async def test_get_embeddings_reraises_grpc_error(monkeypatch):
    """Pins the pre-existing contract chunk_text now mirrors."""
    monkeypatch.setattr(
        embedding_client.embedding_pb2_grpc, "EmbeddingServiceStub", _StubRaising
    )
    with pytest.raises(embedding_client.grpc.aio.AioRpcError):
        await embedding_client.get_embeddings(["some text"])
