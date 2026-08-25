import asyncio
import time
import types
import pytest

import app.core.async_jobs as async_jobs
from app.core.async_jobs import (
    JobManager, JobStore, _JobCapacityExceeded, _JobsDisabled, _JobsUnavailable, poll_status,
)
from app.models.schemas import BatchItem, BatchCounts, DetectionResponse, DetectionMode
from tests.test_async_jobs import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2, JOB_WORKER_CONCURRENCY=1,
                JOB_MAX_S=1500, TERMINAL_WRITE_BUDGET_S=60)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None):
    return types.SimpleNamespace(
        items=[BatchItem(url=u) for u in items], mode=DetectionMode.COMPLETE,
        proxy_url=None, use_nlp_detection=True, force_refresh=False,
        max_concurrency=10, homepage_fallback=True, client_job_id=client_job_id,
        validate_alternatives=True,
    )


async def _instant_runner(items, mode, opts, cb, deadline_monotonic=None):
    cb(len(items))
    results = [DetectionResponse(ok=True, url=i.url, method="test") for i in items]
    return results, BatchCounts(success_count=len(items), failed_count=0, error_count=0)


async def _wait_terminal(jm, job_id, timeout=5.0):
    """Avec la file FIFO, la task du job n'existe pas forcément encore au retour
    de submit — attendre le statut terminal via le store (pas via _job_tasks)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rec = await jm.get_record(job_id)
        if rec and rec.get("status") in ("completed", "failed"):
            return rec
        await asyncio.sleep(0.01)
    raise AssertionError(f"job {job_id} not terminal within {timeout}s")


@pytest.mark.asyncio
async def test_submit_completes_with_authoritative_counts():
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner, _settings())
    job_id, code = await jm.submit(_req(["https://a.fr", "https://b.fr"]))
    assert code == 202
    rec = await _wait_terminal(jm, job_id)
    assert rec["status"] == "completed" and rec["success_count"] == 2 and rec["done"] == 2
    await jm.shutdown()


@pytest.mark.asyncio
async def test_idempotent_concurrent_submit_spawns_once():
    store = JobStore(client=FakeRedis())
    spawns = {"n": 0}
    async def counting_runner(items, mode, opts, cb, deadline_monotonic=None):
        spawns["n"] += 1
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(store, counting_runner, _settings())
    (id1, _), (id2, _) = await asyncio.gather(
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
    )
    assert id1 == id2
    await _wait_terminal(jm, id1)
    assert spawns["n"] == 1
    await jm.shutdown()


@pytest.mark.asyncio
async def test_capacity_rejected_counts_pending_plus_running():
    """MAX_ACTIVE_JOBS borne pending+running : un job encore EN FILE compte."""
    gate = asyncio.Event()
    async def gated_runner(items, mode, opts, cb, deadline_monotonic=None):
        await gate.wait()
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(JobStore(client=FakeRedis()), gated_runner, _settings(MAX_ACTIVE_JOBS=1))
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    with pytest.raises(_JobCapacityExceeded):
        await jm.submit(_req(["https://b.fr"]))
    gate.set()
    await _wait_terminal(jm, job_id)
    await jm.shutdown()


@pytest.mark.asyncio
async def test_disabled():
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner, _settings(ASYNC_JOBS_ENABLED=False))
    with pytest.raises(_JobsDisabled):
        await jm.submit(_req(["https://a.fr"]))


class _ClaimBoomStore(JobStore):
    """claim_index blows up — reproduces the LIVE path: every BO caller sets
    client_job_id, so the `if cjid:` block is not a corner case."""

    async def claim_index(self, client_job_id: str, job_id: str, ttl: int) -> bool:
        raise ConnectionError("claim_index boom")


@pytest.mark.asyncio
async def test_submit_claim_index_failure_is_retryable(caplog):
    """R1 review finding 3+4: the claim_index try/except in submit() has a
    production path with every real caller (client_job_id always set) — a
    blowup there must surface as the same retryable _JobsUnavailable as a
    ping failure, and must log the real exception (finding 4: a bare
    `except Exception: raise` would also silently swallow a genuine bug)."""
    import logging as _logging
    jm = JobManager(_ClaimBoomStore(client=FakeRedis()), _instant_runner, _settings())
    with caplog.at_level(_logging.WARNING, logger="app.core.async_jobs"):
        with pytest.raises(_JobsUnavailable):
            await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    assert any("claim_index" in r.message and "K" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_shutdown_marks_running_failed():
    started = asyncio.Event()
    async def hang_runner(items, mode, opts, cb, deadline_monotonic=None):
        started.set()
        await asyncio.sleep(60)
    jm = JobManager(JobStore(client=FakeRedis()), hang_runner, _settings())
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    await started.wait()
    await jm.shutdown()
    rec = await jm.get_record(job_id)
    assert rec["status"] == "failed" and rec["error"] == "service_shutdown"


# ─── File FIFO + worker pool (spec 2026-07-19) ────────────────────────────────

@pytest.mark.asyncio
async def test_jobs_run_serially_in_fifo_order():
    """JOB_WORKER_CONCURRENCY=1 : jamais 2 batches simultanés, ordre FIFO."""
    running = {"now": 0, "max": 0}
    order = []
    async def tracking_runner(items, mode, opts, cb, deadline_monotonic=None):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        order.append(items[0].url)
        await asyncio.sleep(0.03)
        running["now"] -= 1
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(JobStore(client=FakeRedis()), tracking_runner, _settings(MAX_ACTIVE_JOBS=8))
    urls = ["https://a.fr", "https://b.fr", "https://c.fr"]
    ids = []
    for u in urls:
        jid, code = await jm.submit(_req([u]))
        assert code == 202
        ids.append(jid)
    for jid in ids:
        await _wait_terminal(jm, jid)
    assert running["max"] == 1
    assert order == urls
    await jm.shutdown()


@pytest.mark.asyncio
async def test_worker_concurrency_two_runs_two_jobs():
    gate = asyncio.Event()
    running = {"now": 0, "max": 0}
    async def gated_runner(items, mode, opts, cb, deadline_monotonic=None):
        running["now"] += 1
        running["max"] = max(running["max"], running["now"])
        await gate.wait()
        running["now"] -= 1
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(
        JobStore(client=FakeRedis()), gated_runner,
        _settings(JOB_WORKER_CONCURRENCY=2, MAX_ACTIVE_JOBS=8),
    )
    ids = []
    for u in ("https://a.fr", "https://b.fr", "https://c.fr"):
        jid, _ = await jm.submit(_req([u]))
        ids.append(jid)
    deadline = time.monotonic() + 2.0
    while running["now"] < 2 and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert running["now"] == 2, "2 workers doivent exécuter 2 jobs en parallèle"
    gate.set()
    for jid in ids:
        await _wait_terminal(jm, jid)
    assert running["max"] == 2  # jamais 3 : le 3e job attend un worker
    await jm.shutdown()


@pytest.mark.asyncio
async def test_queued_job_heartbeat_prevents_false_stale():
    """Un job EN FILE reste 'pending' au poll : le keeper rafraîchit
    last_activity, sinon il passerait 'stale' après STALE_THRESHOLD_S et le
    BO le croirait mort (re-soumission en double)."""
    gate = asyncio.Event()
    started = asyncio.Event()
    async def blocking_runner(items, mode, opts, cb, deadline_monotonic=None):
        started.set()
        await gate.wait()
        return await _instant_runner(items, mode, opts, cb)
    s = _settings(HEARTBEAT_INTERVAL_S=0.05, MAX_ACTIVE_JOBS=8)
    jm = JobManager(JobStore(client=FakeRedis()), blocking_runner, s)
    id_running, _ = await jm.submit(_req(["https://a.fr"]))
    await started.wait()
    id_queued, _ = await jm.submit(_req(["https://b.fr"]))

    rec0 = await jm.get_record(id_queued)
    assert rec0["status"] == "pending"
    la0 = rec0["last_activity"]

    await asyncio.sleep(0.15)  # >= 2 ticks keeper

    rec1 = await jm.get_record(id_queued)
    assert rec1["status"] == "pending"
    assert rec1["last_activity"] > la0, "le keeper doit rafraîchir last_activity"
    # Même avec un created_at « vieux », le poll ne dérive pas 'stale'.
    assert poll_status(rec1, time.time(), stale_threshold_s=120) == "pending"

    gate.set()
    await _wait_terminal(jm, id_running)
    await _wait_terminal(jm, id_queued)
    await jm.shutdown()


@pytest.mark.asyncio
async def test_shutdown_marks_queued_job_failed():
    """Un job jamais démarré (encore en file) est marqué failed(service_shutdown)
    au shutdown — contrat fail-fast : le caller re-soumet."""
    started = asyncio.Event()
    async def hang_runner(items, mode, opts, cb, deadline_monotonic=None):
        started.set()
        await asyncio.sleep(60)
    jm = JobManager(JobStore(client=FakeRedis()), hang_runner, _settings(MAX_ACTIVE_JOBS=8))
    id_running, _ = await jm.submit(_req(["https://a.fr"]))
    await started.wait()
    id_queued, _ = await jm.submit(_req(["https://b.fr"]))

    await jm.shutdown()

    rec_q = await jm.get_record(id_queued)
    assert rec_q["status"] == "failed" and rec_q["error"] == "service_shutdown"
    rec_r = await jm.get_record(id_running)
    assert rec_r["status"] == "failed" and rec_r["error"] == "service_shutdown"
    # Les réservations drainées sont libérées (pas de fuite de capacité).
    assert jm._inflight == 0


@pytest.mark.asyncio
async def test_resubmit_after_failed_creates_new_job():
    """Incident BO 2026-07-26 : client_job_id déterministe + job failed →
    la re-soumission re-servait le cadavre pendant 1h d'index TTL. La
    re-soumission d'un cjid dont le job est failed doit créer un NOUVEAU job."""
    calls = {"n": 0}

    async def fail_then_ok(items, mode, opts, cb, deadline_monotonic=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return await _instant_runner(items, mode, opts, cb)

    jm = JobManager(JobStore(client=FakeRedis()), fail_then_ok, _settings())
    id1, code1 = await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    assert code1 == 202
    rec1 = await _wait_terminal(jm, id1)
    assert rec1["status"] == "failed"

    id2, code2 = await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    assert code2 == 202 and id2 != id1
    rec2 = await _wait_terminal(jm, id2)
    assert rec2["status"] == "completed"
    await jm.shutdown()


@pytest.mark.asyncio
async def test_resubmit_after_completed_returns_same_job():
    """Idempotence de récupération du résultat : cjid d'un job completed
    re-soumis dans la fenêtre RESULT_TTL → même job, 200."""
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner, _settings())
    id1, _ = await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    await _wait_terminal(jm, id1)
    id2, code2 = await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    assert (id2, code2) == (id1, 200)
    await jm.shutdown()


