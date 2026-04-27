"""Manager de jobs async in-memory pour DELETE album entier (long-running)."""

import asyncio
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# In-memory registry: { job_id: { ... } }
# Re-entrant safe car FastAPI single-process.
_registry: dict[str, dict] = {}
_active_by_domain: dict[str, str] = {}


def reset_jobs() -> None:
    """Reset complet du registry (tests uniquement)."""
    _registry.clear()
    _active_by_domain.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _estimate_products(storage_base: str, domain: str) -> int:
    import json
    p = os.path.join(storage_base, "images", domain, "manifest.json")
    if not os.path.exists(p):
        return 0
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        return len((data or {}).get("products") or [])
    except Exception:
        return 0


async def _run_delete(job_id: str, storage_base: str, domain: str) -> None:
    job = _registry[job_id]
    job["status"] = "running"
    domain_dir = os.path.join(storage_base, "images", domain)
    try:
        await asyncio.to_thread(_delete_domain_dir, domain_dir, job)
        job["status"] = "completed"
        job["finished_at"] = _now_iso()
        job["finished_at_monotonic"] = time.monotonic()
    except Exception as e:
        logger.exception(f"Job {job_id} échec")
        job["status"] = "failed"
        job["error"] = str(e)
        job["finished_at"] = _now_iso()
        job["finished_at_monotonic"] = time.monotonic()
    finally:
        _active_by_domain.pop(domain, None)


def _delete_domain_dir(domain_dir: str, job: dict) -> None:
    if not os.path.exists(domain_dir):
        raise FileNotFoundError(domain_dir)
    # Comptage approximatif de la progression : on supprime produit par produit
    # via shutil.rmtree global. Pour V1 on accepte une progression discrète (0%/100%).
    shutil.rmtree(domain_dir)
    job["progress"] = {"products_done": job["estimated_products"],
                       "products_total": job["estimated_products"]}


def start_delete_album_job(storage_base: str, domain: str) -> dict:
    """Idempotent par domaine : si un job actif existe, on le renvoie."""
    if domain in _active_by_domain:
        existing_id = _active_by_domain[domain]
        return _public_view(_registry[existing_id])

    job_id = "del_" + uuid.uuid4().hex[:10]
    estimated = _estimate_products(storage_base, domain)
    job = {
        "job_id": job_id,
        "status": "queued",
        "domain": domain,
        "estimated_products": estimated,
        "progress": {"products_done": 0, "products_total": estimated},
        "started_at": _now_iso(),
        "finished_at": None,
        "finished_at_monotonic": None,
        "error": None,
    }
    _registry[job_id] = job
    _active_by_domain[domain] = job_id
    _schedule_run(job_id, storage_base, domain)
    return _public_view(job)


def _schedule_run(job_id: str, storage_base: str, domain: str) -> None:
    """Programme `_run_delete` sur la loop courante si elle existe ;
    sinon, démarre un thread autonome avec sa propre loop (cas tests).

    En prod (FastAPI), `start_delete_album_job` est appelé depuis un
    handler async → la branche `create_task` est prise. En tests sync,
    on retombe sur le thread+loop dédié pour éviter `RuntimeError: no running event loop`.
    """
    coro_factory = lambda: _run_delete(job_id, storage_base, domain)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro_factory())
        return
    except RuntimeError:
        pass

    def _runner():
        asyncio.run(coro_factory())

    t = threading.Thread(target=_runner, name=f"album-job-{job_id}", daemon=True)
    t.start()


def get_job(job_id: str) -> dict | None:
    job = _registry.get(job_id)
    if not job:
        return None
    return _public_view(job)


def _public_view(job: dict) -> dict:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "domain": job["domain"],
        "estimated_products": job["estimated_products"],
        "progress": job.get("progress"),
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "error": job["error"],
    }


def purge_expired(ttl_seconds: int = 3600) -> int:
    """Nettoie les jobs terminés depuis plus de ttl_seconds."""
    now = time.monotonic()
    to_drop = [
        jid for jid, j in _registry.items()
        if j["status"] in ("completed", "failed")
        and j.get("finished_at_monotonic") is not None
        and (now - j["finished_at_monotonic"]) > ttl_seconds
    ]
    for jid in to_drop:
        _registry.pop(jid, None)
    return len(to_drop)
