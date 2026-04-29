import aiohttp
import aiofiles
import hashlib
import json
import os
import logging
import asyncio
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional, List, Dict, Tuple
import random

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Local rate limit: delay between requests (seconds)
LOCAL_RATE_DELAY = float(os.environ.get("IMAGE_DOWNLOAD_DELAY", 0.5))

# Répertoire de base du stockage des images (surchargeable via variable d'environnement)
_STORAGE_BASE = os.environ.get("STORAGE_BASE", "/app/storage")

# =============================================================================
# Catégories et sévérités d'erreurs pour le reporting
# =============================================================================
# Catégories possibles :
#   no_url           → Aucune URL d'image fournie dans le message
#   http_client      → Erreur HTTP 4xx côté client (403, 404, etc.)
#   http_server      → Erreur HTTP 5xx côté serveur source
#   timeout          → Le serveur source n'a pas répondu à temps
#   network          → Erreur réseau (DNS, connexion refusée, etc.)
#   processing       → Image téléchargée mais traitement échoué (corrompue, format invalide)
#   dlq              → Message envoyé en Dead-Letter Queue après épuisement des retries
#
# Sévérités :
#   warning  → Problème mineur ou potentiellement temporaire
#   error    → Échec confirmé après retries
#   critical → Échec fatal (DLQ, message invalide)

def _classify_http_error(status_code: int) -> Tuple[str, str, str]:
    """
    Classifie une erreur HTTP en (raison, catégorie, sévérité).
    """
    if status_code == 403:
        return (f"HTTP {status_code} — Accès refusé (anti-bot ou hotlink protection)", "http_client", "error")
    elif status_code == 404:
        return (f"HTTP {status_code} — Image introuvable à la source", "http_client", "warning")
    elif status_code == 429:
        return (f"HTTP {status_code} — Rate limit atteint sur le serveur source", "http_client", "warning")
    elif 400 <= status_code < 500:
        return (f"HTTP {status_code} — Erreur client", "http_client", "warning")
    elif 500 <= status_code < 600:
        return (f"HTTP {status_code} — Erreur serveur source", "http_server", "warning")
    else:
        return (f"HTTP {status_code} — Code inattendu", "http_client", "warning")


def _classify_network_error(error: Exception) -> Tuple[str, str, str]:
    """
    Classifie une exception réseau en (raison, catégorie, sévérité).
    """
    error_str = str(error).lower()
    
    if isinstance(error, asyncio.TimeoutError) or "timeout" in error_str:
        return (f"Timeout — Le serveur source n'a pas répondu dans le délai imparti", "timeout", "warning")
    elif "dns" in error_str or "name resolution" in error_str or "getaddrinfo" in error_str:
        return (f"DNS — Impossible de résoudre le nom de domaine: {error}", "network", "error")
    elif "connection refused" in error_str or "connect" in error_str:
        return (f"Connexion refusée par le serveur source: {error}", "network", "warning")
    elif "ssl" in error_str or "certificate" in error_str:
        return (f"Erreur SSL/TLS: {error}", "network", "error")
    else:
        return (f"Erreur réseau: {error}", "network", "warning")


def _url_hash8(url: str) -> str:
    """
    Retourne les 8 premiers caractères hex du sha1(url).
    Utilisé pour dériver un suffixe de filename stable et unique par URL.
    """
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]


def _build_filename(slug: str, product_id: str, url: str, ext: str) -> str:
    """
    Construit un filename dérivé de l'URL : {slug}-{product_id}-{hash8}{ext}.
    ext doit inclure le point initial (ex : ".jpg").
    """
    return f"{slug}-{product_id}-{_url_hash8(url)}{ext}"


def _load_manifest_entry(manifest_path: str, product_id: str) -> Optional[Dict]:
    """
    Lit manifest.json et retourne l'entrée du produit product_id, ou None si
    le manifest est absent, corrompu, ou si le produit n'est pas présent.
    """
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, "r") as f:
            content = f.read()
            if not content.strip():
                return None
            manifest = json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Could not read manifest {manifest_path}: {e}")
        return None
    for entry in manifest.get("products", []):
        if entry.get("id_produit") == product_id:
            return entry
    return None


