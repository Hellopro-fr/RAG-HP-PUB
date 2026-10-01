"""Symmetry of the 64 MB gRPC message limit on the SERVER side.

The common-utils client raised grpc.max_receive_message_length to 64 MB
(GetEmbeddings responses for ~1000+ chunk pages exceed the 4 MiB default).
The server keeps the 4 MiB RECEIVE default unless overridden: a page whose
raw text exceeds ~4 MB would then fail the ChunkText/GetEmbeddings REQUEST
server-side with the same RESOURCE_EXHAUSTED class of error.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SERVER_PATH = (
    Path(__file__).resolve().parents[1] / "infrastructure" / "grpc_server.py"
)

_64MB = 64 * 1024 * 1024


def _install_fakes():
    # AUGMENT, don't replace — see test_chunktext_offload.py: other test files
    # install their own grpc/grpc_stubs fakes; ensure only what we need exists.
    grpc_mod = sys.modules.get("grpc")
    if grpc_mod is None:
        grpc_mod = types.ModuleType("grpc")
        sys.modules["grpc"] = grpc_mod
    if not hasattr(grpc_mod, "StatusCode"):
        grpc_mod.StatusCode = types.SimpleNamespace(INTERNAL="INTERNAL")
    if not hasattr(grpc_mod, "aio"):
        grpc_mod.aio = types.SimpleNamespace()
    if not hasattr(grpc_mod.aio, "server"):
        grpc_mod.aio.server = lambda *a, **k: None

    pkg = sys.modules.get("grpc_stubs")
    if pkg is None:
        pkg = types.ModuleType("grpc_stubs")
        pkg.__path__ = []
        sys.modules["grpc_stubs"] = pkg
    pb2 = sys.modules.get("grpc_stubs.embedding_pb2")
    if pb2 is None:
        pb2 = types.ModuleType("grpc_stubs.embedding_pb2")
        sys.modules["grpc_stubs.embedding_pb2"] = pb2
        pkg.embedding_pb2 = pb2
    if not hasattr(pb2, "ChunkResponse"):
        pb2.ChunkResponse = lambda chunks=(): types.SimpleNamespace(chunks=list(chunks))
    pb2_grpc = sys.modules.get("grpc_stubs.embedding_pb2_grpc")
    if pb2_grpc is None:
        pb2_grpc = types.ModuleType("grpc_stubs.embedding_pb2_grpc")
        sys.modules["grpc_stubs.embedding_pb2_grpc"] = pb2_grpc
        pkg.embedding_pb2_grpc = pb2_grpc
    if not hasattr(pb2_grpc, "EmbeddingServiceServicer"):
        pb2_grpc.EmbeddingServiceServicer = object
    if not hasattr(pb2_grpc, "add_EmbeddingServiceServicer_to_server"):
        pb2_grpc.add_EmbeddingServiceServicer_to_server = lambda *a, **k: None

    app_pkg = sys.modules.setdefault("application", types.ModuleType("application"))
    if not hasattr(app_pkg, "__path__"):
        app_pkg.__path__ = []
    uc_mod = types.ModuleType("application.embedding_use_case")
    uc_mod.EmbeddingUseCase = object
    sys.modules["application.embedding_use_case"] = uc_mod


def _load_server():
    _install_fakes()
    spec = importlib.util.spec_from_file_location(
        "grpc_server_options_under_test", SERVER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_server_options_raise_receive_limit_to_64mb():
    server_mod = _load_server()
    options = dict(server_mod._SERVER_OPTIONS)
    assert options.get("grpc.max_receive_message_length") == _64MB


@pytest.mark.asyncio
async def test_serve_passes_options_to_grpc_server(monkeypatch):
    server_mod = _load_server()
    captured = {}

    class _FakeServer:
        def add_insecure_port(self, addr):
            captured["port"] = addr

        async def start(self):
            pass

        async def wait_for_termination(self):
            pass

    def _fake_server(executor, options=None):
        captured["options"] = options
        return _FakeServer()

    monkeypatch.setattr(server_mod.grpc.aio, "server", _fake_server)

    await server_mod.serve(object())

    options = dict(captured["options"])
    assert options.get("grpc.max_receive_message_length") == _64MB
    assert captured["port"] == "[::]:50052"
