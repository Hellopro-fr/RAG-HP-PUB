# Embedding-Service Livelock Fix (Backpressure + Budget Realignment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the embedding-service retry livelock by making consumer concurrency and timeouts env-tunable (`PREFETCH_COUNT=2`, `PROCESS_TIMEOUT=240`) and restoring the gRPC completion band (`GRPC_TIMEOUT=110`).

**Architecture:** Two changes per the approved spec `docs/superpowers/specs/2026-07-02-embedding-livelock-backpressure-design.md`: (1) `consumer.py` reads two new env tunables at import and uses them in `set_qos` / `asyncio.wait_for`; (2) `docker-compose.yml` sets `GRPC_TIMEOUT=110` plus the two new vars explicitly. No shared-lib or model-service change. Error classification is untouched.

**Tech Stack:** Python 3.10 asyncio, aio-pika (faked in tests — not installed locally), pytest + pytest-asyncio, docker-compose env.

**Constraints for the implementer:**
- Local machine has NO `aio_pika`, NO `grpc`, NO `grpc_stubs`. Tests must fake them in `sys.modules` and load `consumer.py` by file path (bypassing package imports). The pattern is proven in `libs/common-utils/tests/test_embedding_grpc_client.py`.
- Commits: Conventional Commits, bilingual EN+FR, via `git commit --file=<temp>` (a heredoc with `-f`-like tokens trips the force-push blocker hook).

---

### Task 1: Consumer env tunables (PREFETCH_COUNT, PROCESS_TIMEOUT) with tests

**Goal:** `consumer.py` reads `PREFETCH_COUNT` (default 2) and `PROCESS_TIMEOUT` (default 240) from env and uses them in QoS and the per-message timeout; timeout messages report the actual configured value.

**Files:**
- Modify: `apps-microservices/embedding-service/app/messaging/consumer.py`
- Test (create): `apps-microservices/embedding-service/tests/test_consumer_tunables.py`
- Modify: `apps-microservices/embedding-service/CLAUDE.md` (RabbitMQ Topology section: prefetch + timeout now env-driven)

**Acceptance Criteria:**
- [ ] `PREFETCH_COUNT` defaults to 2, overridable by env; used in `channel.set_qos`
- [ ] `PROCESS_TIMEOUT` defaults to 240.0, overridable by env; used in `asyncio.wait_for`
- [ ] Timeout log + DLQ reason strings report the configured value (no hardcoded "120s")
- [ ] Existing behavior otherwise unchanged (retry/DLQ routing identical)

**Verify:** `python -m pytest apps-microservices/embedding-service/tests/test_consumer_tunables.py -v` → 4 passed

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `apps-microservices/embedding-service/tests/test_consumer_tunables.py`:

```python
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
    if "aio_pika" not in sys.modules:
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

    if "embedding_service.messaging.publisher" not in sys.modules:
        pub_mod = types.ModuleType("embedding_service.messaging.publisher")
        pub_mod.Publisher = type("Publisher", (), {})
        sys.modules["embedding_service.messaging.publisher"] = pub_mod

    if "embedding_service.core.processor" not in sys.modules:
        proc_mod = types.ModuleType("embedding_service.core.processor")

        async def embed_input_data(input_data, **kwargs):
            return {"collection": "produits", "data": [{"embedding": [0.1]}]}

        proc_mod.embed_input_data = embed_input_data
        sys.modules["embedding_service.core.processor"] = proc_mod

    if "common_utils.autres.DLQProperties" not in sys.modules:
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
    monkeypatch.setenv("PREFETCH_COUNT", "2")
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

    assert channel.qos_kwargs == {"prefetch_count": 2}
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
```

- [ ] **Step 2: Run tests to verify they fail correctly**

Run: `python -m pytest apps-microservices/embedding-service/tests/test_consumer_tunables.py -v`
Expected: `test_prefetch_count_defaults_to_2` and `test_tunables_read_from_env` FAIL with `AttributeError: module 'consumer_under_test' has no attribute 'PREFETCH_COUNT'`; `test_start_consuming_applies_prefetch_env` FAIL (qos called with `prefetch_count=10`); `test_process_timeout_env_drives_wait_for` FAIL (no timeout at 0.05s — the hardcoded 120s applies, `pytest.raises` gets nothing). Any other failure mode (ImportError etc.) = fix the fakes first, re-run until failures are exactly these.

