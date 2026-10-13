"""R19: a queued request must never wait for a LATER request to be served.

Prod 2026-10-13 11:18:06Z: a MEDIUM request (api-classification-service) sat in
an otherwise idle queue `[H:0, M:1, L:0]` for 300 s until the client deadline,
with zero batch processed in between. Cause: `generate_embeddings` woke a single
waiter with `notify(1)`; when that waiter was a HIGH-only (or LOW-only) worker,
it found its own queue empty and went back to sleep — the wakeup was consumed
and the request left unserved until some other request arrived.

embedding_use_case imports torch, tritonclient, sentence_transformers,
transformers, langchain and common_utils (absent locally), so they are faked
before loading the module by file path; `_process_embeddings` (Triton) is
replaced by an in-memory stub.
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
USE_CASE_PATH = SERVICE_ROOT / "application" / "embedding_use_case.py"

HIGH, MEDIUM, LOW = "svc-high", "svc-medium", "svc-low"
# Idle gap between requests: long enough for every worker to go back to waiting.
IDLE_GAP_S = 0.05
# A request on an idle service is served in milliseconds; 1 s means "stalled".
SERVE_DEADLINE_S = 1.0


def _fake_module(name, **attrs):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    for key, value in attrs.items():
        if not hasattr(mod, key):
            setattr(mod, key, value)
    return mod


def _install_fakes():
    # AUGMENT only: never replace a module another test (or the real env) put there.
    class _Dummy:
        def __init__(self, *a, **k):
            self.tokenizer = self

        @classmethod
        def from_pretrained(cls, *a, **k):
            return cls()

    _fake_module("sentence_transformers", SentenceTransformer=_Dummy)
    _fake_module("tritonclient")
    _fake_module("tritonclient.grpc")
    _fake_module(
        "tritonclient.grpc.aio",
        InferenceServerClient=_Dummy,
        InferInput=_Dummy,
        InferRequestedOutput=_Dummy,
    )
    _fake_module("torch")
    _fake_module("langchain_text_splitters", RecursiveCharacterTextSplitter=_Dummy)
    _fake_module("transformers", AutoTokenizer=_Dummy)
    _fake_module("common_utils")
    _fake_module("common_utils.metrics")
    _fake_module(
        "common_utils.metrics.prometheus",
        measure_processing_time=lambda **k: (lambda fn: fn),
    )


def _load_use_case_module():
    _install_fakes()
    if str(SERVICE_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVICE_ROOT))
    # Other test files install a fake `application` package with an empty
    # __path__; extend it (never replace) so the real application.chunking loads.
    app_pkg = sys.modules.get("application")
    real_dir = str(SERVICE_ROOT / "application")
    if app_pkg is not None and real_dir not in list(getattr(app_pkg, "__path__", [])):
        app_pkg.__path__ = list(getattr(app_pkg, "__path__", [])) + [real_dir]
    spec = importlib.util.spec_from_file_location(
        "r19_embedding_use_case", USE_CASE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HIGH_PRIORITY_SERVICES = {HIGH}
    module.MEDIUM_PRIORITY_SERVICES = {MEDIUM}
    return module


@pytest.fixture
def use_case_module():
    return _load_use_case_module()


async def _started_use_case(module):
    use_case = module.EmbeddingUseCase()
    use_case.max_concurrent_requests = 10  # prod: TOTAL_MAX_CONCURRENT_REQUESTS=10

    async def _fake_process_embeddings(texts, executor=None, limiter=None):
        return [[float(len(t))] for t in texts]

    use_case._process_embeddings = _fake_process_embeddings
    await use_case.start_workers()
    await asyncio.sleep(IDLE_GAP_S)  # every worker reaches its wait
    return use_case


async def _stop(use_case):
    for worker in use_case.workers:
        worker.cancel()
    await asyncio.gather(*use_case.workers, return_exceptions=True)
    use_case._high_executor.shutdown(wait=False)
    use_case._default_executor.shutdown(wait=False)


async def _served_flags(module, sources):
    """Send each request alone on an idle service; True = served before deadline."""
    use_case = await _started_use_case(module)
    try:
        flags = []
        for source in sources:
            try:
                await asyncio.wait_for(
                    use_case.generate_embeddings(["x"], source_service=source),
                    SERVE_DEADLINE_S,
                )
                flags.append(True)
            except asyncio.TimeoutError:
                flags.append(False)
            await asyncio.sleep(IDLE_GAP_S)
        return flags
    finally:
        await _stop(use_case)


@pytest.mark.parametrize("source", [MEDIUM, LOW])
def test_lower_priority_request_is_served_on_idle_service(use_case_module, source):
    flags = asyncio.run(_served_flags(use_case_module, [source] * 6))
    assert flags == [True] * 6


def test_high_request_is_served_whatever_the_waiter_order(use_case_module):
    # Each consumed wakeup sends its waiter to the tail of the Condition's queue.
    # After two MEDIUM requests the HIGH workers sit past the first
    # high+shared waiters, so `notify(high + shared)` woke only workers that
    # cannot serve HIGH (shared ones re-park while HIGH holds the gate):
    # the HIGH request stalled too (deterministic on the pre-fix code).
    flags = asyncio.run(_served_flags(use_case_module, [MEDIUM, MEDIUM, HIGH]))
    assert flags[-1] is True


def test_results_reach_the_right_caller(use_case_module):
    # Guard on the stub path itself: each caller gets the vector of ITS text.
    async def scenario():
        use_case = await _started_use_case(use_case_module)
        try:
            return await asyncio.gather(
                use_case.generate_embeddings(["a"], source_service=MEDIUM),
                use_case.generate_embeddings(["bbb"], source_service=LOW),
                use_case.generate_embeddings(["cc"], source_service=HIGH),
            )
        finally:
            await _stop(use_case)

    assert asyncio.run(scenario()) == [[[1.0]], [[3.0]], [[2.0]]]
