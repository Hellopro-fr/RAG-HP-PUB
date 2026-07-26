import asyncio
import time
import types
import pytest

from app.core.async_jobs import (
    JobManager, JobStore, _JobCapacityExceeded, _JobsDisabled, poll_status,
)
from app.models.schemas import BatchItem, BatchCounts, DetectionResponse, DetectionMode
from tests.test_async_jobs import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2, JOB_WORKER_CONCURRENCY=1)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None):
    return types.SimpleNamespace(
        items=[BatchItem(url=u) for u in items], mode=DetectionMode.COMPLETE,
        proxy_url=None, use_nlp_detection=True, force_refresh=False,
        max_concurrency=10, homepage_fallback=True, client_job_id=client_job_id,
        validate_alternatives=True,
    )


async def _instant_runner(items, mode, opts, cb):
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
    async def counting_runner(items, mode, opts, cb):
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
    async def gated_runner(items, mode, opts, cb):
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


@pytest.mark.asyncio
async def test_shutdown_marks_running_failed():
    started = asyncio.Event()
    async def hang_runner(items, mode, opts, cb):
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
    async def tracking_runner(items, mode, opts, cb):
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
    async def gated_runner(items, mode, opts, cb):
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
    async def blocking_runner(items, mode, opts, cb):
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
    async def hang_runner(items, mode, opts, cb):
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
async def test_terminal_write_lost_is_loud(caplog):
    """Écriture terminale définitivement perdue : plus de `except: pass`
    silencieux — un logger.error nomme le job et l'état résiduel."""
    import logging as _logging
    store = _FlakyTerminalStore(FakeRedis(), fail_n=99)
    jm = JobManager(store, _instant_runner, _settings())
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