- [ ] **Step 3: Implement the tunables in consumer.py**

In `apps-microservices/embedding-service/app/messaging/consumer.py`:

3a. Add `import os` to the imports block:

```python
import aio_pika
import json
import asyncio
import logging
import os
```

3b. Replace the constants block:

```python
MAX_RETRIES = 3
RETRY_TTL_MS = 30000
# Tunables (spec 2026-07-02 livelock) : backpressure + budget par message.
# PREFETCH_COUNT : messages simultanés par replica (défaut 2 — aligné sur le
#   Semaphore(3) non-HIGH du model-service ; 4 replicas x 2 = 8 en vol).
# PROCESS_TIMEOUT : plafond global par message ; doit rester > 2x GRPC_TIMEOUT
#   (pire cas ChunkText + GetEmbeddings au deadline) pour que le DEADLINE gRPC
#   (retryable proprement) parte AVANT ce plafond.
PREFETCH_COUNT = int(os.getenv("PREFETCH_COUNT", "2"))
PROCESS_TIMEOUT = float(os.getenv("PROCESS_TIMEOUT", "240"))
```

3c. In `_process_message_task`, replace the `wait_for` call:

```python
                # Exécute l'embedding et le publishing avec un timeout global
                await asyncio.wait_for(
                    process_and_publish(),
                    timeout=PROCESS_TIMEOUT
                )
```

3d. Replace the `asyncio.TimeoutError` branch strings (both sub-branches):

```python
            except asyncio.TimeoutError as e:
                # Timeout spécifique pour éviter le gel du loop
                retry_count = self._get_retry_count(message)
                if retry_count < MAX_RETRIES:
                    print(f"⏱️ Timeout après {PROCESS_TIMEOUT:g}s (essai {retry_count + 1}/{MAX_RETRIES + 1}). Redirection vers Retry Queue.")
                    # Levée d'exception pour déclencher le NACK(requeue=False) automatique vers la Retry Queue
                    raise Exception(f"Timeout de traitement (>{PROCESS_TIMEOUT:g}s)")
                else:
                    print(f"⏱️ Échec (Timeout) après {MAX_RETRIES + 1} tentatives. Message envoyé à la DLQ finale.")
                    await self._send_to_dlq(message, Exception(f"Timeout de traitement (>{PROCESS_TIMEOUT:g}s)"), MAX_RETRIES)
                    # Pas de levée d'exception -> le message est ACK et supprimé
```

3e. In `start_consuming`, replace the QoS line:

```python
        await channel.set_qos(prefetch_count=PREFETCH_COUNT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest apps-microservices/embedding-service/tests/test_consumer_tunables.py -v`
Expected: 4 passed. Then syntax-check: `python -m py_compile apps-microservices/embedding-service/app/messaging/consumer.py` → exit 0.

- [ ] **Step 5: Update the service CLAUDE.md**

In `apps-microservices/embedding-service/CLAUDE.md`, RabbitMQ Topology section, replace the line:

```markdown
- Prefetch: 10, poison message shield (x-death > 10)
```

with:

```markdown
- Prefetch: env `PREFETCH_COUNT` (default 2), poison message shield (x-death > 10)
- Per-message timeout: env `PROCESS_TIMEOUT` (default 240s); keep > 2x `GRPC_TIMEOUT` so the gRPC deadline fires first (spec 2026-07-02)
```

- [ ] **Step 6: Commit (bilingual, via temp file)**

```bash
git add apps-microservices/embedding-service/app/messaging/consumer.py apps-microservices/embedding-service/tests/test_consumer_tunables.py apps-microservices/embedding-service/CLAUDE.md
git commit --file=<temp file containing the bilingual message below>
```