def _delete_image_files(image_entry: Dict, storage_base: str = "/app/storage",
                        domain: Optional[str] = None) -> None:
    """
    Supprime les fichiers main et thumb d'une entrée image du manifest.
    Un fichier manquant loggue un warning mais ne lève jamais d'exception.
    Supporte les chemins absolus (legacy) et relatifs depuis le manifest.
    Pour les chemins relatifs, reconstruit : {storage_base}/images/{domain}/{relpath}.
    """
    for key in ("main", "thumb"):
        path = image_entry.get(key, "")
        if not path:
            continue
        if not os.path.isabs(path):
            if domain:
                path = os.path.join(storage_base, "images", domain, path)
            else:
                logger.warning(f"Cannot resolve relative path '{path}' without domain")
                continue
        try:
            if os.path.exists(path):
                os.remove(path)
            else:
                logger.warning(f"File to delete not found: {path}")
        except OSError as e:
            logger.warning(f"Failed to delete {path}: {e}")


class Downloader:
    def __init__(self):
        from image_download_service.core.image_processor import ImageProcessor
        self.image_processor = ImageProcessor()
        
        # Proxy config
        self.proxy_password = os.environ.get("APIFY_PROXY")
        self.proxy_url = os.environ.get("PROXY_URL") 
        
        if self.proxy_password and not self.proxy_url:
             self.proxy_url = f"http://auto:{self.proxy_password}@proxy.apify.com:8000"
             logger.info(f"Configured Apify Proxy (auto/port 8000)")
        elif self.proxy_url:
             logger.info(f"Configured generic Proxy: {self.proxy_url}")

    def _normalize_name(self, name: str) -> str:
        """
        Simple slugification to match PHP's normaliser_mot_expression roughly.
        """
        # Lowercase
        name = name.lower()
        
        # Remove accents
        nfkd_form = unicodedata.normalize('NFKD', name)
        name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        
        # Replace non-alphanumeric with -
        name = re.sub(r'[^a-z0-9]+', '-', name)
        
        # Trim dashes
        name = name.strip('-')
        
        return name

    def _recupere_domaine(self, input_domain: str) -> str:
        """
        Equivalent Python de la fonction PHP recupere_domaine().
        Extrait le host d'une URL et supprime le prefixe 'www.'.
        """
        if not input_domain:
            return ""
        parsed = urlparse(input_domain)
        domain = parsed.hostname if parsed.hostname else input_domain.split('/')[0]
        domain = re.sub(r'^www\.', '', domain, flags=re.IGNORECASE)
        return domain.lower()

    async def download_and_process(self, url: str, domain: str, product_id: str, product_name: str, storage_base: str = None, index: int = 0) -> Dict:
        """
        Downloads image bytes and delegates to ImageProcessor.

        Le filename sur disque est dérivé de l'URL via _build_filename pour garantir
        l'idempotence : même URL → même filename, indépendamment de l'ordre de traitement.

        Returns:
            dict with either:
                - {"status": "ok", "paths": {"main_path": ..., "thumb_path": ..., "filename": ..., "url_source": <url>}}
                - {"status": "error", "reason": "...", "categorie": "...", "severite": "..."}  on failure
        """
        # I2 : aligner storage_base sur _STORAGE_BASE si non fourni explicitement
        if storage_base is None:
            storage_base = _STORAGE_BASE

        retries = 3
        timeout = aiohttp.ClientTimeout(total=30)
        last_error_info = None

        # Construire le filename à partir de l'URL (idempotent, dérivé de l'URL)
        slug = self._normalize_name(product_name)
        # Détecter l'extension depuis l'URL, sinon fallback .jpg
        parsed_url = urlparse(url)
        url_path = parsed_url.path.lower()
        if url_path.endswith('.png'):
            ext = '.png'
        elif url_path.endswith('.gif'):
            ext = '.gif'
        elif url_path.endswith('.webp'):
            ext = '.webp'
        else:
            ext = '.jpg'
        filename = _build_filename(slug, product_id, url, ext)

        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    kwargs = {}
                    if self.proxy_url:
                        kwargs["proxy"] = self.proxy_url

                    async with session.get(url, **kwargs) as response:
                        logger.info(f"Download status for {url}: {response.status}")
                        if response.status == 200:
                            content = await response.read()

                            try:
                                paths = self.image_processor.process_image(
                                    content=content,
                                    domain=domain,
                                    product_id=product_id,
                                    product_name=product_name,
                                    base_storage_dir=storage_base,
                                    filename=filename,
                                )
                                paths["url_source"] = url
                                return {"status": "ok", "paths": paths}
                            except Exception as e:
                                logger.error(f"Image processing failed for {url}: {e}")
                                # Erreur de traitement = pas de retry, l'image est corrompue
                                return {
                                    "status": "error",
                                    "reason": f"Traitement échoué — Image corrompue ou format non supporté: {e}",
                                    "categorie": "processing",
                                    "severite": "error"
                                }
                            
                        else:
                            reason, categorie, severite = _classify_http_error(response.status)
                            logger.warning(f"Failed to download {url}: Status {response.status}")
                            last_error_info = {
                                "status": "error",
                                "reason": reason,
                                "categorie": categorie,
                                "severite": severite
                            }
                            # Pour les 4xx (sauf 429), pas de retry car c'est une erreur permanente
                            if 400 <= response.status < 500 and response.status != 429:
                                return last_error_info

            except Exception as e:
                reason, categorie, severite = _classify_network_error(e)
                logger.warning(f"Error downloading {url} (Attempt {attempt+1}): {e}")
                last_error_info = {
                    "status": "error",
                    "reason": reason,
                    "categorie": categorie,
                    "severite": severite
                }
                await asyncio.sleep(attempt * 1)
        
        # Toutes les tentatives échouées → élever la sévérité à "error"
        if last_error_info:
            last_error_info["severite"] = "error"
            last_error_info["reason"] += f" (après {retries} tentatives)"
            return last_error_info
        
        return {
            "status": "error",
            "reason": f"Échec inconnu après {retries} tentatives",
            "categorie": "network",
            "severite": "error"
        }

    async def save_error(self, domain: str, product_id: str, product_name: str, url: str,
                         error_reason: str, error_category: str = "unknown", error_severity: str = "error"):
        """
        Save download and processing errors to a dedicated domain errors.json file.
        Uses NFS-safe locking (os.mkdir) for exclusive cross-replica locking
        and atomic write (temp file + os.replace) to prevent corruption.
        
        Catégories: no_url, http_client, http_server, timeout, network, processing, dlq
        Sévérités:  warning, error, critical
        """
        import json
        import tempfile
        from image_download_service.core.nfs_lock import nfs_lock
        
        errors_dir = f"{_STORAGE_BASE}/images/{domain}"
        errors_path = f"{errors_dir}/errors.json"
        
        os.makedirs(errors_dir, exist_ok=True)
        
        error_entry = {
            "id_produit": product_id,
            "nom": product_name,
            "url": url,
            "erreur": error_reason,
            "categorie": error_category,
            "severite": error_severity,
            "date": datetime.now().isoformat()
        }
        
        try:
            with nfs_lock(errors_path):
                errors_list = []
                if os.path.exists(errors_path):
                    try:
                        with open(errors_path, 'r') as f:
                            content = f.read()
                            if content.strip():
                                errors_list = json.loads(content)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Corrupted errors file detected for {domain}, starting fresh: {e}")
                
                errors_list.append(error_entry)
                
                fd, tmp_path = tempfile.mkstemp(dir=errors_dir, suffix='.tmp')
                try:
                    with os.fdopen(fd, 'w') as tmp_f:
                        tmp_f.write(json.dumps(errors_list, indent=2, ensure_ascii=False))
                    os.replace(tmp_path, errors_path)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
        except Exception as e:
            logger.error(f"Could not write error file for {domain}: {e}")

    async def process_product(self, product_data: dict) -> dict:
        """
        Synchronisation d'images set-based : la liste url_images reçue fait autorité.

        - URLs déjà dans le manifest (url_source match) ET fichiers présents sur disque → réutilisées (0 DL).
        - Nouvelles URLs → téléchargées avec un filename dérivé du hash SHA1 de l'URL.
        - URLs disparues de la liste → fichiers main+thumb supprimés du FS (orphan cleanup).
        - Manifest v1 legacy (aucune entrée image n'a url_source) → rebuild complet + suppression des fichiers legacy.
        - Échec de DL partiel : les URLs réussies sont conservées ; si tout échoue, l'ancien manifest est préservé.
        """
        domain = self._recupere_domaine(
            product_data.get("domaine_dspi") or product_data.get("domaine", "unknown")
        )
        product_id = product_data.get("id_produit", "unknown")
        product_name = (
            product_data.get("nom") or product_data.get("nom_produit")
            or product_data.get("name") or f"produit-{product_id}"
        )
        urls_raw = product_data.get("url_images")

        if not urls_raw:
            await self.save_error(
                domain, product_id, product_name, "",
                "Aucune URL d'image fournie dans le message produit",
                "no_url", "warning",
            )
            return product_data

        # Normaliser urls_raw en liste, supprimer les entrées vides
        if isinstance(urls_raw, str):
            urls = [u.strip() for u in urls_raw.split(",")] if "," in urls_raw else [urls_raw]
        else:
            urls = list(urls_raw)
        urls = [u for u in urls if u]

        # Charger l'entrée manifest précédente pour ce produit
        manifest_path = f"{_STORAGE_BASE}/images/{domain}/manifest.json"
        prev_entry = _load_manifest_entry(manifest_path, product_id)

        # Détecter v1 legacy : entrée présente, avec images, mais aucune n'a url_source
        is_v1_legacy = (
            prev_entry is not None
            and prev_entry.get("images")
            and not any(img.get("url_source") for img in prev_entry["images"])
        )

        if is_v1_legacy:
            logger.info(f"🔁 Legacy v1 manifest détecté pour le produit {product_id} — rebuild complet")
            for legacy_img in prev_entry.get("images", []):
                _delete_image_files(legacy_img, storage_base=_STORAGE_BASE, domain=domain)
            prev_by_url = {}
        else:
            prev_by_url = {
                img["url_source"]: img
                for img in (prev_entry.get("images", []) if prev_entry else [])
                if img.get("url_source")
            }

        processed = []
        download_errors = []
        reused_count = 0
        first_download = True

        logger.info(f"🔄 Traitement de {len(urls)} URLs pour le produit {product_id} ({domain})")

        for url in urls:
            # Tentative de réutilisation si l'URL est déjà dans le manifest
            if url in prev_by_url:
                entry = prev_by_url[url]
                main_rel = entry.get("main", "")
                thumb_rel = entry.get("thumb", "")
                main_abs = os.path.join(_STORAGE_BASE, "images", domain, main_rel)
                thumb_abs = os.path.join(_STORAGE_BASE, "images", domain, thumb_rel)
                if main_rel and thumb_rel and os.path.exists(main_abs) and os.path.exists(thumb_abs):
                    logger.info(f"⏭️  URL inchangée, fichiers réutilisés : {url[:80]}")
                    processed.append({
                        "url_source": url,
                        "main_path": main_abs,
                        "thumb_path": thumb_abs,
                        "filename": entry.get("filename", ""),
                    })
                    reused_count += 1
                    continue
                logger.warning(f"⚠️  Entrée manifest trouvée pour {url[:80]} mais fichiers manquants — re-téléchargement")

            # Délai entre téléchargements successifs pour éviter les 429 côté fournisseur
            # (skippé avant le premier téléchargement ; les réutilisations ne comptent pas)
            if not first_download:
                await asyncio.sleep(LOCAL_RATE_DELAY)
            first_download = False

            # Téléchargement (storage_base omis : download_and_process utilisera _STORAGE_BASE)
            result = await self.download_and_process(
                url=url, domain=domain, product_id=product_id, product_name=product_name,
            )
            if result["status"] == "ok" and result.get("paths"):
                processed.append(result["paths"])
            else:
                download_errors.append(url)
                await self.save_error(
                    domain, product_id, product_name, url,
                    result.get("reason", "Erreur de téléchargement inconnue"),
                    result.get("categorie", "unknown"),
                    result.get("severite", "error"),
                )

        # Échec total : si aucune image n'a été traitée (ni réutilisée, ni téléchargée),
        # on préserve l'ancien manifest et on ne touche pas aux orphelins.
        all_failed = len(processed) == 0 and len(download_errors) > 0
        if all_failed:
            logger.warning(
                f"Tous les téléchargements ont échoué pour le produit {product_id} — "
                f"l'ancien manifest est préservé ({len(urls)} téléchargements échoués)"
            )
            product_data["processed_images"] = processed
            product_data["total_images"] = len(urls)
            product_data["download_errors_count"] = len(download_errors)
            return product_data

        # Orphan cleanup : URLs présentes dans l'ancien manifest mais absentes du nouveau message
        new_urls_set = set(urls)
        orphans_deleted = 0
        for old_url, old_entry in prev_by_url.items():
            if old_url not in new_urls_set:
                logger.info(f"🗑️  Suppression des fichiers orphelins pour l'URL : {old_url[:80]}")
                _delete_image_files(old_entry, storage_base=_STORAGE_BASE, domain=domain)
                orphans_deleted += 1

        # Mettre à jour product_data pour le consumer (I1 : pas de skipped_count)
        product_data["processed_images"] = processed
        product_data["total_images"] = len(urls)
        product_data["download_errors_count"] = len(download_errors)

        # Écrire le manifest seulement si on a un nouvel état à persister
        # (le cas all_failed — aucune image traitée ET des erreurs — est traité en early-return plus haut)
        if processed or orphans_deleted > 0:
            await self._save_to_manifest(domain, product_id, product_name, processed)

        logger.info(
            f"📊 Produit {product_id} ({domain}) : {len(urls)} URLs | "
            f"{reused_count} réutilisées, {len(processed) - reused_count} téléchargées, "
            f"{orphans_deleted} orphelins supprimés, {len(download_errors)} erreurs"
        )
        return product_data

    async def _save_to_manifest(self, domain: str, product_id: str, product_name: str, processed_images: list):
        """
        Appends product metadata to the domain's manifest.json file.
        This manifest will be included in the archive for the BO to update the database.
        
        Uses NFS-safe locking (os.mkdir) for exclusive cross-replica locking 
        and atomic write (temp file + os.replace) to prevent corruption.
        """
        import json
        import tempfile
        from image_download_service.core.nfs_lock import nfs_lock
        
        manifest_dir = f"{_STORAGE_BASE}/images/{domain}"
        manifest_path = f"{manifest_dir}/manifest.json"
        
        # Create directory if needed
        os.makedirs(manifest_dir, exist_ok=True)
        
        # Build product entry
        # I1 : last_update est posé à chaque écriture/réécriture du produit
        # pour que le tri "updated" du service album_products soit stable
        # même quand le produit n'a pas encore été marqué "synced".
        product_entry = {
            "id_produit": product_id,
            "nom": product_name,
            "last_update": datetime.now().isoformat(),
            "images": []
        }
        
        for img in processed_images:
            # Extract relative paths from full paths
            main_path = img.get("main_path", "")
            thumb_path = img.get("thumb_path", "")
            
            # Convert to relative paths (e.g., produit-2/1/0/0/nom-60001.jpg)
            if "/images/" in main_path:
                main_rel = main_path.split(f"/images/{domain}/")[1] if f"/images/{domain}/" in main_path else main_path
            else:
                main_rel = main_path
                
            if "/images/" in thumb_path:
                thumb_rel = thumb_path.split(f"/images/{domain}/")[1] if f"/images/{domain}/" in thumb_path else thumb_path
            else:
                thumb_rel = thumb_path
            
            product_entry["images"].append({
                "url_source": img.get("url_source", ""),
                "main": main_rel,
                "thumb": thumb_rel,
                "filename": img.get("filename", "")
            })
        
        # --- NFS-safe exclusive lock + atomic write to prevent concurrent corruption ---
        try:
            with nfs_lock(manifest_path):
                # Read existing manifest (under lock)
                manifest = {"products": [], "last_updated": ""}
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r') as f:
                            content = f.read()
                            if content.strip():
                                manifest = json.loads(content)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Corrupted manifest detected for {domain}, starting fresh: {e}")
                        manifest = {"products": [], "last_updated": ""}
                
                # Update or add product entry
                existing_idx = next((i for i, p in enumerate(manifest.get("products", [])) if p.get("id_produit") == product_id), None)
                if existing_idx is not None:
                    manifest["products"][existing_idx] = product_entry
                else:
                    manifest.setdefault("products", []).append(product_entry)
                
                manifest["last_updated"] = datetime.now().isoformat()
                
                # Write to temp file, then atomic rename
                fd, tmp_path = tempfile.mkstemp(dir=manifest_dir, suffix='.tmp')
                try:
                    with os.fdopen(fd, 'w') as tmp_f:
                        tmp_f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
                    os.replace(tmp_path, manifest_path)
                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
        except Exception as e:
            logger.error(f"Could not write manifest for {domain}: {e}")
