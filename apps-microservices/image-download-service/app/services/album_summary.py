"""Aggregation des stats par domaine pour l'index Albums."""

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _count_dir_size_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _count_errors(domain_dir: str) -> int:
    """Compte les lignes dans errors.log si présent."""
    err_path = os.path.join(domain_dir, "errors.log")
    if not os.path.exists(err_path):
        return 0
    try:
        with open(err_path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
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
    total_size_bytes = _count_dir_size_bytes(domain_dir)

    return {
        "domain": domain,
        "product_count": product_count,
        "image_count": image_count,
        "error_count": error_count,
        "synced_count": synced_count,
        "unsynced_count": unsynced_count,
        "last_update": last_update,
        "total_size_bytes": total_size_bytes,
    }


async def list_domains_with_stats(storage_base: str) -> dict[str, Any]:
    """Liste les domaines présents sous {storage_base}/images/ + stats agrégées.

    Retourne {"domains": [...], "total": N}, trié par domain ASC.
    Tolérant aux manifests absents/corrompus → counters à 0.
    """
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
    return {"domains": summaries, "total": len(summaries)}
