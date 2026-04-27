"""Actions destructives/redownload sur albums avec verrou NFS."""

import asyncio
import json
import logging
import math
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class LockTimeoutError(Exception):
    """Lock NFS occupé au-delà du timeout."""


class ManifestEntryMissingError(Exception):
    """Le manifest ne contient pas l'entrée demandée (utilisé pour redownload sur image inconnue → 422)."""


def _manifest_path(storage_base: str, domain: str) -> str:
    return os.path.join(storage_base, "images", domain, "manifest.json")


def _domain_dir(storage_base: str, domain: str) -> str:
    return os.path.join(storage_base, "images", domain)


def _load_manifest(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.loads(f.read())


def _atomic_write(path: str, manifest: dict) -> None:
    import tempfile
    dirpath = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _remove_image_files(domain_dir: str, img: dict) -> None:
    for key in ("main", "thumb"):
        rel = img.get(key)
        if not rel:
            continue
        abs_p = os.path.join(domain_dir, rel)
        try:
            if os.path.exists(abs_p):
                os.unlink(abs_p)
        except OSError as e:
            logger.warning(f"Suppression {abs_p} échouée: {e}")


def _with_lock(manifest_path: str, timeout: float, fn):
    """Wrap synchrone autour de nfs_lock avec timeout. Lève LockTimeoutError si occupé.

    Note d'implémentation : le `nfs_lock` du projet expose un paramètre
    `max_wait` (en secondes) et lève `NFSLockError` à l'expiration. On le
    configure avec le timeout demandé et on convertit l'exception locale
    en `LockTimeoutError` pour exposer une API stable côté service.
    """
    from core.nfs_lock import nfs_lock, NFSLockError
    # max_wait est un entier dans NFSLock — on arrondit au supérieur pour ne pas
    # tomber sous le timeout demandé (3.0 → 3, 0.5 → 1).
    max_wait = max(1, math.ceil(timeout))
    try:
        with nfs_lock(manifest_path, max_wait=max_wait):
            return fn()
    except NFSLockError as e:
        raise LockTimeoutError(f"Lock {manifest_path} occupé > {timeout}s ({e})")


async def delete_image(storage_base: str, domain: str, id_produit: str, filename: str) -> None:
    domain_dir = _domain_dir(storage_base, domain)
    if not os.path.isdir(domain_dir):
        raise FileNotFoundError(f"domain {domain}")
    manifest_path = _manifest_path(storage_base, domain)

    def _do():
        manifest = _load_manifest(manifest_path)
        for product in manifest.get("products") or []:
            if str(product.get("id_produit")) != str(id_produit):
                continue
            new_images = []
            removed = None
            for img in product.get("images") or []:
                if img.get("filename") == filename:
                    removed = img
                else:
                    new_images.append(img)
            if removed is None:
                raise FileNotFoundError(f"image {filename} not in product {id_produit}")
            product["images"] = new_images
            _remove_image_files(domain_dir, removed)
            _atomic_write(manifest_path, manifest)
            return
        raise FileNotFoundError(f"product {id_produit} not in {domain}")

    await asyncio.to_thread(_with_lock, manifest_path, 3.0, _do)


async def delete_product(storage_base: str, domain: str, id_produit: str) -> None:
    domain_dir = _domain_dir(storage_base, domain)
    if not os.path.isdir(domain_dir):
        raise FileNotFoundError(f"domain {domain}")
    manifest_path = _manifest_path(storage_base, domain)

    def _do():
        manifest = _load_manifest(manifest_path)
        new_products = []
        target = None
        for p in manifest.get("products") or []:
            if str(p.get("id_produit")) == str(id_produit):
                target = p
            else:
                new_products.append(p)
        if target is None:
            raise FileNotFoundError(f"product {id_produit}")
        for img in target.get("images") or []:
            _remove_image_files(domain_dir, img)
        manifest["products"] = new_products
        _atomic_write(manifest_path, manifest)

    await asyncio.to_thread(_with_lock, manifest_path, 3.0, _do)


async def redownload_product(storage_base: str, domain: str, id_produit: str, downloader) -> dict[str, Any]:
    """Force-redownload toutes les URLs connues du produit. Supprime les fichiers existants d'abord."""
    domain_dir = _domain_dir(storage_base, domain)
    manifest_path = _manifest_path(storage_base, domain)
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest {domain}")
    started = time.monotonic()

    # Charger sous lock pour figer la liste d'URLs
    def _capture_urls():
        manifest = _load_manifest(manifest_path)
        for p in manifest.get("products") or []:
            if str(p.get("id_produit")) == str(id_produit):
                for img in p.get("images") or []:
                    _remove_image_files(domain_dir, img)
                return p, list(p.get("images") or [])
        raise FileNotFoundError(f"product {id_produit}")

    product, images = await asyncio.to_thread(_with_lock, manifest_path, 3.0, _capture_urls)

    downloaded = 0
    failed = 0
    errors: list[dict] = []
    for img in images:
        url = img.get("url_source")
        try:
            res = await downloader.download_and_process(
                url, domain=domain, product_id=id_produit,
                product_name=product.get("nom"))
            if (res or {}).get("status") == "ok":
                downloaded += 1
            else:
                failed += 1
                errors.append({"url": url, "reason": (res or {}).get("error", "unknown")})
        except Exception as e:
            failed += 1
            errors.append({"url": url, "reason": str(e)})

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "domain": domain, "id_produit": id_produit,
        "downloaded": downloaded, "skipped": 0, "failed": failed,
        "errors": errors, "duration_ms": duration_ms,
    }


async def redownload_image(storage_base: str, domain: str, id_produit: str, filename: str, downloader) -> dict[str, Any]:
    domain_dir = _domain_dir(storage_base, domain)
    manifest_path = _manifest_path(storage_base, domain)
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest {domain}")
    started = time.monotonic()

    def _capture():
        manifest = _load_manifest(manifest_path)
        for p in manifest.get("products") or []:
            if str(p.get("id_produit")) == str(id_produit):
                for img in p.get("images") or []:
                    if img.get("filename") == filename:
                        _remove_image_files(domain_dir, img)
                        return p, img
                raise ManifestEntryMissingError(f"image {filename}")
        raise FileNotFoundError(f"product {id_produit}")

    product, img = await asyncio.to_thread(_with_lock, manifest_path, 3.0, _capture)

    try:
        res = await downloader.download_and_process(
            img.get("url_source"), domain=domain, product_id=id_produit,
            product_name=product.get("nom"))
        ok = (res or {}).get("status") == "ok"
    except Exception as e:
        ok = False
        res = {"status": "error", "error": str(e)}

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "domain": domain, "id_produit": id_produit, "filename": filename,
        "downloaded": 1 if ok else 0,
        "failed": 0 if ok else 1,
        "errors": [] if ok else [{"url": img.get("url_source"), "reason": (res or {}).get("error", "unknown")}],
        "duration_ms": duration_ms,
    }
