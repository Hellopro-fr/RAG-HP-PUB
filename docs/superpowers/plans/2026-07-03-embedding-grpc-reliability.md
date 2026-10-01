# Embedding gRPC Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the residual `CANCELLED`/`DEADLINE_EXCEEDED` gRPC errors in the embedding pipeline by unblocking the model-service event loop (S1), sharing a persistent gRPC channel (C1), and setting liveness-sized deadlines (C2).

**Architecture:** Per approved spec `docs/superpowers/specs/2026-07-03-embedding-grpc-reliability-design.md`. S1 offloads the synchronous `chunk_text` off the model-service event loop. C1 replaces per-call gRPC channels with one lazily-created persistent channel in the shared client. C2 raises the ingestion timeouts to liveness bounds. Error classification unchanged.

**Tech Stack:** Python 3.10 asyncio, grpc.aio (faked in tests — not installed locally), pytest + pytest-asyncio, docker-compose env.

**Implementer constraints:**
- Local machine has NO `grpc`, `grpc_stubs`, `aio_pika`, `torch`, `sentence_transformers`, `tritonclient`, `transformers`, `langchain_text_splitters`. Tests MUST fake the needed modules in `sys.modules` (try-real-import-first) and load the module-under-test by file path, bypassing package `__init__` and heavy transitive imports. Proven pattern: `libs/common-utils/tests/test_embedding_grpc_client.py`, `apps-microservices/embedding-service/tests/test_consumer_tunables.py`.
- Commits: Conventional Commits, bilingual EN+FR, via a temp file + `git commit --file=<path>` (heredoc trips the force-push hook). Use the exact messages given.
- Surgical edits; read each file before editing; preserve unrelated lines.

---

### Task 1: S1 — offload ChunkText off the model-service event loop

**Goal:** `ChunkText` runs `chunk_text` in a thread executor so it no longer blocks the asyncio event loop.

**Files:**
- Modify: `apps-microservices/embedding-model-service/infrastructure/grpc_server.py`
- Create: `apps-microservices/embedding-model-service/tests/test_chunktext_offload.py`

**Acceptance Criteria:**
- [ ] `ChunkText` executes `chunk_text` via `loop.run_in_executor(None, ...)` (off the event-loop thread)
- [ ] Returned chunks identical to what `chunk_text` produces
- [ ] Error branch (INTERNAL) preserved

**Verify:** `python -m pytest apps-microservices/embedding-model-service/tests/test_chunktext_offload.py -v` → 2 passed

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/embedding-model-service/tests/test_chunktext_offload.py`:

```python
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
    if "grpc" not in sys.modules:
        grpc_mod = types.ModuleType("grpc")
        grpc_mod.StatusCode = types.SimpleNamespace(INTERNAL="INTERNAL")
        grpc_mod.aio = types.SimpleNamespace(server=lambda *a, **k: None)
        sys.modules["grpc"] = grpc_mod

    if "grpc_stubs" not in sys.modules:
        pkg = types.ModuleType("grpc_stubs")
        pkg.__path__ = []
        pb2 = types.ModuleType("grpc_stubs.embedding_pb2")
        pb2.ChunkResponse = lambda chunks=(): types.SimpleNamespace(chunks=list(chunks))
        pb2.EmbeddingsResponse = lambda embeddings=(): types.SimpleNamespace(embeddings=list(embeddings))
        pb2.EmbeddingVector = lambda vector=(): types.SimpleNamespace(vector=list(vector))
        pb2.TokenizeResponse = lambda tokenized_texts=(): types.SimpleNamespace(tokenized_texts=list(tokenized_texts))
        pb2.TokenizedOutput = lambda tokens=(): types.SimpleNamespace(tokens=list(tokens))
        pb2.DetokenizeResponse = lambda texts=(): types.SimpleNamespace(texts=list(texts))
        pb2_grpc = types.ModuleType("grpc_stubs.embedding_pb2_grpc")
        pb2_grpc.EmbeddingServiceServicer = object
        pb2_grpc.add_EmbeddingServiceServicer_to_server = lambda *a, **k: None
        pkg.embedding_pb2 = pb2
        pkg.embedding_pb2_grpc = pb2_grpc
        sys.modules["grpc_stubs"] = pkg
        sys.modules["grpc_stubs.embedding_pb2"] = pb2
        sys.modules["grpc_stubs.embedding_pb2_grpc"] = pb2_grpc

    # Replace the heavy use-case module with a light stub so grpc_server imports cleanly.
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
    # Proof of offload: chunk_text ran in an executor thread, not the loop thread.
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
```

- [ ] **Step 2: Run to verify RED**

Run: `python -m pytest apps-microservices/embedding-model-service/tests/test_chunktext_offload.py -v`
Expected: `test_chunktext_runs_off_event_loop_thread` FAILS — the current synchronous `ChunkText` runs `chunk_text` on the **main/loop thread**, so `seen["thread"] == main_thread` → `assert seen["thread"] != main_thread` fails. (`test_chunktext_error_sets_internal` likely already passes — the error branch is unchanged.) If you get ImportError, fix the fakes until only the offload assertion fails.

- [ ] **Step 3: Implement the offload**

In `apps-microservices/embedding-model-service/infrastructure/grpc_server.py`:

3a. Add imports after `import logging`:
```python
import asyncio
import functools
```

3b. Replace the body of `ChunkText`:
```python
    async def ChunkText(self, request, context):
        """
        Implémentation de la méthode RPC ChunkText.
        """
        logging.info(f"Requête ChunkText reçue.")
        try:
            # Offload : chunk_text est CPU-lourd (tokenizer par split) et bloquerait
            # l'event loop du serveur, gelant toutes les RPC concurrentes. On l'exécute
            # dans le thread pool par défaut (spec 2026-07-03).
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(
                None,
                functools.partial(
                    self.use_case.chunk_text,
                    request.text,
                    request.chunk_size,
                    request.chunk_overlap,
                ),
            )
            return embedding_pb2.ChunkResponse(chunks=chunks)
        except Exception as e:
            logging.error(f"Erreur dans ChunkText: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Erreur interne lors du chunking du texte.")
            return embedding_pb2.ChunkResponse()