@pytest.mark.asyncio
async def test_resubmit_on_stale_record_creates_new_job():
    """Index pointant vers un record running au heartbeat gelé (stale dérivé)
    → re-soumission = nouveau job (le job gelé est mort, cf. fail-fast)."""
    store = JobStore(client=FakeRedis())
    jm = JobManager(store, _instant_runner, _settings())
    old = time.time() - 1000
    await store.write({"job_id": "dead1", "status": "running",
                       "created_at": old, "last_activity": old}, 7200)
    await store.claim_index("K", "dead1", 7200)

    job_id, code = await jm.submit(_req(["https://a.fr"], client_job_id="K"))
    assert code == 202 and job_id != "dead1"
    rec = await _wait_terminal(jm, job_id)
    assert rec["status"] == "completed"
    await jm.shutdown()


class _FlakyTerminalStore(JobStore):
    """Fait échouer les N premières écritures TERMINALES (status completed/
    failed) — reproduit le job 9597267b : batch fini, écriture du résultat
    perdue, record bloqué 'running'."""

    def __init__(self, client, fail_n: int):
        super().__init__(client=client)
        self.fail_left = fail_n
        self.terminal_attempts = 0

    async def write(self, record, ttl):
        if record.get("status") in ("completed", "failed"):
            self.terminal_attempts += 1
            if self.fail_left > 0:
                self.fail_left -= 1
                raise ConnectionError("terminal write boom")
        await super().write(record, ttl)


