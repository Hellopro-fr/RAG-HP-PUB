"""Liste paginée/filtrée/triée des produits d'un album avec détection statuts image."""

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

VALID_FILTERS = {"all", "errors", "pending", "synced"}
VALID_SORTS = {"name", "name_desc", "errors", "updated"}


def _load_manifest(domain_dir: str) -> dict | None:
    p = os.path.join(domain_dir, "manifest.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    except (json.JSONDecodeError, OSError):
        return None


def _detect_image_status(domain_dir: str, img: dict) -> str:
    main_rel = img.get("main")
    if not main_rel:
        return "error"
    main_abs = os.path.join(domain_dir, main_rel)
    return "ok" if os.path.exists(main_abs) else "orphan_manifest"


def _enrich_images(domain_dir: str, images: list[dict]) -> list[dict]:
    out = []
    for img in images:
        out.append({
            "filename":   img.get("filename"),
            "url_source": img.get("url_source"),
            "main":       img.get("main"),
            "thumb":      img.get("thumb"),
            "status":     _detect_image_status(domain_dir, img),
        })
    return out


def _enrich_product(domain_dir: str, p: dict) -> dict:
    enriched_images = _enrich_images(domain_dir, p.get("images") or [])
    error_count = sum(1 for i in enriched_images if i["status"] in ("error", "orphan_manifest"))
    if error_count > 0:
        sync_status = "error"
    elif p.get("synced"):
        sync_status = "synced"
    else:
        sync_status = "pending"
    return {
        "id_produit":  p.get("id_produit"),
        "nom":         p.get("nom"),
        "sync_status": sync_status,
        "error_count": error_count,
        "image_count": len(enriched_images),
        "last_update": p.get("last_update") or p.get("synced_at"),
        "images":      enriched_images,
    }


def _apply_filter(products: list[dict], flt: str) -> list[dict]:
    if flt == "all":
        return products
    if flt == "errors":
        return [p for p in products if p["error_count"] > 0]
    if flt == "pending":
        return [p for p in products if p["sync_status"] == "pending"]
    if flt == "synced":
        return [p for p in products if p["sync_status"] == "synced"]
    return products


def _apply_search(products: list[dict], q: str) -> list[dict]:
    needle = q.strip().lower()
    if not needle:
        return products
    return [p for p in products
            if needle in (p.get("nom") or "").lower()
            or needle in str(p.get("id_produit") or "").lower()]


def _apply_sort(products: list[dict], sort: str) -> list[dict]:
    if sort == "name":
        return sorted(products, key=lambda p: (p.get("nom") or "").lower())
    if sort == "name_desc":
        return sorted(products, key=lambda p: (p.get("nom") or "").lower(), reverse=True)
    if sort == "errors":
        return sorted(products, key=lambda p: p["error_count"], reverse=True)
    # "updated" (défaut)
    return sorted(products, key=lambda p: p.get("last_update") or "", reverse=True)


async def list_products(
    storage_base: str,
    domain: str,
    q: str = "",
    filter: str = "all",
    sort: str = "updated",
    page: int = 1,
    page_size: int = 100,
) -> dict[str, Any]:
    if filter not in VALID_FILTERS:
        raise ValueError(f"filter invalide: {filter}")
    if sort not in VALID_SORTS:
        raise ValueError(f"sort invalide: {sort}")
    if page < 1 or page_size < 1 or page_size > 500:
        raise ValueError("page/page_size invalides (page>=1, 1<=page_size<=500)")

    domain_dir = os.path.join(storage_base, "images", domain)
    if not os.path.isdir(domain_dir):
        raise FileNotFoundError(f"domain absent: {domain}")

    def _compute() -> dict[str, Any]:
        manifest = _load_manifest(domain_dir)
        raw_products = (manifest or {}).get("products") or []
        enriched = [_enrich_product(domain_dir, p) for p in raw_products]
        filtered = _apply_filter(enriched, filter)
        searched = _apply_search(filtered, q)
        sorted_p = _apply_sort(searched, sort)
        total = len(sorted_p)
        start = (page - 1) * page_size
        end = start + page_size
        slice_ = sorted_p[start:end]
        next_page = page + 1 if end < total else None
        return {
            "domain":    domain,
            "products":  slice_,
            "page":      page,
            "page_size": page_size,
            "total":     total,
            "next_page": next_page,
        }

    return await asyncio.to_thread(_compute)