```

- [ ] **Step 4: Run to verify GREEN**

Run: `python -m pytest apps-microservices/embedding-model-service/tests/test_chunktext_offload.py -v`
Expected: 2 passed. Then `python -m py_compile apps-microservices/embedding-model-service/infrastructure/grpc_server.py` → exit 0.

- [ ] **Step 5: Commit** (temp file + `git commit --file=`)

```text
fix(embedding-model): offload ChunkText to executor (unblock event loop)

EN: ChunkText ran chunk_text synchronously inside the async servicer,
and chunk_text calls the HF tokenizer per split — hundreds of blocking
encodes for a big page, freezing the event loop and stalling every
concurrent RPC (root cause of 484/833 client gRPC timeouts, dominant).
Now offloaded via run_in_executor(None). Pure-CPU offload, no GPU,
result unchanged.

FR : ChunkText exécutait chunk_text de façon synchrone dans le servicer
async, et chunk_text appelle le tokenizer HF par split — des centaines
d'encodages bloquants pour une grosse page, gelant l'event loop et
bloquant toutes les RPC concurrentes (cause dominante des 484/833
timeouts gRPC client). Désormais déporté via run_in_executor(None).
Offload CPU pur, sans GPU, résultat inchangé.
```

---

### Task 2: C1 — shared persistent gRPC channel in embedding_client

**Goal:** All 5 client functions reuse one lazily-created persistent channel (with keepalive) instead of opening/closing a channel per call.

**Files:**
- Modify: `libs/common-utils/src/common_utils/grpc_clients/embedding_client.py`
- Modify: `libs/common-utils/tests/test_embedding_grpc_client.py` (add channel-reuse tests)

**Acceptance Criteria:**
- [ ] `grpc.aio.insecure_channel` called at most once across N mixed calls
- [ ] All 5 functions (`get_embeddings`, `get_embedding`, `tokenize`, `detokenize`, `chunk_text`) build stubs from the shared channel
- [ ] Keepalive options passed to the channel
- [ ] No `async with` channel teardown remains
- [ ] Existing re-raise / graceful-empty error contract preserved (existing tests still pass)

**Verify:** `python -m pytest libs/common-utils/tests/test_embedding_grpc_client.py -v` → all pass (existing + new)

**Steps:**

- [ ] **Step 1: Write the failing test** (append to `libs/common-utils/tests/test_embedding_grpc_client.py`)

```python
@pytest.mark.asyncio
async def test_shared_channel_created_once_across_calls(monkeypatch):
    channel_calls = []

    class _FakeChannel:
        def __init__(self, url, options=None):
            channel_calls.append({"url": url, "options": options})

    def _fake_insecure_channel(url, options=None):
        return _FakeChannel(url, options)

    class _StubOK:
        def __init__(self, channel):
            pass

        async def ChunkText(self, request, timeout=None):
            return type("R", (), {"chunks": ["a", "b"]})()

        async def GetEmbeddings(self, request, timeout=None):
            return type("R", (), {"embeddings": [type("V", (), {"vector": [0.1]})()]})()

    monkeypatch.setattr(embedding_client.grpc.aio, "insecure_channel", _fake_insecure_channel)
    monkeypatch.setattr(embedding_client.embedding_pb2_grpc, "EmbeddingServiceStub", _StubOK)
    if hasattr(embedding_client, "_reset_channel_for_tests"):
        await embedding_client._reset_channel_for_tests()

    await embedding_client.chunk_text("t", 500, 100)
    await embedding_client.get_embeddings(["x"])
    await embedding_client.get_embeddings(["y"])

    assert len(channel_calls) == 1  # ONE channel across 3 calls
    assert channel_calls[0]["options"] is not None  # keepalive options set
