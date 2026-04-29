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
    from image_download_service.core.nfs_lock import nfs_lock, NFSLockError
    # max_wait est un entier dans NFSLock — on arrondit au supérieur pour ne pas
    # tomber sous le timeout demandé (3.0 → 3, 0.5 → 1).
    max_wait = max(1, math.ceil(timeout))
    try:
        with nfs_lock(manifest_path, max_wait=max_wait):
            return fn()
    except NFSLockError as e:
        raise LockTimeoutError(f"Lock {manifest_path} occupé > {timeout}s ({e})")


async def delete_image(storage_base: str, domain: str, id_produit: str, filename: str) -> None:
    logger.info(
        "[albums] delete_image: domain=%s id_produit=%s filename=%s",
        domain, id_produit, filename,
    )
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
    logger.info("[albums] delete_product: domain=%s id_produit=%s", domain, id_produit)
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


class LegacyManifestError(Exception):
    """Manifest v1 legacy : aucune entrée image n'a `url_source` (champ ajouté en v2,
    2026-04-24). Le redownload n'est pas possible depuis l'API Albums — il faut
    re-ingérer le produit côté BO pour déclencher la migration v1→v2 automatique
    (cf. CLAUDE.md du service). Mappé en HTTP 422 par le router."""


def _is_legacy_v1(images: list[dict]) -> bool:
    """True si toutes les images ont `url_source` absent/null (manifest v1 pre-2026-04-24)."""
    if not images:
        return False
    return all(not img.get("url_source") for img in images)


def _clear_errors_for_urls(domain_dir: str, success_urls: set) -> int:
    """Retire de `errors.json` les entrées dont `url` est dans `success_urls`.

    Sans ce nettoyage, le statut d'une image revient à "error" dans
    `_detect_image_status` même après un redownload réussi (priorité haute
    sur les URLs présentes dans errors.json — cf. album_products.py:50).

    Tolérant aux fichiers absents/corrompus → no-op. Idempotent.
    Lock NFS dédié sur errors.json (séparé du lock manifest.json pour
    éviter une dépendance circulaire). Si le lock est occupé, on
    log et on skip — ne pas faire échouer le redownload pour ça.

    Si la liste devient vide, on supprime le fichier (état "no errors").
    Retourne le nombre d'entrées retirées.
    """
    if not success_urls:
        return 0
    errors_path = os.path.join(domain_dir, "errors.json")
    if not os.path.exists(errors_path):
        return 0

    from image_download_service.core.nfs_lock import nfs_lock, NFSLockError

    try:
        with nfs_lock(errors_path, max_wait=3):
            try:
                with open(errors_path, "r", encoding="utf-8") as f:
                    content = f.read()
                errors_list = json.loads(content) if content.strip() else []
            except (json.JSONDecodeError, OSError):
                return 0

            if not isinstance(errors_list, list):
                return 0

            new_list = [e for e in errors_list if e.get("url") not in success_urls]
            removed = len(errors_list) - len(new_list)
            if removed == 0:
                return 0

            if not new_list:
                try:
                    os.unlink(errors_path)
                except OSError:
                    pass
                return removed

            import tempfile
            fd, tmp = tempfile.mkstemp(dir=domain_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(new_list, indent=2, ensure_ascii=False))
                os.replace(tmp, errors_path)
            except Exception:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
            return removed
    except NFSLockError:
        logger.warning(
            "[albums] could not lock %s to clear errors (skipping)", errors_path,
        )
        return 0