@pytest.mark.asyncio
async def test_terminal_write_retried_until_success():
    """2 échecs d'écriture terminale → le retry aboutit, le job finit
    'completed' avec ses résultats (avant : record bloqué 'running')."""
    store = _FlakyTerminalStore(FakeRedis(), fail_n=2)
    jm = JobManager(store, _instant_runner, _settings())
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    rec = await _wait_terminal(jm, job_id, timeout=8.0)
    assert rec["status"] == "completed"
    assert rec["results"] is not None and len(rec["results"]) == 1
    assert store.terminal_attempts == 3
    await jm.shutdown()


@pytest.mark.asyncio
async def test_terminal_write_survives_past_three_fixed_attempts(monkeypatch):
    """R3 defect: the old loop was a FIXED 3 attempts (~1.5s of sleep total,
    ~3.6s wall including the writes themselves) regardless of how much budget
    was actually available — nowhere near enough to survive a fast-fail Redis
    restart. A write that fails 4 times before succeeding on the 5th must
    still land, proving the retry now honours the configured budget, not a
    hardcoded attempt count.

    Calls _write_terminal DIRECTLY (no submit()/worker task) with asyncio.sleep
    patched to a no-op — same idiom as tests/test_variant_gate.py. This is
    cost, not correctness: the real 0.5/1/2/4/8s backoff schedule is already
    exercised at real speed by the untouched test_terminal_write_retried_until_success
    (~1.5s); this one only needs to prove the loop doesn't hard-stop at 3.
    Calling the method directly (vs. going through submit()) also means
    there is no separate task for a real sleep to yield control to in the
    first place — patching it here can't starve a sibling task, because
    there is no sibling task in this test."""
    async def _no_sleep(_seconds):
        return None
    monkeypatch.setattr(async_jobs.asyncio, "sleep", _no_sleep)
    store = _FlakyTerminalStore(FakeRedis(), fail_n=4)
    jm = JobManager(store, _instant_runner, _settings())
    wrote = await jm._write_terminal({"job_id": "x", "status": "completed"}, None, budget_s=5.0)
    assert wrote is True
    assert store.terminal_attempts == 5