```

- [ ] **Step 2: Run to verify RED**

Run: `python -m pytest libs/common-utils/tests/test_embedding_grpc_client.py::test_shared_channel_created_once_across_calls -v`
Expected: FAIL with `assert 3 == 1` — the current code opens a fresh channel per call (3 calls → 3 channels).

- [ ] **Step 3: Implement the shared channel**

Edit `libs/common-utils/src/common_utils/grpc_clients/embedding_client.py`.

3a. After the `GRPC_TIMEOUT` line, add the channel machinery:
```python
# Canal gRPC persistant partagé (anti-pattern éliminé : un canal par appel
# provoquait des CANCELLED à la fermeture + surcoût de handshake). Créé
# paresseusement DANS la boucle courante — les canaux grpc.aio sont liés à
# leur event loop, donc pas de création à l'import. Spec 2026-07-03.
_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.keepalive_permit_without_calls", 1),
]

_channel = None


def _get_channel():
    global _channel
    if _channel is None:
        _channel = grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL, options=_CHANNEL_OPTIONS)
    return _channel


async def _reset_channel_for_tests():
    """Ferme et oublie le canal partagé (hermétisme des tests / boucles distinctes)."""
    global _channel
    if _channel is not None:
        try:
            await _channel.close()
        except Exception:
            pass
        _channel = None
```

3b. In EACH of the 5 functions, replace the channel-open block. Pattern — change:
```python
        async with grpc.aio.insecure_channel(EMBEDDING_SERVICE_URL) as channel:
            stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
            ...body...
```
to:
```python
        channel = _get_channel()
        stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
        ...body... (dedented one level)
