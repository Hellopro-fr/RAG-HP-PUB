"""
Service de regeneration IDF.
============================

Orchestration de la regeneration du fichier `app/data/idf_nom_produit.json`
via le script `scripts/compute_idf.py`, avec reload du dict en RAM apres
generation.

Utilise par :
  - app/router/admin.py :: POST /admin/compute-idf (background task)
  - site/script/typesense/compute_idf_weekly.php (cron PHP hebdomadaire)
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any

from app.core.credentials import settings

logger = logging.getLogger(__name__)


# Chemins (resolus au runtime, marchent depuis container Docker ET hote)
#   app/services/idf_service.py -> app/ -> root opti-moteur-front
_SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_PATH = _SERVICE_ROOT / "scripts" / "compute_idf.py"
_OUT_PATH = _SERVICE_ROOT / "app" / "data" / "idf_nom_produit.json"


# Etat global (suivi des regenerations)
_lock = Lock()
_state: Dict[str, Any] = {
    "status": "never_run",      # never_run | running | ok | error | exception
    "started_at": None,         # ISO datetime
    "finished_at": None,
    "duration_s": None,
    "collection": None,
    "returncode": None,
    "stdout_tail": None,
    "stderr_tail": None,
    "error": None,
    "gcs_uploaded": None,       # bool si upload GCS reussi (None = GCS desactive)
}


def regenerate_idf_sync(collection: Optional[str] = None,
                        timeout_s: int = 900) -> Dict[str, Any]:
    """
    Lance compute_idf.py en subprocess (bloquant).

    Args:
        collection: collection Typesense source (default = settings.TYPESENSE_COLLECTION).
        timeout_s: timeout du subprocess (default 15 min, large pour 5M+ docs).

    Returns:
        dict avec status, returncode, stdout_tail, stderr_tail, duration_s.

    Effet de bord : ecrit `app/data/idf_nom_produit.json`.
    Le caller est responsable de recharger le cache idf_loader si besoin.
    """
    coll = collection or settings.TYPESENSE_COLLECTION
    cmd = [sys.executable, str(_SCRIPT_PATH), "--collection", coll]
    logger.info("Running: %s", " ".join(cmd))
    t0 = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(_SERVICE_ROOT),
        )
        duration = (datetime.now(timezone.utc) - t0).total_seconds()
        return {
            "status": "ok" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "duration_s": round(duration, 1),
            "stdout_tail": (result.stdout or "")[-2000:],
            "stderr_tail": (result.stderr or "")[-2000:],
        }
    except subprocess.TimeoutExpired as e:
        duration = (datetime.now(timezone.utc) - t0).total_seconds()
        return {
            "status": "error",
            "returncode": -1,
            "duration_s": round(duration, 1),
            "stdout_tail": (e.stdout or "")[-2000:] if e.stdout else "",
            "stderr_tail": f"TIMEOUT after {timeout_s}s",
        }


def regenerate_idf_background(collection: Optional[str] = None) -> None:
    """
    Wrapper utilise par FastAPI BackgroundTasks :
      1. Met a jour _state -> "running"
      2. Lance regenerate_idf_sync()
      3. Reload du cache idf_loader (force lazy reload au prochain get_idf)
      4. Met a jour _state -> "ok" / "error" / "exception"

    Thread-safe : protege par lock pour eviter 2 regen concurrentes.
    """
    with _lock:
        _state["status"] = "running"
        _state["collection"] = collection or settings.TYPESENSE_COLLECTION
        _state["started_at"] = datetime.now(timezone.utc).isoformat()
        _state["finished_at"] = None
        _state["error"] = None

    try:
        result = regenerate_idf_sync(collection)
        with _lock:
            _state["returncode"] = result["returncode"]
            _state["duration_s"] = result["duration_s"]
            _state["stdout_tail"] = result["stdout_tail"]
            _state["stderr_tail"] = result["stderr_tail"]
            _state["status"] = result["status"]
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()

        if result["status"] == "ok":
            # Upload du nouveau JSON vers GCS pour partage entre pods.
            # No-op si GCS_IDF_BUCKET non defini.
            try:
                from app.services import gcs_idf_storage
                if gcs_idf_storage.gcs_enabled():
                    upload_ok = gcs_idf_storage.upload(_OUT_PATH)
                    with _lock:
                        _state["gcs_uploaded"] = upload_ok
                else:
                    logger.info("GCS persistence disabled, IDF reste local au pod")
            except Exception as e:
                logger.warning("GCS upload failed: %s", e)

            # Reset cache du loader : force reload au prochain get_idf()
            try:
                from app.services import idf_loader
                idf_loader.reset_cache_for_test()
                # Trigger le reload tout de suite pour logger la stat
                idf_loader.idf_available()
                logger.info("IDF cache reset + reloaded successfully")
            except Exception as e:
                logger.warning("Could not reset IDF cache: %s", e)

    except Exception as e:
        logger.exception("regenerate_idf_background failed unexpectedly")
        with _lock:
            _state["status"] = "exception"
            _state["error"] = str(e)
            _state["finished_at"] = datetime.now(timezone.utc).isoformat()


def get_state() -> Dict[str, Any]:
    """Retourne un snapshot de l'etat actuel (lecture, thread-safe)."""
    with _lock:
        return dict(_state)


def is_running() -> bool:
    return get_state()["status"] == "running"