@pytest.mark.asyncio
async def test_terminal_write_budget_clamped_to_job_max_s_remainder():
    """R3 central risk: _write_terminal must NEVER retry longer than what's
    left of JOB_MAX_S. _worker_loop's asyncio.wait(timeout=JOB_MAX_S) races
    the same clock as _run_job's `started_mono` — a write still retrying when
    that fires gets cancelled by _abandon_job, which overwrites a COMPLETED
    batch with failed(job_timeout): worse than the stale 'running' this retry
    loop exists to avoid. Pure unit on the clamp helper: JOB_MAX_S=10 with 7s
    already elapsed leaves only 3s, well under the configured 60s budget.

    Uses time.monotonic() (review 2026-08-11): the helper now takes a
    monotonic basis to match asyncio.wait's own clock, not time.time()."""
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner, _settings(JOB_MAX_S=10))
    started_mono = time.monotonic() - 7
    budget = jm._terminal_write_budget(started_mono)
    assert 0 < budget <= 3.5, f"expected ~3s (10 - 7 elapsed), got {budget}"

    # Job already past JOB_MAX_S (should not happen in practice — the
    # watchdog would have fired — but the clamp must degrade to "try once,
    # give up fast" rather than a negative/blocking budget).
    started_over = time.monotonic() - 999
    assert jm._terminal_write_budget(started_over) == 0.0