```

Apply to `get_embeddings`, `tokenize`, `detokenize`, `chunk_text` (each has its own `async with`). `get_embedding` is a wrapper over `get_embeddings` — no change. Keep every `try/except grpc.aio.AioRpcError` and its re-raise / graceful-empty return exactly as-is; only the channel acquisition changes.

Concrete — `get_embeddings` becomes:
```python
async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Appelle le service gRPC pour obtenir les embeddings pour une liste de textes.
    """
    if not texts:
        return []
    try:
        channel = _get_channel()
        stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
        request = embedding_pb2.EmbeddingsRequest(
            texts=texts, source_service=SERVICE_NAME
        )
        response = await stub.GetEmbeddings(request, timeout=GRPC_TIMEOUT)
        return [list(e.vector) for e in response.embeddings]
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service Embedding: {e.details()}")
        raise e
```
`chunk_text` becomes:
```python
async def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    """
    Appelle le service gRPC pour découper un texte en chunks.
    """
    if not text:
        return []
    try:
        channel = _get_channel()
        stub = embedding_pb2_grpc.EmbeddingServiceStub(channel)
        request = embedding_pb2.ChunkRequest(
            text=text, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        response = await stub.ChunkText(request, timeout=GRPC_TIMEOUT)
        return list(response.chunks)
    except grpc.aio.AioRpcError as e:
        logging.error(f"Erreur gRPC en appelant le service de Chunking: {e.details()}")
        return []
```
Apply the same channel swap to `tokenize` and `detokenize` (keep their bodies + graceful-empty returns).

- [ ] **Step 4: Run to verify GREEN + no regression**

Run: `python -m pytest libs/common-utils/tests/test_embedding_grpc_client.py -v`
Expected: all pass — the two existing re-raise tests (`test_chunk_text_reraises_grpc_error`, `test_get_embeddings_reraises_grpc_error`) still pass (their `_StubRaising` still raises through the shared channel), plus the new `test_shared_channel_created_once_across_calls`. Then `python -m py_compile libs/common-utils/src/common_utils/grpc_clients/embedding_client.py` → exit 0.

Note: the existing re-raise tests monkeypatch `EmbeddingServiceStub` but not `insecure_channel`; with the shared channel they call `_get_channel()` which calls the real `grpc.aio.insecure_channel` — but `grpc` is faked in that test's `_ensure_fake_grpc` (returns a fake channel object), so `_get_channel()` succeeds and the stub (raising) is what matters. If a stale `_channel` leaks between tests, add `await embedding_client._reset_channel_for_tests()` at the start of those two tests. Verify by running the whole file; if the two re-raise tests fail on a closed/fake channel, add the reset call to them.

- [ ] **Step 5: Commit**

```text
fix(embedding-client): shared persistent gRPC channel (kill CANCELLED)

EN: every call opened a fresh grpc.aio.insecure_channel; teardown under
an in-flight RPC terminated it CANCELLED, plus a handshake per call.
Replaced with one lazily-created shared channel (bound to the running
loop) + keepalive, reused by all 5 client functions. Error contract
(re-raise for embeddings/chunk, graceful-empty for tokenize/detokenize)
unchanged. Benefits every embedding consumer.

FR : chaque appel ouvrait un grpc.aio.insecure_channel neuf ; sa
fermeture pendant une RPC en vol la terminait en CANCELLED, plus un
handshake par appel. Remplacé par un canal partagé créé paresseusement
(lié à la boucle courante) + keepalive, réutilisé par les 5 fonctions.
Contrat d'erreur (propagation pour embeddings/chunk, vide gracieux pour
tokenize/detokenize) inchangé. Bénéficie à tous les consommateurs.
```

---

### Task 3: C2 — liveness deadlines in embedding-service compose env

**Goal:** embedding-service runs with `GRPC_TIMEOUT=300` / `PROCESS_TIMEOUT=360`.

**Files:**
- Modify: `docker-compose.yml` (embedding-service env block)

**Acceptance Criteria:**
- [ ] `GRPC_TIMEOUT=300` (was 110), `PROCESS_TIMEOUT=360` (was 240)
- [ ] Comment references the censored-tail evidence + S1 ordering assumption
- [ ] YAML parses

**Verify:** `python -c "import yaml; yaml.safe_load(open('docker-compose.yml', encoding='utf-8')); print('OK')"` → OK

**Steps:**

- [ ] **Step 1: Edit the env block**

In `docker-compose.yml`, the embedding-service block currently has (from the livelock fix):
```yaml
      # Fail-fast: ... 45s ...
      - GRPC_TIMEOUT=110
      - PROCESS_TIMEOUT=240
      # Backpressure : 4 replicas x 2 = 8 en vol contre Semaphore(3) non-HIGH.
      - PREFETCH_COUNT=2
```
Read the actual current lines first (the livelock commit set 110/240). Replace the `GRPC_TIMEOUT` + `PROCESS_TIMEOUT` lines and their comment with:
```yaml
      # Liveness (spec 2026-07-03) : temps_embedding.log p99=36.6s, max=109s
      # CENSURÉ au deadline 110 => la vraie traîne dépasse 110s. Deadlines
      # dimensionnés en bornes de liveness (au-dessus du travail réel, en
      # dessous d'un hang). PROCESS_TIMEOUT > GRPC_TIMEOUT tient car S1 rend
      # ChunkText non bloquant (chunk rapide + embed<=300 + publish < 360).
      - GRPC_TIMEOUT=300
      - PROCESS_TIMEOUT=360
      # Backpressure : 4 replicas x 2 = 8 en vol contre Semaphore(3) non-HIGH.
      - PREFETCH_COUNT=2
```
Keep `PREFETCH_COUNT=2` and every other env line unchanged.

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('docker-compose.yml', encoding='utf-8')); print('OK')"`
Expected: `OK`. Also confirm `git diff --stat` shows only `docker-compose.yml`.

- [ ] **Step 3: Commit**

```text
fix(embedding): liveness deadlines GRPC_TIMEOUT=300 / PROCESS_TIMEOUT=360

EN: temps_embedding.log showed p99=36.6s and max=109s censored at the
110s deadline — legitimate big pages exceed 110s and were killed.
Ingestion is async (no SLA), so size the client timeouts as liveness
bounds above the real tail; backpressure (prefetch=2) prevents pile-up.
Ordering holds because S1 makes ChunkText non-blocking.

FR : temps_embedding.log montre p99=36,6s et max=109s censuré au
deadline 110s — de grosses pages légitimes dépassent 110s et étaient
tuées. L'ingestion est asynchrone (pas de SLA) : on dimensionne les
timeouts client en bornes de liveness au-dessus de la vraie traîne ; le
backpressure (prefetch=2) évite l'accumulation. L'ordre tient car S1
rend ChunkText non bloquant.
```

---

## Deploy (operator-controlled — do NOT push)

1. `git push origin features/poc`.
2. VM rebuild: **embedding-model-service** (S1) + **all embedding-consuming images** (C1 is in common-utils, baked into images: embedding-service, api-embedding-service, api-recherche, graph-rag-*). C2 applies at `docker compose up -d embedding-service`.
3. Verify (spec §Verify): ChunkText timeouts `grep "service de Chunking" | grep -ciE "deadline|cancelled"` ≈0; `grep -ci cancelled` ≈0; `temps_embedding.log` max no longer pinned at the deadline.
4. If retry herding persists → open C3 (tiered retry queues).