```text
feat(embedding): env-tunable consumer prefetch + per-message timeout

EN: PREFETCH_COUNT (default 2) and PROCESS_TIMEOUT (default 240s)
replace the hardcoded prefetch 10 / wait_for 120s. Purpose: break the
retry livelock — fewer in-flight messages cut Triton Semaphore
contention, and the per-message cap now exceeds the 2x GRPC_TIMEOUT
worst case so the retryable gRPC deadline fires first. Timeout strings
report the configured value.

FR : PREFETCH_COUNT (défaut 2) et PROCESS_TIMEOUT (défaut 240s)
remplacent le prefetch 10 / wait_for 120s codés en dur. But : casser le
livelock de retry — moins de messages en vol réduit la contention sur
le Semaphore Triton, et le plafond par message dépasse désormais le
pire cas 2x GRPC_TIMEOUT pour que le deadline gRPC (retryable) parte en
premier. Les messages de timeout affichent la valeur configurée.
```

---

### Task 2: Compose env — GRPC_TIMEOUT 110 + explicit tunables

**Goal:** embedding-service containers run with the retuned budgets; values self-documented in compose.

**Files:**
- Modify: `docker-compose.yml` (embedding-service service block, env section — currently around line 1006-1017)

**Acceptance Criteria:**
- [ ] `GRPC_TIMEOUT=110` (was 45) with updated comment
- [ ] `PREFETCH_COUNT=2` and `PROCESS_TIMEOUT=240` explicit in env
- [ ] YAML parses

**Verify:** `python -c "import yaml; yaml.safe_load(open('docker-compose.yml', encoding='utf-8')); print('OK')"` → OK

**Steps:**

- [ ] **Step 1: Edit the embedding-service env block**

In `docker-compose.yml`, replace:

```yaml
      - SERVICE_NAME=embedding-service
      # Fail-fast: chaque appel gRPC échoue en DEADLINE_EXCEEDED (retryable) AVANT
      # le timeout global consumer de 120s, au lieu d'être annulé brutalement par lui.
      # Requiert le re-raise de chunk_text (common-utils) — sinon DEADLINE_EXCEEDED
      # sur ChunkText serait avalé en "aucun chunk" => DLQ permanente.
      - GRPC_TIMEOUT=45
```

with:

```yaml
      - SERVICE_NAME=embedding-service
      # Budgets (spec 2026-07-02 livelock) : le deadline gRPC (retryable) part
      # AVANT le plafond global PROCESS_TIMEOUT (> 2x GRPC_TIMEOUT, pire cas
      # ChunkText + GetEmbeddings). 45s coupait dans la bande de complétion des
      # gros payloads (diagnostic files H/M/L quasi vides => temps passé dans le
      # traitement, pas en file). Requiert le re-raise chunk_text (1cc8c203).
      - GRPC_TIMEOUT=110
      - PROCESS_TIMEOUT=240
      # Backpressure : 4 replicas x 2 = 8 en vol contre Semaphore(3) non-HIGH.
      - PREFETCH_COUNT=2
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('docker-compose.yml', encoding='utf-8')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit (bilingual, via temp file)**

```bash
git add docker-compose.yml
git commit --file=<temp file containing the bilingual message below>
```

```text
fix(embedding): retune GRPC_TIMEOUT 45->110 + explicit consumer tunables

EN: 45s sat inside the large-payload completion band (H/M/L queue
diagnostic showed near-empty queues — time is spent processing, not
waiting), so every attempt failed and the 30s retry recycled it
forever. 110 restores completion; PROCESS_TIMEOUT=240 and
PREFETCH_COUNT=2 made explicit in compose.

FR : 45s tombait dans la bande de complétion des gros payloads (le
diagnostic des files H/M/L montre des files quasi vides — le temps part
dans le traitement, pas en attente), donc chaque tentative échouait et
le retry de 30s recyclait à l'infini. 110 restaure la complétion ;
PROCESS_TIMEOUT=240 et PREFETCH_COUNT=2 explicités dans le compose.
```

---

## Deploy (operator-controlled — do NOT push)

1. `git push origin features/poc` (user).
2. VM: rebuild the **embedding-service image only** (consumer.py is bind-mounted but the image default should match; compose env applies at `up`). `docker compose up -d embedding-service` after rebuild.
3. Verify per spec: cancellation-count grep before/after, `/logs/temps_embedding.log` durations (bulk < 110s), `embedding_queue`/`_retry` depths trending down.
4. If duration log shows tails > 110s → open Phase 2 (per-retry timeout ladder) from the spec.