@pytest.mark.asyncio
async def test_terminal_write_lost_is_loud(caplog):
    """Écriture terminale définitivement perdue : plus de `except: pass`
    silencieux — un logger.error nomme le job et l'état résiduel.

    TERMINAL_WRITE_BUDGET_S=2 : le retry est maintenant à échéance (R3), pas à
    3 tentatives fixes — sans un petit budget explicite, ce test (qui échoue
    à l'infini) dormirait le budget par défaut (60s) en temps réel."""
    import logging as _logging
    store = _FlakyTerminalStore(FakeRedis(), fail_n=99)
    jm = JobManager(store, _instant_runner, _settings(TERMINAL_WRITE_BUDGET_S=2))
    def _lost_logged():
        return any("écriture terminale PERDUE" in r.message for r in caplog.records)

    with caplog.at_level(_logging.ERROR, logger="app.core.async_jobs"):
        job_id, _ = await jm.submit(_req(["https://a.fr"]))
        deadline = time.monotonic() + 8.0
        while not _lost_logged() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
    assert store.terminal_attempts >= 3
    rec = await jm.get_record(job_id)
    assert rec["status"] == "running"   # dégradé documenté → 'stale' au poll
    assert _lost_logged()
    await jm.shutdown()


@pytest.mark.asyncio
async def test_terminal_write_budget_actually_wired_to_job_max_s():
    """Review finding 5, round 2 (2026-08-11): the first version of this test
    raced two live timers on one outcome. JOB_MAX_S=1 clamps the retry budget
    to ~1s, and a PERMANENTLY-failing store means _write_terminal's own
    deadline ALSO expires around that same ~1s mark — so `_worker_loop`'s
    watchdog (`asyncio.wait(timeout=JOB_MAX_S)`, armed the instant the task
    is created) and `_write_terminal`'s internal deadline (armed off the same
    clock, `started_mono`) were both live at ~1s, and whichever fired first
    decided whether `_abandon_job` cancelled the task before PERDUE could be
    logged. Scheduling jitter, not the code, decided the assertion — flaky by
    construction (confirmed: alone it failed, in the full file it passed).

    Fixed by removing the second timer instead of racing it: use a HEALTHY
    store, so _write_terminal returns True on its very FIRST attempt, well
    under any deadline — the retry loop's own clock never gets close to
    expiring, so `_worker_loop`'s 1s watchdog has nothing to race (the job
    finishes in the same event-loop tick, µs-scale, versus a 1s timeout).
    With no second timer live, the property is asserted as a plain captured
    fact instead of a stopwatch: spy on _write_terminal and read the budget_s
    _run_job actually passed it. JOB_MAX_S=1 + TERMINAL_WRITE_BUDGET_S=60
    must yield a budget close to 1s (the clamp winning), not 60 (the
    regression this guards against — a bare TERMINAL_WRITE_BUDGET_S)."""
    captured = {}
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner,
                    _settings(JOB_MAX_S=1, TERMINAL_WRITE_BUDGET_S=60))
    real_write_terminal = jm._write_terminal

    async def _spy(rec, cjid, budget_s):
        captured["budget_s"] = budget_s
        return await real_write_terminal(rec, cjid, budget_s)

    jm._write_terminal = _spy
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    rec = await _wait_terminal(jm, job_id, timeout=5.0)
    assert rec["status"] == "completed"
    assert 0 < captured["budget_s"] <= 1.0, (
        f"expected a budget close to 1s (JOB_MAX_S clamp), got "
        f"{captured['budget_s']} — looks like a bare TERMINAL_WRITE_BUDGET_S"
    )
    await jm.shutdown()


@pytest.mark.asyncio
async def test_heartbeat_stops_cooperatively_without_cancel():
    """Le heartbeat s'arrête via l'Event (fin propre de sa commande Redis en
    cours), PAS par annulation — hb.cancel() mi-commande pouvait empoisonner
    la connexion du pool réutilisée par l'écriture terminale."""
    jm = JobManager(JobStore(client=FakeRedis()), _instant_runner, _settings())
    stop = asyncio.Event()
    hb = asyncio.create_task(jm._heartbeat("nonexistent", {"done": 0}, stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(hb, timeout=2.0)
    assert hb.cancelled() is False
