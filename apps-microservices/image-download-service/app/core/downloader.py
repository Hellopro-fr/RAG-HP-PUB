import aiohttp
import aiofiles
import hashlib
import json
import os
import logging
import asyncio
import re
import tempfile
import time
import unicodedata
import weakref
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
        from image_download_service.core.image_processor import ImageProcessor, process_logo
        self.image_processor = ImageProcessor()
        self.process_logo = process_logo
        
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

    async def process_page_image(self, payload: dict) -> Optional[dict]:
        """
        Télécharge et traite une image de page (pipeline Chantier D, spec §9.7).

        **Sémantique INSERT-only** (différent du flux FP set-based) :
        - 1 événement = 1 image (pas de groupement N URLs par produit)
        - Idempotence : si ``url_source`` + fichier main présent → skip (retourne entrée existante)
        - Pas d'orphan cleanup (INSERT only, pas de replace-from-source)

        Mapping champ wire → manifest : ``payload["url_image"]`` → ``entry["url_source"]``

        Payload attendu (champs wire du POST /enqueue T4) :
        ```json
        {
            "id_image_isi": <int>,
            "domaine": "<str>",
            "url_image": "<str>",
            "url_page_source": "<str>",
            "page_type": "<str>",
            "alt_text": "<str|null>",
            "contexte_h1": "<str|null>",
            "contexte_h2": "<str|null>"
        }
        ```

        Retourne l'entrée manifest insérée/réutilisée, ou None en cas d'erreur
        (l'erreur est enregistrée dans errors_pages.json via _append_errors_pages_entry).

        **Limitation MVP — race window sur l'idempotence** :
        Deux consumers concurrents peuvent passer simultanément le check d'idempotence
        (étape 1) et télécharger la même image deux fois. Le second write passe par
        ``replace_idx`` dans ``_append_manifest_pages_entry``, donc pas de corruption
        du manifest, mais la bande passante est gaspillée. Acceptable à <100 images
        concurrentes par domaine. Amélioration future : lock per-url_source OU
        check-inside-lock dans ``_append_manifest_pages_entry``.

        **Divergence shard spec §9.3 vs T3** :
        - Spec §9.3 : ``pages/{shard}/{shard}/{shard}/{filename}`` (3 niveaux)
        - Spec §9.5 example : ``pages/1/0/0/...`` (3 niveaux confirmés)
        - T3 ``process_image_page`` (image_processor.py) : ``pages/{shard1}/{shard2}/{filename}``
          (2 niveaux — shard1=last char stem, shard2=second-to-last char stem)
        - T6 délègue le calcul des shards à T3 (``self.image_processor.process_image_page``),
          donc les paths réels utilisent le schéma 2-niveaux de T3.
        TODO(T8-ou-post-MVP) : aligner T3 sur spec §9.3 (3 niveaux) OU mettre à jour la spec.
        Ne pas modifier T3 dans ce commit — concern séparé.

        Args:
            payload: Dict du message consommé depuis RabbitMQ (voir shape ci-dessus).

        Returns:
            Dict correspondant à l'entrée ``pages_images[]`` du manifest, ou None.
        """
        domain = payload.get("domaine", "unknown")
        id_image_isi = payload.get("id_image_isi")
        url_image = payload.get("url_image", "")
        url_page_source = payload.get("url_page_source", "")
        page_type = payload.get("page_type", "")
        alt_text = payload.get("alt_text")
        # contexte_h1 et contexte_h2 sont extraits du payload mais non écrits dans
        # manifest_pages.json (délibéré, per spec §9.5 schema) — ils sont déjà persistés
        # dans la table image_scrapping_ia côté BO (Hellopro PHP).

        # --- Étape 1 : Idempotence — vérification dans manifest_pages.json ---
        try:
            manifest = await asyncio.to_thread(_load_manifest_pages_file, domain)
            existing = next(
                (e for e in manifest.get("pages_images", []) if e.get("url_source") == url_image),
                None
            )
            if existing:
                main_abs = os.path.join(_STORAGE_BASE, "images", domain, existing.get("main", ""))
                if os.path.exists(main_abs):
                    logger.info(
                        f"[process_page_image] Idempotence : url_source déjà présente + fichier OK, skip : {url_image[:80]}"
                    )
                    return existing
                logger.warning(
                    f"[process_page_image] Entrée manifest trouvée pour {url_image[:80]} mais fichier absent — re-téléchargement"
                )
        except Exception as e:
            logger.warning(f"[process_page_image] Erreur lecture manifest_pages pour {domain}: {e}")

        # --- Étape 2 : Téléchargement HTTP (pattern download_and_process) ---
        retries = 3
        timeout = aiohttp.ClientTimeout(total=30)
        content = None
        last_error_msg = None

        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    kwargs = {}
                    if self.proxy_url:
                        kwargs["proxy"] = self.proxy_url

                    async with session.get(url_image, **kwargs) as response:
                        logger.info(f"[process_page_image] Download status {url_image}: {response.status}")
                        if response.status == 200:
                            content = await response.read()
                            break  # Téléchargement réussi → sortir de la boucle retry
                        else:
                            reason, _cat, _sev = _classify_http_error(response.status)
                            last_error_msg = reason
                            logger.warning(f"[process_page_image] {reason}")
                            # 4xx permanentes → pas de retry
                            if 400 <= response.status < 500 and response.status != 429:
                                break

            except Exception as e:
                reason, _cat, _sev = _classify_network_error(e)
                last_error_msg = reason
                logger.warning(f"[process_page_image] {reason} (tentative {attempt + 1}/{retries})")
                await asyncio.sleep(attempt * 1)

        if content is None:
            error_entry = {
                "id_image_isi": id_image_isi,
                "url_image": url_image,
                "url_page_source": url_page_source,
                "page_type": page_type,
                "error_message": last_error_msg or f"Échec téléchargement après {retries} tentatives",
                "error_at": datetime.utcnow().isoformat(),
            }
            try:
                await asyncio.to_thread(_append_errors_pages_entry, domain, error_entry)
            except Exception as err:
                logger.error(f"[process_page_image] Erreur écriture errors_pages pour {domain}: {err}")
            return None

        # --- Étape 3 : Construction du filename ---
        filename = _build_page_filename(page_type, id_image_isi, url_image)

        # --- Étape 4 : Traitement image via ImageProcessor.process_image_page (T3) ---
        storage_subdir = os.path.join(_STORAGE_BASE, "images", domain)
        try:
            result = await asyncio.to_thread(
                self.image_processor.process_image_page,
                content,
                domain,
                storage_subdir,
                filename,
            )
        except Exception as e:
            error_entry = {
                "id_image_isi": id_image_isi,
                "url_image": url_image,
                "url_page_source": url_page_source,
                "page_type": page_type,
                "error_message": f"Traitement image échoué — {e}",
                "error_at": datetime.utcnow().isoformat(),
            }
            try:
                await asyncio.to_thread(_append_errors_pages_entry, domain, error_entry)
            except Exception as err:
                logger.error(f"[process_page_image] Erreur écriture errors_pages pour {domain}: {err}")
            return None

        # result keys: main_path, thumb_path, filename, width, height, format, file_size
        # Le filename peut avoir été corrigé par _process_image_internal (ex: webp→png)
        resolved_filename = result["filename"]

        # --- Étape 5 : Conversion chemins absolus → relatifs (parité _save_to_manifest) ---
        main_abs = result["main_path"]
        thumb_abs = result["thumb_path"]

        domain_prefix = os.path.join(_STORAGE_BASE, "images", domain) + os.sep
        main_rel = main_abs[len(domain_prefix):] if main_abs.startswith(domain_prefix) else main_abs
        thumb_rel = thumb_abs[len(domain_prefix):] if thumb_abs.startswith(domain_prefix) else thumb_abs

        # --- Étape 6 : Construction de l'entrée manifest ---
        manifest_entry = {
            "id_image_isi": id_image_isi,
            "url_source": url_image,          # mapping wire url_image → manifest url_source
            "page_type": page_type,
            "url_page_source": url_page_source,
            "alt_text": alt_text,
            "main": main_rel,
            "thumb": thumb_rel,
            "filename": resolved_filename,
            "width": result["width"],
            "height": result["height"],
            "format": result["format"],
            "file_size": result["file_size"],
            "downloaded_at": datetime.utcnow().isoformat(),
        }

        # --- Étape 7 : Écriture atomique dans manifest_pages.json ---
        try:
            await asyncio.to_thread(_append_manifest_pages_entry, domain, manifest_entry)
        except Exception as e:
            # L'image est sauvée sur disque mais le manifest n'a pas pu être mis à jour.
            # On loggue l'erreur sans retourner None pour ne pas perdre l'info côté appelant.
            logger.error(
                f"[process_page_image] Image téléchargée ({resolved_filename}) mais manifest_pages non mis à jour pour {domain}: {e}"
            )

        logger.info(
            f"[process_page_image] OK : {resolved_filename} | {domain} | {result['width']}x{result['height']} | {result['file_size']} bytes"
        )
        return manifest_entry

    async def process_logo_download(self, payload: dict) -> Optional[dict]:
        """
        Telecharge et traite un logo fournisseur (chantier logo fournisseur, Task 2).

        Miroir de process_page_image, avec les particularites logo :
        - Pas de shape id_image_isi/page_type : le payload est {domaine, url_logo, key}.
        - Traitement via process_logo (Task 1, module-level dans image_processor.py) :
          SVG conserve verbatim, raster non flatten/non resize (passthrough).
        - Ecriture sur disque sous images/{domain}/logo/{filename}{extension}.
        - Entree manifest_logo.json dediee (cle de dedup : "key", pas "url_source").
        - content_hash = SHA-256 hex des octets ecrits sur disque (necessaire au
          cycle de vie MAJ cote BO, cf. plan chantier logo fournisseur).
        - Derive d'affichage 200x200 (etapes 3bis / 4bis) : ADDITIF, non bloquant,
          derriere ENABLE_LOGO_DERIVE (OFF par defaut). Le master n'est jamais
          touche ; un echec de derivation n'echoue pas le telechargement.

        Payload attendu :
        ```json
        {"domaine": "<str>", "url_logo": "<str>", "key": "<str>"}
        ```

        Returns:
            Dict correspondant a l'entree manifest logo inseree/remplacee, ou None
            en cas d'erreur (l'erreur est enregistree dans errors_logo.json).
        """
        domain = payload.get("domaine", "unknown")
        key = payload.get("key", "")
        url_logo = payload.get("url_logo", "")

        # --- Etape 1 : Telechargement HTTP (meme pattern que process_page_image) ---
        retries = 3
        timeout = aiohttp.ClientTimeout(total=30)
        content = None
        last_error_msg = None

        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    kwargs = {}
                    if self.proxy_url:
                        kwargs["proxy"] = self.proxy_url

                    async with session.get(url_logo, **kwargs) as response:
                        logger.info(f"[process_logo_download] Download status {url_logo}: {response.status}")
                        if response.status == 200:
                            content = await response.read()
                            break  # Telechargement reussi -> sortir de la boucle retry
                        else:
                            reason, _cat, _sev = _classify_http_error(response.status)
                            last_error_msg = reason
                            logger.warning(f"[process_logo_download] {reason}")
                            # 4xx permanentes -> pas de retry
                            if 400 <= response.status < 500 and response.status != 429:
                                break

            except Exception as e:
                reason, _cat, _sev = _classify_network_error(e)
                last_error_msg = reason
                logger.warning(f"[process_logo_download] {reason} (tentative {attempt + 1}/{retries})")
                await asyncio.sleep(attempt * 1)

        if content is None:
            error_entry = {
                "key": key,
                "url_logo": url_logo,
                "error_message": last_error_msg or f"Echec telechargement apres {retries} tentatives",
                "error_at": datetime.utcnow().isoformat(),
            }
            try:
                await asyncio.to_thread(_append_errors_logo_entry, domain, error_entry)
            except Exception as err:
                logger.error(f"[process_logo_download] Erreur ecriture errors_logo pour {domain}: {err}")
            return None

        # --- Etape 2 : Traitement logo-safe via process_logo (Task 1) ---
        filename_base = _build_logo_filename(key)
        try:
            result = await asyncio.to_thread(self.process_logo, content, domain, filename_base)
        except Exception as e:
            error_entry = {
                "key": key,
                "url_logo": url_logo,
                "error_message": f"Traitement logo echoue — {e}",
                "error_at": datetime.utcnow().isoformat(),
            }
            try:
                await asyncio.to_thread(_append_errors_logo_entry, domain, error_entry)
            except Exception as err:
                logger.error(f"[process_logo_download] Erreur ecriture errors_logo pour {domain}: {err}")
            return None

        # --- Etape 3 : Ecriture des octets hebergés sous images/{domain}/logo/ ---
        filename = f"{filename_base}{result['extension']}"
        logo_dir = os.path.join(_STORAGE_BASE, "images", domain, "logo")

        def _write_logo_file() -> None:
            os.makedirs(logo_dir, exist_ok=True)
            file_path = os.path.join(logo_dir, filename)
            with open(file_path, "wb") as f:
                f.write(result["bytes"])

        try:
            await asyncio.to_thread(_write_logo_file)
        except OSError as e:
            error_entry = {
                "key": key,
                "url_logo": url_logo,
                "error_message": f"Ecriture fichier logo echouee — {e}",
                "error_at": datetime.utcnow().isoformat(),
            }
            try:
                await asyncio.to_thread(_append_errors_logo_entry, domain, error_entry)
            except Exception as err:
                logger.error(f"[process_logo_download] Erreur ecriture errors_logo pour {domain}: {err}")
            return None

        # content_hash calcule sur les octets reellement heberges (passthrough SVG/raster)
        content_hash = hashlib.sha256(result["bytes"]).hexdigest()
        hosted_path = os.path.join("logo", filename)  # relatif au domaine, miroir main_rel des pages

        # --- Etape 3bis : derive d'affichage 200x200 (ADDITIF, non bloquant) ---
        # Relu AVANT l'ecriture de l'entree : _append_manifest_logo_entry REMPLACE
        # l'entree entiere et effacerait sinon un bloc pose par le backfill.
        try:
            derive_block = await asyncio.to_thread(
                _carry_over_logo_derive_block, domain, key, content_hash
            )
        except Exception as e:
            logger.warning(
                f"[process_logo_download] Relecture du bloc derive impossible pour {domain}/{key}: {e}"
            )
            derive_block = None

        if derive_block is None and _logo_derive_enabled():
            try:
                # Sur les octets REELLEMENT ECRITS, ceux dont content_hash est le sha256.
                # Les dimensions viennent de ``process_logo`` : le plafond de
                # surface du master ne coute donc aucune I/O supplementaire.
                derive_block = await _derive_and_write_logo(
                    domain, key, result["bytes"], content_hash,
                    master_width=result.get("width"),
                    master_height=result.get("height"),
                    master_format=result.get("format"),
                )
            except Exception as e:
                # Un echec de derivation ne doit JAMAIS faire echouer le
                # telechargement du master : c'est lui qui porte le content_hash de
                # tout le cycle de vie 4b.
                logger.error(
                    f"[process_logo_download] Derive logo echoue pour {domain}/{key} "
                    f"(master conserve) : {e}"
                )
                derive_block = None

        # --- Etape 4 : Construction + ecriture atomique de l'entree manifest_logo.json ---
        manifest_entry = {
            "key": key,
            "hosted_path": hosted_path,
            "format": result["format"],
            "width": result["width"],
            "height": result["height"],
            "content_hash": content_hash,
            "downloaded_at": datetime.utcnow().isoformat(),
        }

        try:
            await asyncio.to_thread(_append_manifest_logo_entry, domain, manifest_entry)
        except Exception as e:
            # Le logo est sauve sur disque mais le manifest n'a pas pu etre mis a jour.
            logger.error(
                f"[process_logo_download] Logo telecharge ({filename}) mais manifest_logo non mis a jour pour {domain}: {e}"
            )

        # --- Etape 4bis : enrichissement de l'entree avec le bloc derive -------
        # FUSION et pas append : l'entree master vient d'etre ecrite, on n'ajoute
        # que la cle du derive sans reecrire le reste (et sans imbriquer les
        # verrous : _append a rendu le sien avant cet appel).
        if derive_block is not None:
            try:
                await asyncio.to_thread(
                    _merge_manifest_logo_entry, domain, key,
                    {_LOGO_DERIVE_MANIFEST_KEY: derive_block},
                )
                manifest_entry[_LOGO_DERIVE_MANIFEST_KEY] = derive_block
            except Exception as e:
                logger.error(
                    f"[process_logo_download] Variantes derivees mais entree manifest "
                    f"non enrichie pour {domain}/{key} : {e}"
                )

        logger.info(
            f"[process_logo_download] OK : {filename} | {domain} | key={key} | {result['format']}"
        )
        return manifest_entry


