"""Aggregation des stats par domaine pour l'index Albums.

Performance : `total_size_bytes` est intentionnellement renvoyé à 0 — calculer
la taille agrégée ferait `os.walk` récursif sur chaque domaine, ce qui sur le
volume NFS de prod (1000+ domaines × 10000+ fichiers) dépasse les timeouts
HTTP raisonnables. La stat "taille" n'est pas critique pour l'usage admin V1
(le dialog de suppression affiche juste produits/images). Si besoin futur,
ajouter un endpoint dédié `GET /domains/{domain}/size` calculé à la demande,
ou maintenir un cache invalidé par le writer du manifest (V2).
"""

import asyncio
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def _count_errors(domain_dir: str) -> int:
    """Compte les entrées dans errors.json (tableau JSON) si présent."""
    err_path = os.path.join(domain_dir, "errors.json")
    if not os.path.exists(err_path):
        return 0
    try:
        with open(err_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read() or "[]")
        return len(data) if isinstance(data, list) else 0
    except (json.JSONDecodeError, OSError):
        return 0


def _summarize_domain(domain: str, domain_dir: str) -> dict[str, Any]:
    manifest_path = os.path.join(domain_dir, "manifest.json")
    manifest = None
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            manifest = None

    products = (manifest or {}).get("products") or []
    product_count = len(products)
    image_count = sum(len(p.get("images") or []) for p in products)
    synced_count = sum(1 for p in products if p.get("synced"))
    unsynced_count = product_count - synced_count
    last_update = (manifest or {}).get("last_updated")
    error_count = _count_errors(domain_dir)

    return {
        "domain": domain,
        "product_count": product_count,
        "image_count": image_count,
        "error_count": error_count,
        "synced_count": synced_count,
        "unsynced_count": unsynced_count,
        "last_update": last_update,
        # Toujours 0 en V1 — voir le bandeau du module.
        "total_size_bytes": 0,
    }


async def list_domains_with_stats(storage_base: str) -> dict[str, Any]:
    """Liste les domaines présents sous {storage_base}/images/ + stats agrégées.

    Retourne {"domains": [...], "total": N}, trié par domain ASC.
    Tolérant aux manifests absents/corrompus → counters à 0.
    """
    started = time.monotonic()
    images_base = os.path.join(storage_base, "images")
    if not os.path.isdir(images_base):
        return {"domains": [], "total": 0}

    domains: list[str] = sorted(
        d for d in os.listdir(images_base)
        if os.path.isdir(os.path.join(images_base, d))
    )

    # I/O FS bloquant → on délègue à un thread pour ne pas bloquer l'event loop.
    def _build():
        return [_summarize_domain(d, os.path.join(images_base, d)) for d in domains]

    summaries = await asyncio.to_thread(_build)
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "list_domains_with_stats: %d domains in %dms",
        len(summaries), duration_ms,
    )
    return {"domains": summaries, "total": len(summaries)}
