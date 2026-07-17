import aiohttp
import aiofiles
import hashlib
import json
import os
import logging
import asyncio
import re
import tempfile
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