# =============================================================================
# T6 — Chantier D : Pages images helpers (module-level)
# =============================================================================

def _detect_ext_from_url(url: str) -> str:
    """
    Détecte l'extension d'image depuis l'URL (chemin uniquement, sans query string).
    Retourne l'extension avec point (ex: ".jpg"). Fallback : ".jpg".
    Aligné sur la logique inline de download_and_process pour le flux FP.
    """
    parsed = urlparse(url)
    url_path = parsed.path.lower()
    if url_path.endswith('.png'):
        return '.png'
    elif url_path.endswith('.gif'):
        return '.gif'
    elif url_path.endswith('.webp'):
        return '.webp'
    elif url_path.endswith('.jpeg'):
        return '.jpg'
    elif url_path.endswith('.avif'):
        return '.jpg'  # MVP : pas de support AVIF natif PIL, fallback jpg
    else:
        return '.jpg'


def _build_page_filename(page_type: str, id_image_isi: int, url_image: str) -> str:
    """
    Construit le filename pour une image de page (pipeline Chantier D).

    Pattern : ``page-{page_type}-{id_image_isi}-{hash8}.{ext}``

    Aligne sur le pattern FP ``{slug}-{product_id}-{hash8}`` de _build_filename,
    avec les particularités pages :
    - Préfixe ``page-`` fixe (identifiant du pipeline)
    - ``hash8`` = 8 premiers hex de MD5(url_image) — cf. spec §9 (différent du SHA1 FP)
    - Extension détectée depuis l'URL via _detect_ext_from_url

    Args:
        page_type:    Type de page (ex: "savoir_faire", "produit", "accueil").
        id_image_isi: Identifiant numérique de l'image dans la BDD isi.
        url_image:    URL source de l'image (champ ``url_image`` du payload wire).

    Returns:
        Filename avec extension (ex: "page-savoir_faire-12345-ab12cd34.jpg").
    """
    # Sanitisation : interdit les caractères non-alphanumériques/tiret-bas pour
    # éviter les path traversal ou noms de fichier invalides depuis un message RabbitMQ malformé.
    page_type = re.sub(r'[^a-z0-9_]', '_', page_type.lower())
    hash8 = hashlib.md5(url_image.encode()).hexdigest()[:8]
    ext = _detect_ext_from_url(url_image)
    return f"page-{page_type}-{id_image_isi}-{hash8}{ext}"


# =============================================================================
# T6 — Chantier D : manifest_pages.json helpers (module-level, async-compatible)
# =============================================================================

def _load_manifest_pages_file(domain: str) -> dict:
    """
    Lit ``manifest_pages.json`` depuis ``{_STORAGE_BASE}/images/{domain}/``.

    Retourne ``{"pages_images": [], "last_updated": None}`` si le fichier est
    absent, vide, ou corrompu (JSON invalide). Ne lève jamais d'exception.

    Note : appelé en synchrone ; pour l'utiliser depuis un contexte async,
    faire ``await asyncio.to_thread(_load_manifest_pages_file, domain)``.
    """
    manifest_path = os.path.join(_STORAGE_BASE, "images", domain, "manifest_pages.json")
    empty = {"pages_images": [], "last_updated": None}
    if not os.path.exists(manifest_path):
        return empty
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return empty
        return json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Could not read manifest_pages {manifest_path}: {e}")
        return empty


