"""S1: ChunkText must run chunk_text off the event-loop thread (run_in_executor).

grpc_server imports EmbeddingUseCase (torch, tritonclient, sentence_transformers,
transformers, langchain) which are absent locally — so we fake grpc / grpc_stubs
and REPLACE application.embedding_use_case with a light stub before importing
grpc_server by file path.
"""
import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

SERVER_PATH = (
    Path(__file__).resolve().parents[1] / "infrastructure" / "grpc_server.py"
)


def _install_fakes():
    # AUGMENT, don't skip: another test file (test_embedding_grpc_client.py)
    # installs its OWN grpc/grpc_stubs fakes into sys.modules at import time.
    # A wholesale "if not in sys.modules: build" guard would let that
    # incompatible fake win when the suite runs together (missing StatusCode /
    # ChunkResponse). So ensure each attribute this test needs exists, whatever
    # fake is already present.
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
    spec = importlib.util.spec_from_file_location("grpc_server_under_test", SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Req:
    text = "some text to split"
    chunk_size = 500
    chunk_overlap = 100


class _Ctx:
    def set_code(self, *_): pass
    def set_details(self, *_): pass


@pytest.mark.asyncio
async def test_chunktext_runs_off_event_loop_thread():
    server = _load_server()
    main_thread = threading.get_ident()
    seen = {}

    class FakeUseCase:
        def chunk_text(self, text, chunk_size, chunk_overlap):
            seen["thread"] = threading.get_ident()
            seen["args"] = (text, chunk_size, chunk_overlap)
            return ["chunk-a", "chunk-b"]

    impl = server.EmbeddingServiceImpl(FakeUseCase())
    resp = await impl.ChunkText(_Req(), _Ctx())

    assert list(resp.chunks) == ["chunk-a", "chunk-b"]
    assert seen["args"] == ("some text to split", 500, 100)
    assert seen["thread"] != main_thread


@pytest.mark.asyncio
async def test_chunktext_error_sets_internal():
    server = _load_server()
    codes = {}

    class BoomUseCase:
        def chunk_text(self, *a):
            raise RuntimeError("boom")

    class Ctx:
        def set_code(self, c): codes["code"] = c
        def set_details(self, d): codes["details"] = d

    impl = server.EmbeddingServiceImpl(BoomUseCase())
    resp = await impl.ChunkText(_Req(), Ctx())
    assert list(resp.chunks) == []
    assert codes["code"] == server.grpc.StatusCode.INTERNAL


def test_server_options_permit_client_keepalive_cadence():
    """Regression: the server must accept the client's 30s liveness pings during
    a long GetEmbeddings, or it sends GOAWAY too_many_pings -> UNAVAILABLE loop.
    min_ping_interval_without_data_ms must be <= client keepalive_time_ms (30000)."""
    server = _load_server()
    opts = dict(server._SERVER_OPTIONS)
    assert opts["grpc.keepalive_permit_without_calls"] == 1
    assert opts["grpc.http2.max_ping_strikes"] == 0
    assert opts["grpc.http2.min_ping_interval_without_data_ms"] <= 30000
