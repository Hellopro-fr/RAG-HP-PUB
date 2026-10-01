"""
Persistance du fichier IDF dans un bucket GCS.

Alternative au PVC ReadWriteMany (qui necessiterait Filestore = couts
~30-50EUR/mois). Avec GCS :
  - Cout : qq centimes/mois pour ~20 MB
  - Auth : Workload Identity (le SA Kubernetes du pod doit avoir
    roles/storage.objectAdmin sur le bucket)
  - Pattern : upload apres compute_idf, download au startup du pod

Si `settings.GCS_IDF_BUCKET` est vide -> toutes les fonctions sont des
no-op. Permet un mode "local-only" pour dev sans GCS.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.core.credentials import settings

logger = logging.getLogger(__name__)


def gcs_enabled() -> bool:
    """True si la persistance GCS est configuree."""
    return bool(settings.GCS_IDF_BUCKET)


def _get_client():
    """Lazy import du client GCS (evite l'import quand pas configure)."""
    from google.cloud import storage
    return storage.Client()


def _get_blob():
    """Retourne le blob target (bucket + object)."""
    client = _get_client()
    bucket = client.bucket(settings.GCS_IDF_BUCKET)
    return bucket.blob(settings.GCS_IDF_OBJECT)


def upload(local_path: Path) -> bool:
    """
    Upload le fichier local vers `gs://<GCS_IDF_BUCKET>/<GCS_IDF_OBJECT>`.

    Returns:
        True si upload reussi, False si GCS non configure ou echec.

    Idempotent : ecrase le blob existant.
    """
    if not gcs_enabled():
        logger.info("GCS upload skipped (GCS_IDF_BUCKET non defini)")
        return False
    if not local_path.exists():
        logger.warning("GCS upload skipped (local file %s absent)", local_path)
        return False

    try:
        blob = _get_blob()
        blob.upload_from_filename(str(local_path), content_type="application/json")
        size_mb = local_path.stat().st_size / (1024 * 1024)
        logger.info(
            "IDF uploaded to gs://%s/%s (%.1f MB)",
            settings.GCS_IDF_BUCKET, settings.GCS_IDF_OBJECT, size_mb,
        )
        return True
    except Exception as e:
        logger.exception("GCS upload failed: %s", e)
        return False


def download(local_path: Path) -> bool:
    """
    Download le blob GCS vers `local_path`. Cree le dossier parent si besoin.

    Returns:
        True si download reussi (fichier disponible sur disque local),
        False si GCS non configure, blob absent, ou erreur.
    """
    if not gcs_enabled():
        return False

    try:
        blob = _get_blob()
        if not blob.exists():
            logger.info(
                "IDF blob gs://%s/%s n'existe pas encore",
                settings.GCS_IDF_BUCKET, settings.GCS_IDF_OBJECT,
            )
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(local_path))
        size_mb = local_path.stat().st_size / (1024 * 1024)
        logger.info(
            "IDF downloaded from gs://%s/%s (%.1f MB) -> %s",
            settings.GCS_IDF_BUCKET, settings.GCS_IDF_OBJECT, size_mb, local_path,
        )
        return True
    except Exception as e:
        logger.warning("GCS download failed: %s", e)
        return False


def get_blob_updated_at() -> Optional[str]:
    """Retourne la date de derniere update du blob GCS (ISO string), ou None."""
    if not gcs_enabled():
        return None
    try:
        blob = _get_blob()
        blob.reload()
        if blob.updated:
            return blob.updated.isoformat()
    except Exception as e:
        logger.debug("GCS get_blob_updated_at failed: %s", e)
    return None