async def redownload_product(storage_base: str, domain: str, id_produit: str, downloader) -> dict[str, Any]:
    """Force-redownload toutes les URLs connues du produit. Supprime les fichiers existants d'abord.

    Lève `LegacyManifestError` si le manifest est en v1 (aucune `url_source`) — dans ce cas
    le redownload n'est pas possible depuis l'API et on ne touche PAS aux fichiers existants.
    """
    logger.info("[albums] redownload_product start: domain=%s id_produit=%s", domain, id_produit)
    domain_dir = _domain_dir(storage_base, domain)
    manifest_path = _manifest_path(storage_base, domain)
    if not os.path.exists(manifest_path):
        logger.warning("[albums] redownload_product: manifest absent for %s", domain)
        raise FileNotFoundError(f"manifest {domain}")
    started = time.monotonic()

    # Étape 1 : capture des URLs sous lock (lecture seule, pas de mutation FS encore).
    def _peek_images():
        manifest = _load_manifest(manifest_path)
        for p in manifest.get("products") or []:
            if str(p.get("id_produit")) == str(id_produit):
                return p, list(p.get("images") or [])
        raise FileNotFoundError(f"product {id_produit}")

    product, images = await asyncio.to_thread(_with_lock, manifest_path, 3.0, _peek_images)

    # Garde-fou : manifest v1 → on ne supprime rien et on signale au caller.
    if _is_legacy_v1(images):
        logger.warning(
            "[albums] redownload_product: legacy v1 manifest for %s/%s "
            "(%d images sans url_source) — skip, re-ingest required",
            domain, id_produit, len(images),
        )
        raise LegacyManifestError(
            f"product {id_produit} en manifest v1 (aucune url_source) — "
            f"re-ingérer côté BO pour déclencher la migration v1→v2"
        )

    # Étape 2 : suppression des fichiers existants (sous nouveau lock pour atomicité).
    def _remove_old_files():
        for img in images:
            _remove_image_files(domain_dir, img)

    await asyncio.to_thread(_with_lock, manifest_path, 3.0, _remove_old_files)

    # Étape 3 : redownload séquentiel (parallélisable en V2).
    downloaded = 0
    skipped = 0
    failed = 0
    errors: list[dict] = []
    success_urls: set = set()
    for img in images:
        url = img.get("url_source")
        if not url:
            # Image individuelle sans url_source dans un manifest mixte (rare) — on skip.
            skipped += 1
            errors.append({"url": None, "reason": "url_source absent (legacy entry)"})
            continue
        try:
            res = await downloader.download_and_process(
                url, domain=domain, product_id=id_produit,
                product_name=product.get("nom"))
            if (res or {}).get("status") == "ok":
                downloaded += 1
                success_urls.add(url)
            else:
                failed += 1
                errors.append({"url": url, "reason": (res or {}).get("error", "unknown")})
        except Exception as e:
            failed += 1
            errors.append({"url": url, "reason": str(e)})

    # Étape 4 : nettoyer errors.json pour les URLs qui ont réussi cette fois-ci.
    # Sans ça, _detect_image_status garde le statut "error" en priorité même si
    # le fichier est maintenant présent.
    cleared = await asyncio.to_thread(_clear_errors_for_urls, domain_dir, success_urls)
    if cleared:
        logger.info(
            "[albums] redownload_product: cleared %d errors.json entries for %s/%s",
            cleared, domain, id_produit,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "[albums] redownload_product done: domain=%s id_produit=%s "
        "downloaded=%d skipped=%d failed=%d cleared_errors=%d duration_ms=%d",
        domain, id_produit, downloaded, skipped, failed, cleared, duration_ms,
    )
    return {
        "domain": domain, "id_produit": id_produit,
        "downloaded": downloaded, "skipped": skipped, "failed": failed,
        "errors": errors, "duration_ms": duration_ms,
    }


async def redownload_image(storage_base: str, domain: str, id_produit: str, filename: str, downloader) -> dict[str, Any]:
    logger.info(
        "[albums] redownload_image start: domain=%s id_produit=%s filename=%s",
        domain, id_produit, filename,
    )
    domain_dir = _domain_dir(storage_base, domain)
    manifest_path = _manifest_path(storage_base, domain)
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"manifest {domain}")
    started = time.monotonic()

    # Étape 1 : capture de l'image sous lock (sans mutation FS).
    def _peek_image():
        manifest = _load_manifest(manifest_path)
        for p in manifest.get("products") or []:
            if str(p.get("id_produit")) == str(id_produit):
                for img in p.get("images") or []:
                    if img.get("filename") == filename:
                        return p, img
                raise ManifestEntryMissingError(f"image {filename}")
        raise FileNotFoundError(f"product {id_produit}")

    product, img = await asyncio.to_thread(_with_lock, manifest_path, 3.0, _peek_image)

    # Garde-fou : entrée legacy sans url_source.
    if not img.get("url_source"):
        logger.warning(
            "[albums] redownload_image: legacy v1 entry %s/%s/%s — skip, re-ingest required",
            domain, id_produit, filename,
        )
        raise LegacyManifestError(
            f"image {filename} sans url_source (entrée legacy v1) — "
            f"re-ingérer le produit côté BO pour la migration v1→v2"
        )

    # Étape 2 : suppression du fichier sous lock.
    def _remove_old_file():
        _remove_image_files(domain_dir, img)

    await asyncio.to_thread(_with_lock, manifest_path, 3.0, _remove_old_file)

    # Étape 3 : redownload.
    url = img.get("url_source")
    try:
        res = await downloader.download_and_process(
            url, domain=domain, product_id=id_produit,
            product_name=product.get("nom"))
        ok = (res or {}).get("status") == "ok"
    except Exception as e:
        ok = False
        res = {"status": "error", "error": str(e)}

    # Étape 4 : nettoyer errors.json pour cette URL si succès (sinon on perdrait
    # l'info d'erreur sur un échec persistant).
    cleared = 0
    if ok and url:
        cleared = await asyncio.to_thread(_clear_errors_for_urls, domain_dir, {url})

    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "[albums] redownload_image done: domain=%s id_produit=%s filename=%s "
        "ok=%s cleared_errors=%d duration_ms=%d",
        domain, id_produit, filename, ok, cleared, duration_ms,
    )
    return {
        "domain": domain, "id_produit": id_produit, "filename": filename,
        "downloaded": 1 if ok else 0,
        "failed": 0 if ok else 1,
        "errors": [] if ok else [{"url": img.get("url_source"), "reason": (res or {}).get("error", "unknown")}],
        "duration_ms": duration_ms,
    }
