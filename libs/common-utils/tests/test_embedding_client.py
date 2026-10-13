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


# --- Relance sur UNAVAILABLE (R20, 2026-10-13) --------------------------------
# Un vrai serveur grpc.aio local répond UNAVAILABLE puis OK : prouve que la
# politique de _CHANNEL_OPTIONS est lue par grpcio et appliquée au bon nom de
# service. Ne prouve PAS la ré-résolution DNS après recréation du conteneur :
# celle-ci se vérifie sur la VM.
_REAL_GRPC = hasattr(embedding_client.grpc.aio, "server")
_METHOD = "/embedding.EmbeddingService/GetEmbeddings"


def _run_against_server(script, options):
    """Lance un serveur qui rejoue `script` (un code par tentative, None = OK).

    Rend (réponse ou code d'erreur client, nombre de tentatives reçues).
    """
    import asyncio

    grpc = embedding_client.grpc
    attempts = []

    async def _handler(request, context):
        code = script[min(len(attempts), len(script) - 1)]
        attempts.append(code)
        if code is not None:
            await context.abort(code, "scripted")
        return b"ok"

    async def _main():
        server = grpc.aio.server()
        server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    "embedding.EmbeddingService",
                    {"GetEmbeddings": grpc.unary_unary_rpc_method_handler(_handler)},
                ),
            )
        )
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        try:
            async with grpc.aio.insecure_channel(
                f"127.0.0.1:{port}", options=options
            ) as channel:
                call = channel.unary_unary(_METHOD)
                try:
                    return await call(b"x", timeout=20), len(attempts)
                except grpc.aio.AioRpcError as e:
                    return e.code(), len(attempts)
        finally:
            await server.stop(None)

    return asyncio.run(_main())


_needs_real_grpc = pytest.mark.skipif(not _REAL_GRPC, reason="grpcio absent")


@_needs_real_grpc
def test_unavailable_is_retried_until_success():
    unavailable = embedding_client.grpc.StatusCode.UNAVAILABLE
    result, attempts = _run_against_server(
        [unavailable, unavailable, None], embedding_client._CHANNEL_OPTIONS
    )
    assert (result, attempts) == (b"ok", 3)


@_needs_real_grpc
def test_without_the_policy_unavailable_fails_on_first_attempt():
    # Témoin : même serveur, options sans la politique => l'ancien comportement.
    unavailable = embedding_client.grpc.StatusCode.UNAVAILABLE
    options = [
        (k, v)
        for k, v in embedding_client._CHANNEL_OPTIONS
        if k not in ("grpc.service_config", "grpc.enable_retries")
    ]
    result, attempts = _run_against_server([unavailable, None], options)
    assert (result, attempts) == (unavailable, 1)


@_needs_real_grpc
def test_unavailable_gives_up_after_three_attempts():
    unavailable = embedding_client.grpc.StatusCode.UNAVAILABLE
    result, attempts = _run_against_server(
        [unavailable], embedding_client._CHANNEL_OPTIONS
    )
    assert (result, attempts) == (unavailable, 3)


@_needs_real_grpc
@pytest.mark.parametrize("code_name", ["DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"])
def test_other_codes_are_not_retried(code_name):
    code = getattr(embedding_client.grpc.StatusCode, code_name)
    result, attempts = _run_against_server(
        [code, None], embedding_client._CHANNEL_OPTIONS
    )
    assert (result, attempts) == (code, 1)
