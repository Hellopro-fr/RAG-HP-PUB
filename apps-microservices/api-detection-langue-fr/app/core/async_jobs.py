"""Async job store + manager for the /detect-batch-async API.

Job state lives in Redis (records + an atomic idempotency index). The worker
runs in-process via asyncio, reusing the batch core injected at construction
(no import of app.api.routes — avoids a cycle). See spec
docs/superpowers/specs/2026-06-01-detection-langue-fr-async-job-api-design.md.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

from common_utils.redis import cache_service

logger = logging.getLogger(__name__)

_JOB_KEY = "detect:job:{}"
_IDX_KEY = "detect:jobidx:{}"


class _JobsDisabled(Exception):
    """ASYNC_JOBS_ENABLED is false (permanent 503, not retryable)."""


class _JobsUnavailable(Exception):
    """Redis unreachable / first write failed / claim_index blew up (transient
    503 WITH Retry-After — a Redis restart is not the permanent kill-switch;
    see _JobsDisabled, which must stay the only header-less 503)."""


class _JobCapacityExceeded(Exception):
    """MAX_ACTIVE_JOBS reached (transient 503 + Retry-After)."""


class JobStore:
    """Redis CRUD for job records + idempotency index.

    Backed by the shared common_utils cache_service pool — main.py's lifespan
    calls init_redis_pool()/close_redis_pool(). The pool client is read live
    at each call so a startup without Redis degrades to 503 on submit.
    `client` overrides the pool (test seam)."""

    def __init__(self, client=None) -> None:
        self._client_override = client

    @property
    def _client(self):
        return self._client_override or cache_service.redis_client

    async def ping(self) -> bool:
        client = self._client
        if not client:
            return False
        try:
            return bool(await client.ping())
        except Exception as e:
            logger.warning(f"[async-jobs] Redis ping failed: {e}")
            return False

    async def claim_index(self, client_job_id: str, job_id: str, ttl: int) -> bool:
        ok = await self._client.set(_IDX_KEY.format(client_job_id), job_id, nx=True, ex=ttl)
        return bool(ok)

    async def get_index(self, client_job_id: str) -> Optional[str]:
        try:
            return await self._client.get(_IDX_KEY.format(client_job_id))
        except Exception:
            return None

    async def delete_index(self, client_job_id: str) -> None:
        try:
            await self._client.delete(_IDX_KEY.format(client_job_id))
        except Exception:
            pass

    async def refresh_index_ttl(self, client_job_id: str, ttl: int) -> None:
        try:
            await self._client.expire(_IDX_KEY.format(client_job_id), ttl)
        except Exception:
            pass

    async def write(self, record: dict, ttl: int) -> None:
        """Write a record. RAISES on failure — the submit path relies on this
        to detect an unreachable Redis (do NOT swallow here)."""
        client = self._client
        if not client:
            raise RuntimeError("Redis client unavailable")
        await client.setex(_JOB_KEY.format(record["job_id"]), ttl, json.dumps(record))

    async def get(self, job_id: str) -> Optional[dict]:
        client = self._client
        if not client:
            return None
        try:
            data = await client.get(_JOB_KEY.format(job_id))
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug(f"[async-jobs] get error: {e}")
            return None


def poll_status(record: dict, now: float, stale_threshold_s: int) -> str:
    """Compute the BO-visible status. 'stale' is derived on read for a
    pending/running record whose heartbeat froze (dead worker). Never mutates."""
    status = record.get("status", "pending")
    if status in ("pending", "running"):
        last = max(record.get("created_at", 0.0), record.get("last_activity", 0.0))
        if (now - last) > stale_threshold_s:
            return "stale"
    return status


from app.models.schemas import BatchItem, BatchOpts, DetectionMode  # noqa: E402


class JobManager:
    def __init__(self, store: JobStore, batch_runner: Callable[..., Awaitable], settings) -> None:
        self._store = store
        self._batch_runner = batch_runner          # _run_batch_core, injected
        self._s = settings
        self._job_tasks: dict[str, asyncio.Task] = {}
        self._inflight = 0                          # reserve counter (sync-guarded)
        # FIFO d'exécution : les jobs soumis attendent qu'un worker les prenne
        # (JOB_WORKER_CONCURRENCY, défaut 1). Avant : create_task immédiat →
        # jusqu'à MAX_ACTIVE_JOBS batchs simultanés sur le même pool de
        # navigateurs → tempêtes de timeouts 300s + admission_rejected.
        # MAX_ACTIVE_JOBS garde son sens exact (pending+running, _inflight).
        self._queue: asyncio.Queue = asyncio.Queue()
        self._queued_ids: set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._keeper: Optional[asyncio.Task] = None
        self._abandoned_ids: set[str] = set()   # jobs decremented by the watchdog (guard _on_done)

    async def get_record(self, job_id: str) -> Optional[dict]:
        return await self._store.get(job_id)

    async def store_ping(self) -> bool:
        """Exception-safe (JobStore.ping) — lets the poll handler tell an
        absent job_id apart from a Redis read failure that JobStore.get()
        degrades to the same None."""
        return await self._store.ping()

    async def _index_target_reusable(self, job_id: str) -> bool:
        """Un index d'idempotence n'est re-servi que si son job est encore
        vivant (pending/running non-stale) ou 'completed' (résultat
        récupérable). failed / stale / record expiré → non réutilisable."""
        rec = await self._store.get(job_id)
        if not rec:
            return False
        status = poll_status(rec, time.time(), self._s.STALE_THRESHOLD_S)
        return status in ("pending", "running", "completed")

    async def submit(self, req) -> tuple[str, int]:
        """Returns (job_id, http_status). http_status is 202 (new) or 200 (existing)."""
        if not self._s.ASYNC_JOBS_ENABLED:
            raise _JobsDisabled()
        if not await self._store.ping():
            raise _JobsUnavailable()

        job_id = uuid.uuid4().hex
        cjid = req.client_job_id

        # Idempotency claim FIRST (atomic SET NX). Existing -> return it, no spawn.
        # try/except : claim_index (contrairement à get_index/delete_index/
        # refresh_index_ttl juste au-dessus) n'attrape pas ses propres
        # exceptions — une panne Redis tombant ici s'échapperait en 500, un
        # code absent de DETECTION_TRANSIENT_CODES côté BO (jette dès la 1re
        # tentative). On la convertit dans le même 503 rejouable que le ping.
        if cjid:
            try:
                claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
                if not claimed:
                    existing = await self._store.get_index(cjid)
                    if existing and await self._index_target_reusable(existing):
                        return existing, 200
                    # Job failed/stale/disparu : le contrat fail-fast dit « le
                    # caller re-soumet » — la re-soumission doit créer un NOUVEAU
                    # job, pas re-servir le cadavre pendant l'heure de TTL d'index
                    # (incident BO 2026-07-26 : relance du même script → poll d'un
                    # job failed → arrêt). 'completed' reste servi tel quel
                    # (idempotence de récupération du résultat).
                    await self._store.delete_index(cjid)
                    claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
                    if not claimed:
                        existing = await self._store.get_index(cjid)
                        return (existing or job_id), 200
            except Exception as e:
                # Nommer l'exception avant de la reconvertir : un `except
                # Exception` générique transforme aussi un VRAI bug (ex. un
                # enregistrement mal formé qui explose dans ce bloc) en 503
                # rejouable — le BO retentera 3x un défaut déterministe sans
                # qu'aucune trace n'existe de la cause réelle.
                logger.warning(f"[async-jobs] claim_index en échec pour client_job_id={cjid}: {e!r}")
                raise _JobsUnavailable()

        # Capacity reserve - synchronous, NO await between check and increment.
        from app.core.metrics import (
            ASYNC_JOB_CAPACITY_REJECTED, ASYNC_JOBS_SUBMITTED, ASYNC_JOBS_ACTIVE,
        )
        if self._inflight >= self._s.MAX_ACTIVE_JOBS:
            if cjid:
                await self._store.delete_index(cjid)
            ASYNC_JOB_CAPACITY_REJECTED.inc()
            raise _JobCapacityExceeded()
        self._inflight += 1

        now = time.time()
        record = {
            "job_id": job_id, "client_job_id": cjid, "status": "pending",
            "total": len(req.items), "done": 0,
            "success_count": 0, "failed_count": 0, "error_count": 0,
            "results": None, "error": None,
            "created_at": now, "started_at": None, "finished_at": None,
            "last_activity": now,
        }
        try:
            await self._store.write(record, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            self._inflight -= 1
            if cjid:
                await self._store.delete_index(cjid)
            raise _JobsUnavailable()

        opts = BatchOpts(
            proxy_url=req.proxy_url, use_nlp_detection=req.use_nlp_detection,
            force_refresh=req.force_refresh, max_concurrency=req.max_concurrency,
            homepage_fallback=req.homepage_fallback,
            validate_alternatives=req.validate_alternatives,
        )
        self._ensure_workers()
        self._queued_ids.add(job_id)
        self._queue.put_nowait((job_id, cjid, list(req.items), req.mode, opts))
        ASYNC_JOBS_SUBMITTED.inc()
        ASYNC_JOBS_ACTIVE.set(self._inflight)
        self._update_queued_gauge()
        return job_id, 202

    def _on_done(self, job_id: str) -> None:
        self._job_tasks.pop(job_id, None)
        if job_id in self._abandoned_ids:
            self._abandoned_ids.discard(job_id)   # already decremented in _abandon_job
            return
        self._inflight = max(0, self._inflight - 1)
        from app.core.metrics import ASYNC_JOBS_ACTIVE
        ASYNC_JOBS_ACTIVE.set(self._inflight)

    async def _abandon_job(self, job_id: str, task: asyncio.Task) -> None:
        """Job exceeded JOB_MAX_S. Free the slot + guard FIRST (no await before this,
        so a naturally-completing zombie's _on_done can't double-decrement), then
        best-effort cancel, then mark failed. We do NOT await the (possibly
        uncancellable) task."""
        from app.core.metrics import ASYNC_JOBS_TERMINAL, ASYNC_JOBS_ACTIVE
        # --- synchronous, race-free: no await between _worker_loop's wait() and here ---
        self._abandoned_ids.add(job_id)        # so a later _on_done skips its decrement
        self._job_tasks.pop(job_id, None)
        self._inflight = max(0, self._inflight - 1)
        ASYNC_JOBS_ACTIVE.set(self._inflight)
        task.cancel()                          # best-effort; cancels a still-cancellable zombie before it can complete
        logger.error(f"[async-jobs] job {job_id} exceeded JOB_MAX_S={getattr(self._s, 'JOB_MAX_S', 1500)}s — failing + abandoning")
        # --- store I/O after the guard; status gate avoids clobbering a completed result ---
        rec = await self._store.get(job_id) or {"job_id": job_id}
        if rec.get("status") not in ("completed", "failed"):
            rec.update({"status": "failed", "error": "job_timeout",
                        "finished_at": time.time(), "last_activity": time.time()})
            try:
                await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
            except Exception:
                pass
            ASYNC_JOBS_TERMINAL.labels(status="failed").inc()

    def _update_queued_gauge(self) -> None:
        from app.core.metrics import ASYNC_JOBS_QUEUED
        ASYNC_JOBS_QUEUED.set(len(self._queued_ids))

    def _ensure_workers(self) -> None:
        """Lazy spawn (première soumission) : évite de créer des tâches au
        constructeur, appelé hors event loop dans certains tests."""
        if self._workers:
            return
        n = max(1, int(getattr(self._s, "JOB_WORKER_CONCURRENCY", 1)))
        self._workers = [
            asyncio.create_task(self._worker_loop(i)) for i in range(n)
        ]
        self._keeper = asyncio.create_task(self._queued_keeper_loop())

    async def _worker_loop(self, worker_idx: int) -> None:
        while True:
            job_id, cjid, items, mode, opts = await self._queue.get()
            if job_id not in self._queued_ids:
                continue  # drainé par shutdown() entre put et pickup
            self._queued_ids.discard(job_id)
            self._update_queued_gauge()
            # Log défensif : une erreur Redis ici ne doit JAMAIS tuer le worker
            # (worker mort = file gelée sans erreur visible).
            try:
                rec = await self._store.get(job_id)
                queued_s = round(time.time() - rec.get("created_at", time.time()), 1) if rec else 0
            except Exception:
                queued_s = -1
            logger.info(f"[async-jobs] worker#{worker_idx} picked job {job_id} (queued {queued_s}s)")
            task = asyncio.create_task(self._run_job(job_id, cjid, items, mode, opts))
            self._job_tasks[job_id] = task
            task.add_done_callback(lambda t, jid=job_id: self._on_done(jid))
            # wait() : n'importe ni l'exception du job (gérée dans _run_job) ni
            # son annulation ; l'annulation du worker lui-même interrompt le wait.
            done, _pending = await asyncio.wait({task}, timeout=getattr(self._s, "JOB_MAX_S", 1500))
            if not done:
                await self._abandon_job(job_id, task)

    async def _queued_keeper_loop(self) -> None:
        """Heartbeat des jobs EN FILE : sans lui, un job sain en attente >
        STALE_THRESHOLD_S serait vu 'stale' par le poll (le BO le croirait
        mort et re-soumettrait). Un process réellement mort n'a plus de
        keeper → stale surface normalement après restart."""
        try:
            while True:
                await asyncio.sleep(self._s.HEARTBEAT_INTERVAL_S)
                for job_id in list(self._queued_ids):
                    rec = await self._store.get(job_id)
                    if not rec or rec.get("status") != "pending":
                        continue
                    # Re-check APRÈS le get : si le worker a pris le job pendant
                    # l'await, ne pas réécrire la copie 'pending' périmée
                    # par-dessus son écriture 'running'. Fenêtre résiduelle
                    # (réordonnancement réseau pendant le write) : cosmétique —
                    # le heartbeat du job ré-affirme 'running' au tick suivant
                    # et les écritures terminales gagnent toujours.
                    if job_id not in self._queued_ids:
                        continue
                    rec["last_activity"] = time.time()
                    try:
                        await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            return

    async def _heartbeat(self, job_id: str, progress: dict, stop: asyncio.Event) -> None:
        try:
            while True:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=self._s.HEARTBEAT_INTERVAL_S
                    )
                    return  # arrêt coopératif — jamais interrompu mi-commande Redis
                except asyncio.TimeoutError:
                    pass  # tick normal
                rec = await self._store.get(job_id)
                if not rec or rec.get("status") not in ("pending", "running"):
                    return
                rec["done"] = progress["done"]
                # Ce heartbeat ne tourne que pendant _run_job : ré-affirmer
                # 'running' auto-répare une éventuelle écriture 'pending'
                # périmée du keeper de file (course bénigne, cf. keeper).
                rec["status"] = "running"
                rec["last_activity"] = time.time()
                try:
                    await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
                except Exception:
                    pass
        except asyncio.CancelledError:
            return

    async def _stop_heartbeat(self, hb: asyncio.Task, stop: asyncio.Event) -> None:
        """Arrêt coopératif du heartbeat. hb.cancel() pouvait tomber au milieu
        d'une commande Redis et laisser la connexion du pool avec une réponse
        en attente — les get/write TERMINAUX suivants réutilisaient cette
        connexion et échouaient en silence, laissant le record bloqué
        'running' (job 9597267b, 2026-07-26 : batch fini 5/5 OK, résultat
        perdu). L'Event laisse le tick en cours finir sa commande proprement."""
        stop.set()
        try:
            # Borne : un tick complet = attente (INTERVAL) + get + write
            # (2 × socket timeout Redis 10s par défaut).
            await asyncio.wait_for(hb, timeout=self._s.HEARTBEAT_INTERVAL_S + 25)
        except asyncio.TimeoutError:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)

    def _terminal_write_budget(self, started_mono: float) -> float:
        """Clamp le budget de retry de l'écriture terminale au reliquat de
        JOB_MAX_S. `_worker_loop` attend le job avec `asyncio.wait(timeout=
        JOB_MAX_S)` à partir du même instant que `started_mono` (création de
        la task _run_job) ; une écriture terminale encore en train de
        réessayer quand ce délai expire se fait annuler par `_abandon_job`,
        qui écrase un lot pourtant terminé en `failed(job_timeout)` — pire
        que le `running` silencieux que ce retry existe pour éviter. D'où un
        `min` avec le reliquat, jamais un budget nu.

        `started_mono` DOIT être `time.monotonic()`, pas `time.time()` : le
        budget se compare au compte à rebours de `asyncio.wait(timeout=...)`,
        qui arme sur l'horloge monotone de la boucle — un saut d'horloge
        murale (NTP) gonflerait `remaining` dans le sens dangereux avec
        `time.time()`.

        LIMITE CONNUE (revue 2026-08-11) : ce budget ne borne QUE les
        RE-tentatives — il décide si une nouvelle attente puis un nouvel
        essai démarrent, jamais l'essai déjà en vol. Le pool partagé
        (`common_utils/redis/cache_service.py`) enrobe chaque commande dans
        son propre `Retry(ExponentialBackoff(cap=1.0), 3)` par-dessus
        `socket_timeout=10s` — un seul appel à `write()` peut donc bloquer
        plusieurs dizaines de secondes. Un budget clampé à quelques secondes
        peut donc quand même rendre après JOB_MAX_S, laisser le watchdog de
        `_worker_loop` se déclencher pendant ce temps, et `_abandon_job`
        écraser un lot pourtant terminé — exactement le dommage que ce clamp
        existe pour éviter. Strictement mieux qu'avant (aucun clamp), mais
        PAS fermé. Ne PAS enrober l'écriture dans `wait_for` pour fermer ça :
        annuler en pleine commande empoisonnerait la connexion du pool, le
        même mode de panne déjà documenté plus haut pour `_stop_heartbeat`."""
        remaining = self._s.JOB_MAX_S - (time.monotonic() - started_mono)
        return min(self._s.TERMINAL_WRITE_BUDGET_S, max(0.0, remaining))

    async def _write_terminal(self, rec: dict, cjid: Optional[str], budget_s: float) -> bool:
        """Écriture du record terminal = tout le travail du batch. Réessayée
        à échéance (deadline, backoff plafonné 0.5/1/2/4/8/8/…) plutôt qu'un
        compte fixe de tentatives : 3 tentatives à backoff fixe s'épuisaient
        en ~3.6s, pas assez pour survivre à un redémarrage Redis (le mode de
        panne ordinaire que ce garde cible). La perdre en silence (ancien
        `except: pass`) laissait un job pourtant réussi bloqué 'running' →
        'stale' au poll → le BO jetait le batch entier. `budget_s` est déjà
        clampé par l'appelant (`_terminal_write_budget`) au reliquat de
        JOB_MAX_S — ne PAS relire self._s.JOB_MAX_S ici, la fenêtre a pu déjà
        se réduire pendant l'attente du heartbeat avant cet appel."""
        deadline = time.monotonic() + budget_s
        last_err: Optional[Exception] = None
        attempt = 0
        backoff = 0.5
        while True:
            attempt += 1
            try:
                await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                if cjid:
                    await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
                return True
            except Exception as e:
                last_err = e
                logger.warning(
                    f"[async-jobs] écriture terminale {rec.get('job_id')} "
                    f"tentative {attempt} échouée: {e}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(backoff, remaining))
            backoff = min(backoff * 2, 8)
        logger.error(
            f"[async-jobs] écriture terminale PERDUE pour {rec.get('job_id')} "
            f"(status={rec.get('status')}): {last_err} — le record restera sur "
            f"sa dernière copie heartbeat jusqu'à stale/TTL"
        )
        return False

    async def _run_job(self, job_id, cjid, items, mode, opts) -> None:
        from app.core.metrics import ASYNC_JOBS_TERMINAL, ASYNC_JOB_DURATION
        progress = {"done": 0}
        started = time.time()
        # Base séparée pour le clamp de _terminal_write_budget : le watchdog
        # de _worker_loop (asyncio.wait(timeout=JOB_MAX_S)) arme sur
        # l'horloge monotone au même instant que la création de cette task —
        # started_mono suit exactement ce compte à rebours, pas une horloge
        # murale qu'un saut NTP peut fausser (revue 2026-08-11).
        started_mono = time.monotonic()
        rec = await self._store.get(job_id) or {"job_id": job_id}
        rec.update({"status": "running", "started_at": started, "last_activity": started})
        try:
            await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            pass

        stop_hb = asyncio.Event()
        hb = asyncio.create_task(self._heartbeat(job_id, progress, stop_hb))
        try:
            results, counts = await self._batch_runner(
                items, mode, opts, lambda done: progress.__setitem__("done", done)
            )
            await self._stop_heartbeat(hb, stop_hb)
            rec = await self._store.get(job_id) or rec
            rec.update({
                "status": "completed", "done": len(results),
                "success_count": counts.success_count,
                "failed_count": counts.failed_count,
                "error_count": counts.error_count,
                "results": [r.model_dump() for r in results],
                "finished_at": time.time(), "last_activity": time.time(),
            })
            wrote = await self._write_terminal(rec, cjid, self._terminal_write_budget(started_mono))
            ASYNC_JOBS_TERMINAL.labels(status="completed" if wrote else "lost").inc()
            ASYNC_JOB_DURATION.observe(time.time() - started)
            logger.info(
                f"[async-jobs] job {job_id} completed: {counts.success_count} ok, "
                f"{counts.failed_count} non-FR, {counts.error_count} err "
                f"({round(time.time() - started, 1)}s)"
            )
        except asyncio.CancelledError:
            hb.cancel()   # teardown rapide — process en train de mourir
            raise                                   # shutdown() owns the record write
        except Exception as e:
            await self._stop_heartbeat(hb, stop_hb)
            rec = await self._store.get(job_id) or rec
            rec.update({"status": "failed", "error": str(e),
                        "finished_at": time.time(), "last_activity": time.time()})
            wrote = await self._write_terminal(rec, cjid, self._terminal_write_budget(started_mono))
            ASYNC_JOBS_TERMINAL.labels(status="failed" if wrote else "lost").inc()
            logger.error(f"[async-jobs] job {job_id} failed: {e}")

    async def shutdown(self) -> None:
        # 1. Stopper keeper + workers d'abord : rien de nouveau ne démarre.
        infra = [t for t in (self._keeper, *self._workers) if t is not None]
        for t in infra:
            t.cancel()
        if infra:
            await asyncio.gather(*infra, return_exceptions=True)
        self._workers = []
        self._keeper = None

        # 2. Drainer la file : jobs jamais démarrés → failed(service_shutdown)
        # (contrat fail-fast : le caller re-soumet, cf. spec 2026-06-01).
        drained_ids = list(self._queued_ids)
        self._queued_ids.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._update_queued_gauge()

        # 3. Jobs en cours : cancel + marquage (comportement historique).
        job_ids = list(self._job_tasks.keys())
        tasks = list(self._job_tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=self._s.SHUTDOWN_GRACE_S)
        for job_id in (*drained_ids, *job_ids):
            rec = await self._store.get(job_id)
            if rec and rec.get("status") in ("pending", "running"):
                rec.update({"status": "failed", "error": "service_shutdown",
                            "finished_at": time.time()})
                try:
                    await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                except Exception:
                    pass
        # _inflight, deux chemins disjoints : les jobs DÉMARRÉS passent par le
        # done-callback _on_done (décrément à l'annulation ci-dessus) ; les
        # jobs DRAINÉS n'ont jamais eu de task → _on_done ne tirera jamais →
        # décrément manuel ici. Pas de double comptage possible.
        self._inflight = max(0, self._inflight - len(drained_ids))
        from app.core.metrics import ASYNC_JOBS_ACTIVE
        ASYNC_JOBS_ACTIVE.set(self._inflight)