def _save_manifest_pages_file(domain: str, manifest: dict) -> None:
    """
    Écrit ``manifest_pages.json`` de façon atomique :
    tempfile + os.replace (résistant aux crashs et NFS).

    Met à jour ``manifest["last_updated"]`` au timestamp UTC ISO courant avant
    l'écriture. Le caller n'a pas besoin de le mettre à jour lui-même.

    Note : appelé en synchrone depuis ``_append_manifest_pages_entry`` (sous lock) ;
    pour l'utiliser depuis un contexte async sans lock, faire
    ``await asyncio.to_thread(_save_manifest_pages_file, domain, manifest)``.
    """
    manifest_dir = os.path.join(_STORAGE_BASE, "images", domain)
    manifest_path = os.path.join(manifest_dir, "manifest_pages.json")
    os.makedirs(manifest_dir, exist_ok=True)

    # Copie défensive pour éviter de muter le dict du caller en cas d'exception
    manifest = dict(manifest)
    manifest["last_updated"] = datetime.utcnow().isoformat()

    fd, tmp_path = tempfile.mkstemp(dir=manifest_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            tmp_f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
        os.replace(tmp_path, manifest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _append_manifest_pages_entry(domain: str, entry: dict) -> None:
    """
    Ajoute ou remplace une entrée dans ``manifest_pages.json`` sous lock NFS.

    Logique :
    - Acquiert ``nfs_lock(manifest_pages.json)``
    - Charge le manifest courant
    - Cherche une entrée existante avec ``url_source == entry["url_source"]``
    - Si trouvée → replace_idx (remplace en place, préserve l'ordre)
    - Si non trouvée → append
    - Sauvegarde atomiquement via ``_save_manifest_pages_file``

    Args:
        domain: Domaine cible (ex: "fournisseur-x.fr").
        entry:  Dict complet d'une entrée pages_images (clés : id_image_isi,
                url_source, page_type, url_page_source, alt_text, main, thumb,
                filename, width, height, format, file_size, downloaded_at).
    """
    from image_download_service.core.nfs_lock import nfs_lock

    manifest_path = os.path.join(_STORAGE_BASE, "images", domain, "manifest_pages.json")

    # Fix 2026-05-19 : créer le dossier domain avant d'acquérir le lock NFS.
    # nfs_lock fait os.mkdir(path+'.nfslock') qui échoue si le parent n'existe pas
    # (cas d'un domaine traité pour la 1ère fois). Symétrique au fix de
    # _append_errors_pages_entry — même cause racine.
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    try:
        with nfs_lock(manifest_path):
            manifest = _load_manifest_pages_file(domain)
            pages = manifest.get("pages_images", [])

            # Recherche d'un doublon sur url_source (replace_idx logic)
            replace_idx = next(
                (i for i, e in enumerate(pages) if e.get("url_source") == entry.get("url_source")),
                None
            )
            if replace_idx is not None:
                pages[replace_idx] = entry
            else:
                pages.append(entry)

            manifest["pages_images"] = pages
            _save_manifest_pages_file(domain, manifest)
    except Exception as e:
        # Log + return (pas de re-raise) : le caller (_process_page_image) gère
        # déjà l'erreur dans son propre try/except — symétrie avec _append_errors_pages_entry.
        logger.error(f"Could not write manifest_pages for {domain}: {e}")


# =============================================================================
# T6 — Chantier D : errors_pages.json helpers (module-level, mirror manifest)
# =============================================================================

def _load_errors_pages_file(domain: str) -> list:
    """
    Lit ``errors_pages.json`` depuis ``{_STORAGE_BASE}/images/{domain}/``.

    Retourne ``[]`` si le fichier est absent, vide, ou corrompu.
    Ne lève jamais d'exception.
    """
    errors_path = os.path.join(_STORAGE_BASE, "images", domain, "errors_pages.json")
    if not os.path.exists(errors_path):
        return []
    try:
        with open(errors_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return []
        return json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Could not read errors_pages {errors_path}: {e}")
        return []


def _save_errors_pages_file(domain: str, errors: list) -> None:
    """
    Écrit ``errors_pages.json`` de façon atomique :
    tempfile + os.replace (résistant aux crashs et NFS).

    Note : appelé en synchrone sous lock depuis ``_append_errors_pages_entry``.
    """
    errors_dir = os.path.join(_STORAGE_BASE, "images", domain)
    errors_path = os.path.join(errors_dir, "errors_pages.json")
    os.makedirs(errors_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=errors_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            tmp_f.write(json.dumps(errors, indent=2, ensure_ascii=False))
        os.replace(tmp_path, errors_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _append_errors_pages_entry(domain: str, error_entry: dict) -> None:
    """
    Ajoute une entrée dans ``errors_pages.json`` sous lock NFS (spec §9.6).

    Contrairement au manifest, les erreurs ne sont pas dédupliquées :
    chaque échec est enregistré indépendamment (append-only).

    Shape attendue de ``error_entry`` :
    ```json
    {
        "id_image_isi": <int>,
        "url_image": "<str>",
        "url_page_source": "<str>",
        "page_type": "<str>",
        "error_message": "<str>",
        "error_at": "<UTC ISO timestamp>"
    }
    ```

    Args:
        domain:      Domaine cible (ex: "fournisseur-x.fr").
        error_entry: Dict d'erreur structuré (voir shape ci-dessus).
    """
    from image_download_service.core.nfs_lock import nfs_lock

    errors_path = os.path.join(_STORAGE_BASE, "images", domain, "errors_pages.json")

    # Fix 2026-05-19 : créer le dossier domain avant d'acquérir le lock NFS.
    # nfs_lock fait os.mkdir(path+'.nfslock') qui échoue si le parent n'existe pas
    # (cas d'un domaine traité pour la 1ère fois). Sans ce makedirs, les workers
    # loggent "Could not write errors_pages" et perdent silencieusement les erreurs
    # → Phase 4 BO polling timeout car aucun GET /pages/{domain}/errors ne remonte.
    os.makedirs(os.path.dirname(errors_path), exist_ok=True)

    try:
        with nfs_lock(errors_path):
            errors_list = _load_errors_pages_file(domain)
            errors_list.append(error_entry)
            _save_errors_pages_file(domain, errors_list)
    except Exception as e:
        logger.error(f"Could not write errors_pages for {domain}: {e}")





# =============================================================================
# Chantier logo fournisseur (Task 2) — helpers module-level, miroir pages
# =============================================================================

def _build_logo_filename(key: str) -> str:
    """
    Construit le nom de fichier (sans extension) derive de ``key`` pour un logo.

    Pattern : ``logo-{slug(key)}``. Sanitisation : interdit tout caractere hors
    [A-Za-z0-9_-] pour eviter path traversal / noms de fichier invalides depuis
    un message RabbitMQ malformé (meme logique defensive que _build_page_filename).
    """
    slug = re.sub(r'[^A-Za-z0-9_-]', '_', key)
    return f"logo-{slug}"


def _load_manifest_logo_file(domain: str) -> dict:
    """
    Lit ``manifest_logo.json`` depuis ``{_STORAGE_BASE}/images/{domain}/logo/``.

    Retourne ``{"logos": [], "last_updated": None}`` si le fichier est absent,
    vide, ou corrompu (JSON invalide). Ne leve jamais d'exception.
    """
    manifest_path = os.path.join(_STORAGE_BASE, "images", domain, "logo", "manifest_logo.json")
    empty = {"logos": [], "last_updated": None}
    if not os.path.exists(manifest_path):
        return empty
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return empty
        return json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Could not read manifest_logo {manifest_path}: {e}")
        return empty


def _save_manifest_logo_file(domain: str, manifest: dict) -> None:
    """
    Ecrit ``manifest_logo.json`` de facon atomique : tempfile + os.replace.

    Met a jour ``manifest["last_updated"]`` au timestamp UTC ISO courant avant
    l'ecriture.
    """
    manifest_dir = os.path.join(_STORAGE_BASE, "images", domain, "logo")
    manifest_path = os.path.join(manifest_dir, "manifest_logo.json")
    os.makedirs(manifest_dir, exist_ok=True)

    manifest = dict(manifest)
    manifest["last_updated"] = datetime.utcnow().isoformat()

    fd, tmp_path = tempfile.mkstemp(dir=manifest_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            tmp_f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
        os.replace(tmp_path, manifest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _append_manifest_logo_entry(domain: str, entry: dict) -> None:
    """
    Pose l'entree MASTER dans ``manifest_logo.json`` sous lock NFS.

    Dedup sur ``entry["key"]`` (contrairement au manifest pages, dedup sur
    url_source) : une nouvelle ingestion du meme logo fournisseur (MAJ) met a jour
    l'entree existante EN PLACE (replace_idx), preservant l'ordre.

    Elle FUSIONNE, elle ne REMPLACE plus (correctif du 01/09/2026) : les cles
    qu'elle possede (``key``, ``hosted_path``, ``format``, ``width``, ``height``,
    ``content_hash``, ``downloaded_at``) gagnent toujours, et les cles qu'elle NE
    connait pas sont conservees.

    Pourquoi — MESURE du 01/09/2026 sous concurrence reelle (threads + barriere,
    ``_append(master)`` en parallele de ``_merge(derive)`` sur la MEME cle) : avec
    le REPLACE, le bloc ``derive`` etait absent a l'arrivee 8 fois sur 20 rondes
    (40 %) en course libre, et SYSTEMATIQUEMENT dans l'interleaving deterministe
    « le telechargement lit son report-over (rien) -> le backfill fusionne -> le
    telechargement fait son _append ». Avec la fusion : 0 fois sur 20.
    La cause n'est PAS le verrou (l'ecriture est bien serialisee) mais la
    semantique : ``_append`` ecrasait l'entree entiere avec un dict qui n'a jamais
    porte le derive, donc TOUT ce qu'un ecrivain concurrent avait ajoute entre
    temps disparaissait. La reprise faite par ``_carry_over_logo_derive_block`` ne
    peut rien y faire : elle lit AVANT la prise de verrou.

    Une exception : le bloc ``derive`` est ADRESSE AUX OCTETS du master (nommage
    par contenu, CDN immutable 30 jours). Il n'est donc conserve que s'il decrit
    ENCORE ce master — meme ``content_hash``, meme recette, fichiers presents.
    Sinon il est retire, exactement comme le faisait le REPLACE : conserver un
    bloc perime ferait publier au BO la vignette d'un AUTRE logo, ou une URL CDN
    en 404.
    """
    from image_download_service.core.nfs_lock import nfs_lock

    manifest_path = os.path.join(_STORAGE_BASE, "images", domain, "logo", "manifest_logo.json")

    # nfs_lock fait os.mkdir(path+'.nfslock') qui echoue si le parent n'existe pas
    # (cas d'un domaine traite pour la 1ere fois) — meme fix que pages/errors.
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    try:
        with nfs_lock(manifest_path):
            manifest = _load_manifest_logo_file(domain)
            logos = manifest.get("logos", [])

            replace_idx = next(
                (i for i, e in enumerate(logos) if e.get("key") == entry.get("key")),
                None
            )
            if replace_idx is not None:
                logos[replace_idx] = _merge_master_over_existing_entry(
                    domain, logos[replace_idx], entry
                )
            else:
                logos.append(entry)

            manifest["logos"] = logos
            _save_manifest_logo_file(domain, manifest)
    except Exception as e:
        logger.error(f"Could not write manifest_logo for {domain}: {e}")


def _merge_master_over_existing_entry(domain: str, existing, entry: dict) -> dict:
    """
    Applique l'entree MASTER sur l'entree existante sans detruire ce qu'elle ne
    connait pas (cf. :func:`_append_manifest_logo_entry`).

    Args:
        domain:   Domaine fournisseur (pour verifier les fichiers du derive).
        existing: Entree deja presente dans le manifest (peut etre n'importe quoi).
        entry:    Entree master a poser.

    Returns:
        dict: L'entree a ecrire.
    """
    if not isinstance(existing, dict):
        return entry  # entree corrompue : on repart de l'entree master seule

    merged = dict(existing)
    merged.update(entry)

    # Cle du derive : conservee UNIQUEMENT si elle decrit encore ce master. Si
    # l'appelant fournit lui-meme un bloc, c'est le sien qui vaut.
    if (_LOGO_DERIVE_MANIFEST_KEY in merged
            and _LOGO_DERIVE_MANIFEST_KEY not in entry):
        try:
            complete, _reason = _logo_derive_state(
                domain, merged, entry.get("content_hash") or ""
            )
        except Exception as exc:
            # Impossible de trancher (libvips absent, manifest inattendu...) : on
            # retombe sur le comportement historique, le retrait. Une ecriture de
            # master ne doit JAMAIS echouer a cause du derive.
            logger.warning(
                "[logo_derive] %s/%s : bloc derive non verifiable, retire : %s",
                domain, entry.get("key"), exc,
            )
            complete = False
        if not complete:
            merged.pop(_LOGO_DERIVE_MANIFEST_KEY, None)

    return merged


# =============================================================================
# Chantier logo fournisseur — DERIVE D'AFFICHAGE 200x200 (greffe de logo_derive)
# =============================================================================
# Le derive est ADDITIF : il ne touche jamais le master, ni ses octets, ni son
# ``content_hash`` (c'est ce sha256 qui porte tout le cycle de vie 4b cote BO).
# Il ecrit ses PNG dans un SOUS-repertoire dedie et ajoute UNE seule cle a
# l'entree manifest_logo.json.
#
# Pourquoi un sous-repertoire ``logo/d/`` :
#   - ``archiver.py`` et ``services/album_summary.py`` ne font un ``listdir``
#     qu'au niveau DOMAINE (jamais dans ``logo/``) : le sous-repertoire leur est
#     inerte ;
#   - le CDN nginx (image-cdn-service) sert n'importe quel ``.png`` sous
#     ``/images/`` quelle que soit la profondeur — sa regex de types autorises
#     n'est pas ancree sur un niveau, et seuls ``json|txt|log|sh|py|php`` sont
#     bloques : aucune modification de conf n'est necessaire ;
#   - ``rm -rf images/*/logo/d/`` est un rollback complet, sans trace, qui ne
#     touche pas un seul master.

#: Sous-repertoire des derives, sous ``images/{domain}/logo/``.
_LOGO_DERIVE_SUBDIR = "d"

#: Cle DEDIEE ajoutee a l'entree manifest_logo.json. Tout le derive est range
#: dessous : aucune cle existante n'est renommee ni deplacee, et
#: ``GET /logos/{domain}`` renvoie le manifest verbatim (aucun response_model),
#: donc ajouter cette cle ne casse aucun contrat de routeur.
_LOGO_DERIVE_MANIFEST_KEY = "derive"


def _logo_derive_enabled() -> bool:
    """
    Flag d'activation du derive DANS LE FLUX — OFF par defaut.

    Pattern maison (miroir ``ENABLE_PAGE_IMAGE_CONSUMER`` /
    ``ENABLE_LOGO_CONSUMER`` dans main.py) : la variable est lue a CHAQUE appel,
    pas au chargement du module, pour qu'un changement d'environnement n'exige
    pas de reimporter quoi que ce soit.

    N'affecte QUE le chemin telechargement. ``POST /logos/{domain}/derive`` reste
    disponible flag eteint : l'appel EST l'activation, et c'est lui qui porte le
    backfill des logos deja heberges.
    """
    return os.environ.get("ENABLE_LOGO_DERIVE", "false").lower() == "true"


def _import_logo_derive():
    """
    Importe ``logo_derive`` sous les deux noms possibles.

    ``image_download_service.core.logo_derive`` en production (le Dockerfile
    copie ``app/`` sous ce nom), ``core.logo_derive`` en test
    (``pythonpath = app tests``). Le module s'interdit tout import intra-paquet
    precisement pour supporter les deux contextes.
    """
    try:
        from image_download_service.core import logo_derive
    except ImportError:
        from core import logo_derive
    return logo_derive


# =============================================================================
# Chantier logo fournisseur — BORNES DE RESSOURCES (politique, pas recette)
# =============================================================================
# Ces bornes ne sont PAS dans ``logo_derive`` : elles dependent du GABARIT de la
# replica (docker-compose.yml : ``cpus: "1.0"``, ``memory: 2G``, 10 replicas), pas
# du contenu de l'image. Une recette doit rester deterministe et identique
# partout ; une borne de ressources se regle par deploiement. Elles sont donc
# lues dans l'environnement A CHAQUE APPEL (meme pattern que
# :func:`_logo_derive_enabled`).
#
# MESURES DU 01/09/2026 SUR CE POSTE (4 CPU, VmHWM = high-water mark du noyau,
# pas un echantillonnage), sur le PIRE format mesure — le GIF, seul format de la
# liste que libvips ne peut pas lire en flux, donc trame entiere materialisee :
#
#   master GIF      fichier    pic RSS    duree
#   16 Mpx          46 Ko      147 Mo     0,43 s
#   32 Mpx          77 Ko      226 Mo     0,64 s
#   64 Mpx         131 Ko      363 Mo     1,25 s
#  169 Mpx         288 Ko      800 Mo     2,39 s
#
# Et sous CONCURRENCE REELLE (n derivations simultanees d'un master GIF de
# 64 Mpx, dans un seul processus) :
#
#   n = 1  ->  383 Mo      n = 4  -> 1342 Mo
#   n = 2  ->  703 Mo      n = 6  -> 1969 Mo
#                          n = 8  -> 2460 a 2583 Mo (deux mesures)
#                                    limite de la replica : 2048 Mo
#
# Conclusion : 288 Ko sur le reseau suffisaient a reclamer 800 Mo, et 6 requetes
# simultanees suffisaient a l'OOM-kill — qui ne leve AUCUNE exception Python,
# donc le message RabbitMQ n'est jamais acquitte, requeue sans header x-death,
# n'atteint jamais MAX_RETRIES, ne part jamais en DLQ, et tue la replica
# suivante. C'etait le seul poison pill de la greffe.
#
# D'ou les deux bornes ci-dessous, complementaires :
#   (a) un PLAFOND DE SURFACE du master, evalue AVANT toute derivation et sans
#       decoder la moindre trame (les dimensions sont deja dans l'entree du
#       manifest) : au-dela, refus propre et TERMINAL ;
#   (b) un SEMAPHORE qui borne les derivations pyvips simultanees DANS LE
#       PROCESSUS (le seul plafond existant etait le ThreadPoolExecutor par
#       defaut de ``asyncio.to_thread``, soit min(32, os.cpu_count() + 4) — donc
#       8 ici, et davantage en prod ou ``os.cpu_count()`` rend les CPU de
#       l'HOTE et non le quota du conteneur).

#: Surface maximale du master, en pixels, au-dela de laquelle le derive est
#: REFUSE sans etre tente. 32 Mpx = 5657x5657, soit 226 Mo de pic mesure : deux
#: derivations simultanees a ce plafond coutent 2 x 184 Mo au-dessus du socle du
#: processus, soit moins de 20 % des 2 Go de la replica. Un logo reel n'approche
#: jamais cette taille ; le refus est visible (flag dedie) et rejouable
#: (``force=true``) si le porteur releve le plafond apres avoir mesure la
#: distribution reelle des 3762 masters.
_LOGO_DERIVE_MAX_MASTER_PIXELS_DEFAUT = 32000000

#: Derivations pyvips simultanees autorisees dans le processus. 2 sur une replica
#: a 1 CPU : au-dela on ne gagne pas de debit (pyvips est du CPU) et on multiplie
#: le pic memoire. Cf. la matrice de concurrence ci-dessus.
_LOGO_DERIVE_MAX_PARALLEL_DEFAUT = 2

#: Requetes HTTP de derivation acceptees EN ATTENTE au-dela des places
#: d'execution. Au-dela : 429 immediat, avec ``Retry-After``. Mieux vaut un 429
#: honnete qu'une requete qui expire chez l'appelant pendant que le serveur
#: continue d'ecrire.
_LOGO_DERIVE_MAX_QUEUE_DEFAUT = 4

#: Entrees DERIVEES au maximum par requete HTTP. Les entrees deja completes
#: (``skipped``) ne comptent PAS : elles ne coutent que deux ``stat`` et, si elles
#: comptaient, un domaine a plus d'entrees que le plafond ne progresserait JAMAIS
#: (chaque appel reconsommerait sa borne sur les memes entrees deja faites).
_LOGO_DERIVE_MAX_ENTRIES_DEFAUT = 50

#: Budget de temps par requete HTTP, en secondes. Verifie AVANT chaque entree :
#: le depassement maximal est donc d'une entree (~1 s au plafond de surface, plus
#: l'attente de verrou bornee ci-dessous).
_LOGO_DERIVE_TIME_BUDGET_DEFAUT = 15.0

#: Attente maximale du verrou NFS pour la FUSION du manifest, en secondes.
#: ``nfs_lock`` fige son ``max_wait`` a 30 s a la definition : sur le chemin HTTP
#: c'est plus long que le timeout de la plupart des appelants, qui abandonnent
#: pendant que le serveur ecrit encore. 3 s x 4 passes de fusion = 12 s au pire.
_LOGO_DERIVE_LOCK_TIMEOUT_DEFAUT = 3

#: Flag POLITIQUE (pas un flag de recette : il n'est pas dans
#: ``logo_derive.FLAG_ORDER``, et il ne peut pas y etre puisqu'il depend du
#: gabarit de la replica). Il n'a pas besoin d'etre dans ``BLOCKING_FLAGS`` : le
#: refus ne produit aucune variante, donc ``publishable`` est deja False.
_LOGO_DERIVE_FLAG_MASTER_TOO_LARGE = "master_too_large"


class LogoDeriveOverloaded(Exception):
    """Trop de derivations en cours : l'appelant doit rappeler plus tard (429)."""


def _env_int(name: str, defaut: int) -> int:
    """
    Lit un entier STRICTEMENT POSITIF d'environnement, sans jamais lever.

    Une valeur illisible OU nulle OU negative retombe sur le defaut, et le dit :
    ces bornes protegent la replica, une desactivation par typo (``=0``) ne doit
    pas passer en silence — et ``Semaphore(0)`` serait un blocage definitif.
    """
    brut = os.environ.get(name)
    if brut is None:
        return defaut
    try:
        value = int(str(brut).strip())
    except (TypeError, ValueError):
        logger.warning("[logo_derive] %s=%r illisible, defaut %r", name, brut, defaut)
        return defaut
    if value <= 0:
        logger.warning("[logo_derive] %s=%r non positif, defaut %r", name, brut, defaut)
        return defaut
    return value


def _env_float(name: str, defaut: float) -> float:
    """Idem :func:`_env_int`, pour un flottant (budget de temps)."""
    brut = os.environ.get(name)
    if brut is None:
        return defaut
    try:
        value = float(str(brut).strip())
    except (TypeError, ValueError):
        logger.warning("[logo_derive] %s=%r illisible, defaut %r", name, brut, defaut)
        return defaut
    if value <= 0:
        logger.warning("[logo_derive] %s=%r non positif, defaut %r", name, brut, defaut)
        return defaut
    return value


def _logo_derive_max_master_pixels() -> int:
    return _env_int("LOGO_DERIVE_MAX_MASTER_PIXELS", _LOGO_DERIVE_MAX_MASTER_PIXELS_DEFAUT)


def _logo_derive_max_parallel() -> int:
    return _env_int("LOGO_DERIVE_MAX_PARALLEL", _LOGO_DERIVE_MAX_PARALLEL_DEFAUT)


def _logo_derive_max_queue() -> int:
    return _env_int("LOGO_DERIVE_MAX_QUEUE", _LOGO_DERIVE_MAX_QUEUE_DEFAUT)


def _logo_derive_max_entries() -> int:
    return _env_int("LOGO_DERIVE_MAX_ENTRIES", _LOGO_DERIVE_MAX_ENTRIES_DEFAUT)


def _logo_derive_time_budget() -> float:
    return _env_float("LOGO_DERIVE_TIME_BUDGET_S", _LOGO_DERIVE_TIME_BUDGET_DEFAUT)


def _logo_derive_lock_timeout() -> int:
    return _env_int("LOGO_DERIVE_LOCK_TIMEOUT_S", _LOGO_DERIVE_LOCK_TIMEOUT_DEFAUT)


class _LogoDeriveGate:
    """
    Deux compteurs, une seule raison d'etre : ne jamais laisser le processus
    depasser son gabarit memoire.

    - ``semaphore`` borne les derivations pyvips SIMULTANEES. Le consumer et
      l'endpoint le partagent, et tous deux ATTENDENT dessus : une derivation qui
      patiente ne coute rien, une derivation de trop coute la replica.
    - ``admis`` borne les REQUETES HTTP (en cours + en attente). Au-dela, l'appel
      est refuse tout de suite en 429 plutot que de gonfler une file invisible.
      Le consumer n'est PAS soumis a cette borne : un message peut attendre, il
      n'a pas de client au bout du fil.
    """

    def __init__(self, max_parallel: int, max_admis: int):
        self.max_parallel = max_parallel
        self.max_admis = max_admis
        self.semaphore = asyncio.Semaphore(max_parallel)
        self.admis = 0
        #: derivations qui tiennent OU attendent le semaphore. Il ne sert qu'a
        #: savoir si le gate est au repos, donc reconstructible sans perdre de
        #: comptabilite ni liberer un attendeur sur un semaphore abandonne.
        self.en_cours = 0

    def admettre(self) -> None:
        """Reserve une place de requete, ou refuse. Sans ``await`` : atomique."""
        if self.admis >= self.max_admis:
            raise LogoDeriveOverloaded(
                "derivations saturees (%d requetes admises au maximum)" % self.max_admis
            )
        self.admis += 1

    def liberer(self) -> None:
        self.admis = max(0, self.admis - 1)


#: Un gate PAR BOUCLE D'EVENEMENTS. Un ``asyncio.Semaphore`` se lie a la boucle
#: qui l'utilise en premier (``_LoopBoundMixin``) et leve « bound to a different
#: event loop » ailleurs : un singleton de module casserait la suite de tests, qui
#: ouvre une boucle par test. La cle est faible, la boucle fermee est collectee.
_LOGO_DERIVE_GATES = weakref.WeakKeyDictionary()


def _logo_derive_gate() -> "_LogoDeriveGate":
    """Le gate de la boucle courante, cree a la demande."""
    loop = asyncio.get_running_loop()
    voulu = (_logo_derive_max_parallel(),
             _logo_derive_max_parallel() + _logo_derive_max_queue())
    gate = _LOGO_DERIVE_GATES.get(loop)
    if gate is None:
        gate = _LogoDeriveGate(*voulu)
        _LOGO_DERIVE_GATES[loop] = gate
        return gate
    # Reconstruction si l'environnement a change — mais seulement au repos, sinon
    # on perdrait la comptabilite des places deja prises.
    if ((gate.max_parallel, gate.max_admis) != voulu
            and gate.admis == 0 and gate.en_cours == 0):
        gate = _LogoDeriveGate(*voulu)
        _LOGO_DERIVE_GATES[loop] = gate
    return gate


def _logo_derive_dir(domain: str) -> str:
    """Repertoire absolu des derives d'un domaine."""
    return os.path.join(_STORAGE_BASE, "images", domain, "logo", _LOGO_DERIVE_SUBDIR)


def _logo_derive_variant_path(domain: str, filename: str) -> str:
    """
    Resout le chemin absolu d'une variante et REFUSE tout nom compose.

    ``filename`` vient de ``logo_derive`` (slug borne a ``[A-Za-z0-9_-]``) OU du
    manifest relu sur disque : dans le second cas c'est une DONNEE, et elle sert
    ici a construire un chemin d'ECRITURE. Un seul segment est tolere.
    """
    if (not filename or filename in (".", "..")
            or "/" in filename or "\\" in filename
            or os.path.basename(filename) != filename):
        raise ValueError("nom de variante invalide : %r" % (filename,))
    return os.path.join(_logo_derive_dir(domain), filename)


def _logo_master_path(domain: str, hosted_path: str) -> str:
    """
    Resout le chemin absolu du master depuis ``hosted_path`` (relatif au domaine,
    ex. ``logo/logo-acme_fr.png``) et REFUSE tout chemin sortant de
    ``images/{domain}/logo/``.

    Meme raison que ci-dessus : ``hosted_path`` est relu du manifest, et il sert
    ici a OUVRIR un fichier.
    """
    domain_dir = os.path.join(_STORAGE_BASE, "images", domain)
    logo_dir = os.path.normpath(os.path.join(domain_dir, "logo"))
    candidate = os.path.normpath(os.path.join(domain_dir, hosted_path or ""))
    if os.path.dirname(candidate) != logo_dir:
        raise ValueError("hosted_path hors de images/{domain}/logo : %r" % (hosted_path,))
    return candidate


#: Nombre de passes de fusion (1 ecriture + verification, puis reprises).
#: MESURE du 01/09 sur ce depot : ``NFSLock`` n'est PAS exclusif. Son
#: ``_write_info`` cree ``info.json`` puis ecrit dedans ; un concurrent qui lit ce
#: fichier de 0 octet prend un ``JSONDecodeError``, et le ``except`` de
#: ``_is_stale`` conclut « stale » — donc SUPPRIME un verrou pris a l'instant.
#: Chaque suppression enchaine ensuite des liberations en cascade (le premier
#: proprietaire rmdir le verrou du suivant). 6 threads x 30 prises sur un meme
#: chemin : exclusion violee 8 fois, 2 threads simultanement dans la section
#: critique. Consequence pour un manifest : perte de mise a jour silencieuse.
#: On ne corrige pas ``nfs_lock.py`` ici (il est partage par les flux FP et pages,
#: c'est une decision du porteur) ; on rend CETTE fusion convergente : elle relit
#: apres coup et reprend si son patch n'a pas survecu.
_MANIFEST_MERGE_ATTEMPTS = 4


def _logo_patch_survived(domain: str, key: str, expected: dict) -> bool:
    """Le patch est-il present sur disque apres l'ecriture ? (verification hors verrou)"""
    logos = _load_manifest_logo_file(domain).get("logos") or []
    if not isinstance(logos, list):
        return False
    entry = next(
        (e for e in logos if isinstance(e, dict) and e.get("key") == key),
        None
    )
    if not entry:
        return False
    return all(entry.get(k) == v for k, v in expected.items())


def _merge_manifest_logo_entry(domain: str, key: str, patch: dict,
                               attempts: int = _MANIFEST_MERGE_ATTEMPTS) -> dict:
    """
    FUSIONNE ``patch`` dans l'entree ``key`` de manifest_logo.json.

    Trois differences assumees avec :func:`_append_manifest_logo_entry`, qui reste
    inchangee (d'autres appels en dependent) :

    1. Elle FUSIONNE au lieu de REMPLACER : les autres cles de l'entree visee et
       les autres entrees du manifest sont preservees telles quelles. C'est ce qui
       permet d'ajouter le bloc derive sans reecrire les champs du master.
    2. Elle RELEVE l'exception au lieu de l'avaler. Un enrichissement qui echoue
       en silence produirait un endpoint qui repond 200 sans avoir rien ecrit —
       et donc un trou que personne ne verrait.
    3. Elle prend le verrou NFS UNE SEULE fois par passe, ici, et appelle ensuite
       ``_load_``/``_save_`` qui ne verrouillent pas. Ne JAMAIS l'imbriquer avec
       ``_append_manifest_logo_entry`` : ``NFSLock`` est un ``os.mkdir`` NON
       reentrant, l'imbrication attendrait tout le timeout puis n'ecrirait rien.
    4. Elle borne son attente de verrou (``LOGO_DERIVE_LOCK_TIMEOUT_S``, 3 s par
       defaut) au lieu des 30 s de ``nfs_lock``. C'est le chemin HTTP : un
       appelant qui abandonne pendant que le serveur ecrit encore conclut a un
       echec sur un appel qui a reussi. Le depassement leve, donc il est VISIBLE
       (``manifest_non_fusionne``) et le pilote rappelle.

    Elle VERIFIE ensuite son ecriture et reprend si le patch n'a pas survecu,
    parce que le verrou n'est pas exclusif (cf. :data:`_MANIFEST_MERGE_ATTEMPTS`).

    Args:
        domain:   Domaine fournisseur.
        key:      Cle de l'entree a enrichir (cle de dedup du manifest logo).
        patch:    Cles a poser/ecraser dans cette entree.
        attempts: Passes maximum (ecriture + verification).

    Returns:
        dict: L'entree fusionnee telle qu'ecrite.

    Raises:
        KeyError:   Aucune entree ne porte cette cle (rien a enrichir).
        ValueError: Manifest structurellement inattendu.
        Exception:  Toute defaillance d'ecriture (verrou, disque plein, ...), ou
                    un patch qui ne survit pas apres ``attempts`` passes.
    """
    from image_download_service.core.nfs_lock import nfs_lock

    manifest_path = os.path.join(_STORAGE_BASE, "images", domain, "logo", "manifest_logo.json")

    # nfs_lock fait os.mkdir(path+'.nfslock') qui echoue si le parent n'existe pas
    # (meme fix que pages/errors/append).
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    # Le patch tel qu'il ressortira du JSON : sans ce passage, un tuple dans le
    # patch relirait en liste et declencherait des reprises pour rien.
    expected = json.loads(json.dumps(patch))
    lock_timeout = _logo_derive_lock_timeout()

    for attempt in range(1, max(1, attempts) + 1):
        with nfs_lock(manifest_path, max_wait=lock_timeout):
            manifest = _load_manifest_logo_file(domain)
            logos = manifest.get("logos", [])
            if not isinstance(logos, list):
                raise ValueError(
                    "manifest_logo corrompu pour %s : 'logos' n'est pas une liste" % domain
                )

            target_idx = next(
                (i for i, e in enumerate(logos)
                 if isinstance(e, dict) and e.get("key") == key),
                None
            )
            if target_idx is None:
                raise KeyError("aucune entree manifest_logo pour key=%r sur %s" % (key, domain))

            merged = dict(logos[target_idx])
            merged.update(patch)
            logos[target_idx] = merged

            manifest["logos"] = logos
            _save_manifest_logo_file(domain, manifest)

        # Verification HORS verrou : un ecrivain concurrent qui a obtenu le meme
        # verrou peut avoir reecrit le fichier depuis notre relecture.
        if _logo_patch_survived(domain, key, expected):
            return merged

        logger.warning(
            "manifest_logo %s/%s : patch perdu (passe %d/%d), reprise",
            domain, key, attempt, max(1, attempts),
        )
        time.sleep(0.02 + random.random() * 0.05)  # desynchronise les concurrents

    raise RuntimeError(
        "fusion manifest_logo perdue pour key=%r sur %s apres %d passes"
        % (key, domain, max(1, attempts))
    )


def _write_logo_derive_variants(domain: str, variants: list) -> list:
    """
    Ecrit les variantes sous ``images/{domain}/logo/d/`` et decrit ce qui a ete
    ecrit.

    Ecriture atomique (tempfile + ``os.replace`` dans le MEME repertoire) : le
    CDN nginx a un ``open_file_cache`` de 30 s, il memoriserait un PNG tronque
    pendant 30 secondes sans moyen de purge.

    ``chmod 0644`` explicite : ``mkstemp`` cree en 0600, et le conteneur
    image-cdn-service (nginx:alpine) fait tourner ses workers sous
    l'utilisateur ``nginx`` — un derive en 0600 serait servi en 403 alors que le
    master, ecrit par ``open()``, herite du umask (0644).

    Args:
        domain:   Domaine fournisseur.
        variants: ``derive_logo(...)["variants"]``.

    Returns:
        list: Un descripteur par variante ecrite, SANS les octets, avec ``path``
        relatif au domaine (separateur ``/`` : il sert a construire une URL CDN).

    Raises:
        ValueError / OSError: nom de variante invalide, ou echec d'ecriture.
    """
    if not variants:
        return []

    derive_dir = _logo_derive_dir(domain)
    os.makedirs(derive_dir, exist_ok=True)

    written = []
    for item in variants:
        filename = (item or {}).get("filename")
        payload = (item or {}).get("bytes")
        target_path = _logo_derive_variant_path(domain, filename)
        if not payload:
            raise ValueError("variante %r sans octets" % (filename,))

        fd, tmp_path = tempfile.mkstemp(dir=derive_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as tmp_f:
                tmp_f.write(payload)
            os.chmod(tmp_path, 0o644)
            os.replace(tmp_path, target_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        written.append({
            "variant": item.get("variant"),
            "filename": filename,
            "path": "/".join(("logo", _LOGO_DERIVE_SUBDIR, filename)),
            "width": item.get("width"),
            "height": item.get("height"),
            "format": item.get("format"),
            "file_size": len(payload),
        })

    return written


def _build_logo_derive_block(content_hash: str, derive_result: dict, written: list) -> dict:
    """
    Construit le bloc ``derive`` de l'entree manifest.

    ``publishable`` est calcule ICI, une fois : la publication se decide sur
    ``BLOCKING_FLAGS`` SEUL (cf. logo_derive), et un consommateur qui chercherait
    une sous-chaine dans une colonne CSV laisserait passer en silence tout flag
    bloquant ajoute plus tard.
    """
    logo_derive = _import_logo_derive()
    metrics = derive_result.get("metrics") or {}
    flags = list(metrics.get("flags") or [])
    blocking = [f for f in flags if f in logo_derive.BLOCKING_FLAGS]

    return {
        "recipe": metrics.get("recipe") or logo_derive.RECIPE,
        "source_hash": content_hash,
        "generated_at": datetime.utcnow().isoformat(),
        "dir": "/".join(("logo", _LOGO_DERIVE_SUBDIR)),
        "variants": written,
        "metrics": metrics,
        "blocking_flags": blocking,
        "publishable": bool(written) and not blocking,
        "error": derive_result.get("error"),
    }


def _logo_derive_state(domain: str, entry: dict, content_hash: str) -> Tuple[bool, str]:
    """
    Evalue les DEUX conditions d'idempotence du derive d'une entree.

    Un derive n'est « deja fait » que si le bloc manifest EST la ET decrit des
    fichiers PRESENTS. Se fier au seul fichier laisserait un manifest non enrichi
    devenir un trou permanent que le rejeu ne repare pas ; se fier au seul
    manifest annoncerait au BO des URL CDN qui renvoient 404.

    Un bloc qui porte une ``error`` n'est JAMAIS complet — c'est le discriminant
    entre le REFUS et la DEFAILLANCE, et il est disponible a cout nul :

      - un REFUS de la recette (``svg_text``, ``svg_too_complex``,
        ``ink_too_small``, ``master_too_large``...) a ``error is None``. Il ne
        produit aucune variante, mais c'est un etat COMPLET et terminal : le
        rejeu doit le laisser ``skipped``, sinon le backfill re-derive
        indefiniment les logos que la recette refuse ;
      - une DEFAILLANCE (``derivation_failed``) a ``error`` renseigne. Elle
        produit EXACTEMENT LA MEME FORME (``variants == []`` + ``metrics``
        porteur de ``flags``), et sans ce test elle etait donc conclue COMPLETE :
        une panne TRANSITOIRE devenait un trou PERMANENT que ni le rejeu, ni un
        re-telechargement ne reparaient (mesure du 01/09/2026, panne pyvips
        injectee puis RETIREE : passe 1 -> created ; passe 2, panne disparue ->
        skipped ; passe 3 -> skipped ; 0 variante sur disque. Seul ``force``
        outrepassait encore l'idempotence). Un pilote de backfill qui boucle
        « jusqu'a ce que tout soit skipped » concluait au succes sur un domaine
        sans vignette.

    Returns:
        (complet, raison). ``raison`` nomme la condition qui manque.

    Note:
        Un ``content_hash`` vide (entree legacy) rend toute conclusion impossible
        ici : la fonction repond ``source_hash_different``. C'est a l'appelant de
        rappeler cette evaluation avec le hash du master REELLEMENT lu — c'est ce
        que fait :func:`_derive_logo_entry`, sans quoi ces entrees ne
        convergeraient jamais vers ``skipped``.
    """
    block = entry.get(_LOGO_DERIVE_MANIFEST_KEY)
    if not isinstance(block, dict):
        return False, "bloc_manifest_absent"
    if not content_hash or block.get("source_hash") != content_hash:
        return False, "source_hash_different"

    if block.get("error") is not None:
        # Defaillance, pas refus : le rejeu doit la reprendre (cf. docstring).
        return False, "derivation_en_echec"

    logo_derive = _import_logo_derive()
    if block.get("recipe") != logo_derive.RECIPE:
        return False, "recette_differente"

    variants = block.get("variants")
    if not isinstance(variants, list):
        return False, "bloc_manifest_incomplet"

    if not variants:
        # Refus legitime : aucune variante, mais ``error is None`` (verifie
        # ci-dessus). Etat COMPLET.
        metrics = block.get("metrics")
        if isinstance(metrics, dict) and "flags" in metrics:
            return True, "refus_sans_variante"
        return False, "bloc_manifest_incomplet"

    for item in variants:
        filename = (item or {}).get("filename") if isinstance(item, dict) else None
        if not filename:
            return False, "bloc_manifest_incomplet"
        try:
            path = _logo_derive_variant_path(domain, filename)
        except ValueError:
            return False, "bloc_manifest_incomplet"
        if not os.path.isfile(path):
            return False, "fichier_absent"

    return True, "complet"


def _carry_over_logo_derive_block(domain: str, key: str, content_hash: str) -> Optional[dict]:
    """
    Relit le bloc derive deja pose sur l'entree ``key`` et ne le rend que s'il est
    encore valable pour ``content_hash`` (fichiers presents compris).

    Raison d'etre — la course « telechargement APRES backfill » :
    ``_append_manifest_logo_entry`` REMPLACE l'entree entiere. Sans cette
    relecture, un re-telechargement effacerait les cles du derive pose par le
    backfill, et flag eteint rien ne les reposerait. Le nommage etant adresse par
    contenu, un bloc dont le ``source_hash`` vaut encore ``content_hash`` decrit
    exactement les fichiers que la derivation reproduirait : le reprendre est
    exact, et gratuit (145 ms de pyvips economises).

    Un ``source_hash`` different signifie que le master a change : le bloc est
    perime et doit disparaitre, sinon le BO afficherait une vignette derivee
    d'autres octets.
    """
    logos = _load_manifest_logo_file(domain).get("logos") or []
    if not isinstance(logos, list):
        return None

    entry = next(
        (e for e in logos if isinstance(e, dict) and e.get("key") == key),
        None
    )
    if not entry:
        return None

    complete, _reason = _logo_derive_state(domain, entry, content_hash)
    return entry.get(_LOGO_DERIVE_MANIFEST_KEY) if complete else None


def _master_is_svg(content: bytes, master_format: Optional[str]) -> bool:
    """
    Dit si le master est un SVG — donc HORS du plafond de surface.

    Un SVG n'a pas de surface : ses dimensions declarees peuvent valoir
    20000x20000 alors que le rendu est borne a ``MAX_WORK_EDGE`` (2000 px) par la
    recette, qui a par ailleurs ses propres plafonds (``MAX_SVG_CONTENT_BYTES``,
    refus de complexite de librsvg). Lui appliquer un plafond de PIXELS refuserait
    des logos parfaitement derivables.

    L'exemption a ete VERIFIEE, y compris sur le cas qui aurait pu la trahir — un
    SVG qui ENVELOPPE un bitmap (``svg_wraps_raster``), que la recette route vers
    la branche RASTER. Mesures du 01/09/2026 (VmHWM) :
      - SVG vectoriel declarant 30000x30000 : 57 Mo, 0,11 s ;
      - SVG de 1,05 Mo enveloppant un data: URI de 169 Mpx : 99 Mo, 0,16 s.
    Le rendu SVG est mis a l'echelle A LA SOURCE (librsvg), la trame entiere n'est
    jamais materialisee : contrairement au GIF, l'exposition memoire ne suit pas la
    surface declaree. Le plafond d'OCTETS de la recette suffit donc pour cette
    branche.

    Meme heuristique que ``process_logo`` (10 premiers octets) en repli, quand le
    format n'est pas connu de l'appelant.
    """
    if isinstance(master_format, str) and master_format.strip().lower() == "svg":
        return True
    header = content[:10] if content else b""
    return b'<svg' in header or b'<?xml' in header


def _master_pixel_count(content: bytes, master_width, master_height) -> Optional[int]:
    """
    Surface du master en pixels, SANS decoder la moindre trame.

    Args:
        master_width / master_height: dimensions telles que ``process_logo`` les a
            deja ecrites dans l'entree du manifest. C'est la source normale : elle
            ne coute pas un octet d'I/O.

    Returns:
        int: la surface, ou ``None`` si elle reste inconnue — auquel cas on ne
        refuse rien (une inconnue n'est pas un motif de refus).

    Note:
        Le repli lit l'EN-TETE avec pyvips, pour les entrees legacy sans
        dimensions — c'est-a-dire exactement celles que le backfill des 3762
        domaines va lire.

        P18 — POURQUOI PAS PILLOW ICI. Le repli lisait l'en-tete avec
        ``PIL.Image.open``. Mesure : au-dela de 2 x ``MAX_IMAGE_PIXELS``
        (178 956 970 px), Pillow LEVE ``DecompressionBombError`` des l'ouverture,
        le ``except`` concluait « surface inconnue », et une inconnue ne refusant
        rien, le master partait en derivation. Un GIF de 475 Ko et 400 Mpx passait
        donc SANS le moindre flag, coutait 1 840 Mo de pic RSS et 7,94 s, et
        ressortait ``publishable=True`` : le poison pill complet et silencieux sur
        une replica de 2 048 Mo. Le garde de Pillow transformait la seule mesure
        capable d'arreter une bombe en aveu d'ignorance. pyvips lit l'en-tete d'un
        fichier de 400 Mpx sans aucun garde et sans decoder de trame.
    """
    try:
        largeur = int(master_width)
        hauteur = int(master_height)
        if largeur > 0 and hauteur > 0:
            return largeur * hauteur
    except (TypeError, ValueError):
        pass

    if not content:
        return None
    try:
        import pyvips as _pyvips
        # access="sequential" : lecture en flux, l'en-tete suffit a donner les
        # dimensions et aucune trame n'est decodee.
        sonde = _pyvips.Image.new_from_buffer(content, "", access="sequential")
        largeur, hauteur = sonde.width, sonde.height
        if largeur > 0 and hauteur > 0:
            return largeur * hauteur
    except Exception:
        # Un format que pyvips ne sait pas ouvrir ne sera pas derivable non plus :
        # la surface reste inconnue et le refus, s'il doit venir, viendra de la
        # recette elle-meme.
        return None
    return None


def _logo_derive_policy_refusal_block(content_hash: str, flag: str,
                                      master_width, master_height,
                                      detail: str) -> dict:
    """
    Bloc de REFUS de politique : meme forme qu'un refus de recette, ``error`` a
    ``None``.

    Pourquoi ``error is None`` : c'est le discriminant que
    :func:`_logo_derive_state` utilise pour distinguer un etat COMPLET d'une
    defaillance a rejouer (cf. sa docstring). Un master trop grand le restera au
    rejeu : le refus doit etre TERMINAL, sinon chaque passe de backfill repaierait
    la lecture du master pour rien. Il redevient rejouable par ``force=true``, ce
    qui est exactement ce qu'il faut apres un relevement du plafond.

    Le flag est AUSSI pose dans ``blocking_flags``, alors qu'il n'appartient pas a
    ``logo_derive.BLOCKING_FLAGS`` : la greffe documente que « la publication se
    decide sur BLOCKING_FLAGS SEUL », donc un consommateur qui suit ce contrat a
    la lettre doit y trouver le motif. Sans cela il lirait une liste vide sur un
    bloc non publiable.

    Les cles de ``metrics`` sont celles de ``derive_logo`` : le BO remplit ses
    colonnes depuis la reponse, elles ne doivent pas manquer selon le chemin.
    """
    logo_derive = _import_logo_derive()

    def _entier(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return {
        "recipe": logo_derive.RECIPE,
        "source_hash": content_hash,
        "generated_at": datetime.utcnow().isoformat(),
        "dir": "/".join(("logo", _LOGO_DERIVE_SUBDIR)),
        "variants": [],
        "metrics": {
            "recipe": logo_derive.RECIPE,
            "libvips_version": getattr(logo_derive, "LIBVIPS_VERSION", "unknown"),
            "source_hash": content_hash,
            "surface": "unknown",
            "flags": [flag],
            "fill_pct": 0,
            "ratio_x100": 0,
            "master_width": _entier(master_width),
            "master_height": _entier(master_height),
            "ink_bbox": [0, 0, 0, 0],
            "alpha_ratio": 0.0,
            "ink_on_white": 0.0,
            "ink_on_black": 0.0,
            "is_light": False,
            "refus_politique": detail,
        },
        "blocking_flags": [flag],
        "publishable": False,
        "error": None,
    }


async def _derive_and_write_logo(domain: str, key: str, content: bytes,
                                 content_hash: str,
                                 master_width=None, master_height=None,
                                 master_format: Optional[str] = None) -> dict:
    """
    Derive les vignettes 200x200 des octets ``content`` et les ecrit sur disque.

    ``derive_logo`` est appele dans ``asyncio.to_thread`` : pyvips est du CPU
    synchrone et la replica n'a qu'1 CPU partage avec le consumer.

    DEUX BORNES DE RESSOURCES sont appliquees ici, et ici seulement, pour couvrir
    d'un coup le chemin telechargement et le chemin endpoint :

      1. PLAFOND DE SURFACE du master. Evalue sur les dimensions DEJA connues
         (entree du manifest), donc sans un octet d'I/O ni une trame decodee. Au
         dela : refus propre, terminal, ``error is None`` (cf.
         :func:`_logo_derive_policy_refusal_block`). Mesure du 01/09 : un GIF de
         169 Mpx pese 288 Ko et coute 800 Mo de pic RSS — le seul poison pill de
         la greffe.
      2. SEMAPHORE sur les derivations pyvips simultanees. On ATTEND (on ne refuse
         pas) : c'est le refus cote endpoint qui produit le 429, pas ici, car le
         consumer n'a personne au bout du fil.

    Args:
        content:       Octets REELLEMENT heberges (ceux dont ``content_hash`` est
                       le sha256), jamais les octets telecharges bruts.
        content_hash:  sha256 hex du master — il nomme les fichiers.
        master_width / master_height / master_format: ce que l'appelant sait deja
                       du master (entree manifest ou retour de ``process_logo``).

    Returns:
        dict: Le bloc ``derive`` a fusionner dans l'entree manifest.

    Raises:
        Exception: import, ecriture disque ou construction du bloc. ``derive_logo``
        lui-meme ne leve jamais : un refus ou une defaillance de recette revient
        dans ``metrics["flags"]`` / ``error``, pas en exception. C'est a l'appelant
        de decider de la politique (le flux loggue et continue, l'endpoint
        rapporte).
    """
    plafond = _logo_derive_max_master_pixels()
    if not _master_is_svg(content, master_format):
        pixels = _master_pixel_count(content, master_width, master_height)
        if pixels is not None and pixels > plafond:
            logger.warning(
                "[logo_derive] %s key=%s : master refuse, %d pixels > plafond %d",
                domain, key, pixels, plafond,
            )
            return _logo_derive_policy_refusal_block(
                content_hash, _LOGO_DERIVE_FLAG_MASTER_TOO_LARGE,
                master_width, master_height,
                "surface %d px > plafond %d px" % (pixels, plafond),
            )

    logo_derive = _import_logo_derive()
    gate = _logo_derive_gate()
    gate.en_cours += 1
    try:
        async with gate.semaphore:
            derive_result = await asyncio.to_thread(
                logo_derive.derive_logo, content, key, content_hash
            )
            written = await asyncio.to_thread(
                _write_logo_derive_variants, domain, derive_result.get("variants") or []
            )
    finally:
        gate.en_cours = max(0, gate.en_cours - 1)
    return _build_logo_derive_block(content_hash, derive_result, written)


def _logo_derive_report_item(key: str, status: str, reason: str,
                             block: Optional[dict] = None,
                             error: Optional[str] = None) -> dict:
    """
    Normalise une ligne du rapport de ``derive_logos_for_domain``.

    Porte les metriques de ``derive_logo`` VERBATIM : le BO doit pouvoir remplir
    ses colonnes depuis la reponse, sans relire manifest_logo.json.
    """
    block = block if isinstance(block, dict) else {}
    metrics = block.get("metrics") if isinstance(block.get("metrics"), dict) else {}
    return {
        "key": key,
        "status": status,
        "reason": reason,
        "recipe": block.get("recipe"),
        "source_hash": block.get("source_hash"),
        "variants": block.get("variants") or [],
        "metrics": metrics,
        "flags": list(metrics.get("flags") or []),
        "blocking_flags": block.get("blocking_flags") or [],
        "publishable": bool(block.get("publishable")),
        "error": error if error is not None else block.get("error"),
    }


async def _derive_logo_entry(domain: str, entry: dict, force: bool = False) -> dict:
    """
    Derive UNE entree de manifest_logo.json (a la demande).

    Lit le master sur disque (il est intact : rien ne le purge), verifie que ses
    octets sont bien ceux annonces, derive, ecrit les variantes, puis FUSIONNE le
    bloc dans l'entree.

    Args:
        force: ignorer l'idempotence et regenerer.

    Returns:
        dict: ligne de rapport (``status`` dans created / skipped / failed).
        Ne leve pas : chaque defaillance devient une ligne ``failed`` motivee.
    """
    entry = entry if isinstance(entry, dict) else {}
    key = entry.get("key")
    if not key:
        return _logo_derive_report_item("", "failed", "entree_sans_cle")

    hosted_path = entry.get("hosted_path")
    if not hosted_path:
        return _logo_derive_report_item(key, "failed", "entree_sans_hosted_path")

    recorded_hash = entry.get("content_hash") or ""

    # --- Idempotence : les DEUX conditions (bloc manifest ET fichiers) --------
    # ``_logo_derive_state`` fait un ``os.path.isfile`` PAR VARIANTE : c'est de
    # l'I/O synchrone, et sur NFS un stat coute cher. Il part donc en thread comme
    # tout le reste (pyvips, ecriture, fusion). Mesure du 01/09/2026 : 60 entrees
    # deja derivees, stat NFS simule a 10 ms, 2e passage qui ne fait RIEN ->
    # 612 ms de blocage CONTINU de la boucle (1 seul reveil du chien de garde),
    # celle qui porte les heartbeats aio_pika du LogoConsumer et ``/health``.
    # Apres : 1 ms de blocage maximal, 117 reveils, meme duree totale.
    if not force:
        complete, reason = await asyncio.to_thread(
            _logo_derive_state, domain, entry, recorded_hash
        )
        if complete:
            return _logo_derive_report_item(
                key, "skipped", reason,
                block=entry.get(_LOGO_DERIVE_MANIFEST_KEY),
            )

    # --- Master ---------------------------------------------------------------
    try:
        master_path = _logo_master_path(domain, hosted_path)
    except ValueError as exc:
        return _logo_derive_report_item(key, "failed", "hosted_path_invalide", error=str(exc))

    def _read_master() -> bytes:
        with open(master_path, "rb") as f:
            return f.read()

    try:
        content = await asyncio.to_thread(_read_master)
    except OSError as exc:
        return _logo_derive_report_item(key, "failed", "master_illisible", error=str(exc))

    actual_hash = hashlib.sha256(content).hexdigest()
    if recorded_hash and actual_hash != recorded_hash:
        # Le nommage des derives est adresse par CONTENU et le CDN les declare
        # immutables 30 jours sans purge possible : deriver des octets qui ne sont
        # pas ceux que le BO connait publierait une URL intraçable. On refuse au
        # lieu de deviner.
        return _logo_derive_report_item(
            key, "failed", "master_hash_different",
            error="manifest=%s disque=%s" % (recorded_hash, actual_hash),
        )

    # --- Idempotence, 2e evaluation : entrees LEGACY sans content_hash --------
    # L'evaluation ci-dessus n'a rien pu conclure faute de hash de reference
    # (``_logo_derive_state`` exige un ``content_hash`` non vide). Maintenant que
    # le master est lu, ``actual_hash`` fournit cette reference.
    #
    # Sans ce second passage, une entree sans ``content_hash`` renvoie
    # ETERNELLEMENT ``created`` : elle n'acquiert jamais l'etat ``skipped``, et
    # un pilote de backfill qui boucle « jusqu'a ce que tout soit skipped » ne
    # s'arrete jamais (mesure : 5 appels consecutifs, 5 fois ``created``).
    # Ces entrees sont precisement la population visee par le rattrapage : les
    # logos heberges AVANT l'introduction de ``content_hash``.
    if not force and not recorded_hash:
        complete, reason = await asyncio.to_thread(
            _logo_derive_state, domain, entry, actual_hash
        )
        if complete:
            return _logo_derive_report_item(
                key, "skipped", reason,
                block=entry.get(_LOGO_DERIVE_MANIFEST_KEY),
            )

    # --- Derivation + ecriture des variantes ---------------------------------
    try:
        block = await _derive_and_write_logo(
            domain, key, content, actual_hash,
            master_width=entry.get("width"),
            master_height=entry.get("height"),
            master_format=entry.get("format"),
        )
    except LogoDeriveOverloaded as exc:
        # Ne peut venir que du gate ; on le rapporte tel quel plutot que de le
        # noyer dans ``derivation_echouee``, pour que le pilote sache rappeler.
        return _logo_derive_report_item(key, "failed", "derive_sature", error=str(exc))
    except Exception as exc:
        logger.error(
            "[logo_derive] %s key=%s : derivation/ecriture echouee : %s", domain, key, exc
        )
        return _logo_derive_report_item(key, "failed", "derivation_echouee", error=str(exc))

    # --- Fusion dans le manifest (RELEVE, contrairement a _append_...) -------
    try:
        await asyncio.to_thread(
            _merge_manifest_logo_entry, domain, key, {_LOGO_DERIVE_MANIFEST_KEY: block}
        )
    except Exception as exc:
        # Les PNG sont sur disque mais l'entree n'est pas enrichie : c'est
        # exactement le trou que l'idempotence a deux conditions repare au rejeu.
        # On le DIT, au lieu d'annoncer un succes.
        logger.error(
            "[logo_derive] %s key=%s : variantes ecrites mais manifest non fusionne : %s",
            domain, key, exc,
        )
        return _logo_derive_report_item(
            key, "failed", "manifest_non_fusionne", block=block, error=str(exc)
        )

    if block.get("error") is not None:
        # DEFAILLANCE de recette (``derivation_failed``), pas refus. Le bloc est
        # ecrit — il documente la panne et porte ``publishable=False`` — mais le
        # rapport doit dire ECHEC : annoncer ``created`` faisait lire un trou comme
        # un succes, et un pilote qui boucle « jusqu'a ce que tout soit skipped »
        # ne se serait JAMAIS arrete sur une panne permanente (l'entree ne devient
        # jamais ``skipped``, cf. :func:`_logo_derive_state`).
        return _logo_derive_report_item(
            key, "failed", "derivation_defaillante", block=block,
        )

    return _logo_derive_report_item(key, "created", "derive", block=block)


async def derive_logos_for_domain(domain: str, keys: Optional[List[str]] = None,
                                  force: bool = False) -> dict:
    """
    Derive a la demande les logos d'un domaine deja heberges.

    Sert les deux usages du chantier : le BACKFILL des 3762 domaines deja
    telecharges, et la VALIDATION (manuelle, cron 4b ou ponctuelle) qui veut la
    vignette et ses metriques immediatement.

    Les chemins sont resolus via ``_STORAGE_BASE`` (module), comme tout le reste
    de ce fichier.

    LE TRAVAIL EST BORNE PAR APPEL, par deux plafonds complementaires
    (``LOGO_DERIVE_MAX_ENTRIES``, ``LOGO_DERIVE_TIME_BUDGET_S``) :

      - sans ``keys``, TOUTES les entrees du manifest etaient traitees, et
        ``LogoDerivePayload.max_length=200`` ne contraint QUE ``keys`` : mesure du
        01/09/2026, 40 entrees en 3,44 s (86 ms/entree sur des logos minuscules),
        donc ~17 s pour 200 cles EN NOMINAL, sans aucun timeout serveur — et une
        seule prise de verrou sous contention coutait 29,3 s de plus ;
      - seules les entrees REELLEMENT DERIVEES comptent dans le plafond
        d'entrees. Une entree deja complete (``skipped``) ne coute que deux
        ``stat`` et, si elle comptait, un domaine ayant plus d'entrees que le
        plafond ne progresserait JAMAIS : chaque appel reconsommerait sa borne sur
        les memes entrees deja faites. Le budget de temps, lui, couvre TOUT, y
        compris un long balayage de ``skipped``.

    Ce qui reste a faire est dans la reponse (``remaining``, ``truncated``,
    ``stop_reason``) : le pilote de backfill rappelle, il n'a pas a deviner.

    Args:
        domain: Domaine fournisseur — deja valide par le routeur.
        keys:   Cles a traiter. Absent/vide : toutes les entrees du manifest
                (manifest_logo.json est une LISTE dedupliquee sur ``key``).
        force:  Regenerer meme si le derive est deja complet.

    Returns:
        dict: ``{domaine, recipe, manifest_entries, created[], skipped[],
        failed[], remaining[], truncated, stop_reason, counts{}}``. Chaque ligne
        porte les metriques de ``derive_logo``, pour que le BO remplisse ses
        colonnes SANS relire le manifest.

    Raises:
        LogoDeriveOverloaded: trop de derivations en cours dans ce processus. Le
            routeur en fait un 429 : mieux vaut un refus honnete qu'une file
            d'attente invisible qui expire chez l'appelant.
    """
    logo_derive = _import_logo_derive()
    gate = _logo_derive_gate()
    gate.admettre()
    try:
        manifest = await asyncio.to_thread(_load_manifest_logo_file, domain)

        logos = manifest.get("logos") or []
        if not isinstance(logos, list):
            logos = []
        entries = [e for e in logos if isinstance(e, dict)]

        report = {
            "domaine": domain,
            "recipe": logo_derive.RECIPE,
            "manifest_entries": len(entries),
            "created": [],
            "skipped": [],
            "failed": [],
        }

        if keys:
            by_key = {}
            for candidate in entries:
                candidate_key = candidate.get("key")
                if candidate_key and candidate_key not in by_key:
                    by_key[candidate_key] = candidate

            selected = []
            for wanted in list(dict.fromkeys(keys)):  # ordre d'appel, sans doublon
                if wanted in by_key:
                    selected.append(by_key[wanted])
                else:
                    report["failed"].append(
                        _logo_derive_report_item(wanted, "failed", "cle_inconnue")
                    )
            entries = selected

        max_entries = _logo_derive_max_entries()
        budget = _logo_derive_time_budget()
        debut = time.monotonic()
        derivees = 0
        stop_reason = None
        reste = []

        for index, entry in enumerate(entries):
            if derivees >= max_entries:
                stop_reason = "max_entries"
            elif (time.monotonic() - debut) >= budget:
                stop_reason = "time_budget"
            if stop_reason:
                reste = [
                    e.get("key") for e in entries[index:]
                    if isinstance(e, dict) and e.get("key")
                ]
                logger.info(
                    "[logo_derive] %s : borne atteinte (%s), %d entrees non traitees",
                    domain, stop_reason, len(reste),
                )
                break

            item = await _derive_logo_entry(domain, entry, force=force)
            report.setdefault(item["status"], []).append(item)
            if item["status"] != "skipped":
                derivees += 1

        # ``remaining`` / ``truncated`` / ``stop_reason`` sont ajoutes A COTE de
        # ``counts``, jamais DEDANS : la forme de ``counts`` est un contrat pour le
        # pilote (total/created/skipped/failed), et ``len(remaining)`` porte deja
        # le compte.
        report["remaining"] = reste
        report["truncated"] = bool(stop_reason)
        report["stop_reason"] = stop_reason
        report["counts"] = {
            "total": len(report["created"]) + len(report["skipped"]) + len(report["failed"]),
            "created": len(report["created"]),
            "skipped": len(report["skipped"]),
            "failed": len(report["failed"]),
        }
        return report
    finally:
        gate.liberer()


def _load_errors_logo_file(domain: str) -> list:
    """
    Lit ``errors_logo.json`` depuis ``{_STORAGE_BASE}/images/{domain}/logo/``.

    Retourne ``[]`` si le fichier est absent, vide, ou corrompu.
    """
    errors_path = os.path.join(_STORAGE_BASE, "images", domain, "logo", "errors_logo.json")
    if not os.path.exists(errors_path):
        return []
    try:
        with open(errors_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return []
        return json.loads(content)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Could not read errors_logo {errors_path}: {e}")
        return []


def _save_errors_logo_file(domain: str, errors: list) -> None:
    """
    Ecrit ``errors_logo.json`` de facon atomique : tempfile + os.replace.
    """
    errors_dir = os.path.join(_STORAGE_BASE, "images", domain, "logo")
    errors_path = os.path.join(errors_dir, "errors_logo.json")
    os.makedirs(errors_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=errors_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            tmp_f.write(json.dumps(errors, indent=2, ensure_ascii=False))
        os.replace(tmp_path, errors_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _append_errors_logo_entry(domain: str, error_entry: dict) -> None:
    """
    Ajoute une entree dans ``errors_logo.json`` sous lock NFS (append-only,
    pas de dedup — miroir _append_errors_pages_entry).
    """
    from image_download_service.core.nfs_lock import nfs_lock

    errors_path = os.path.join(_STORAGE_BASE, "images", domain, "logo", "errors_logo.json")

    os.makedirs(os.path.dirname(errors_path), exist_ok=True)

    try:
        with nfs_lock(errors_path):
            errors_list = _load_errors_logo_file(domain)
            errors_list.append(error_entry)
            _save_errors_logo_file(domain, errors_list)
    except Exception as e:
        logger.error(f"Could not write errors_logo for {domain}: {e}")
