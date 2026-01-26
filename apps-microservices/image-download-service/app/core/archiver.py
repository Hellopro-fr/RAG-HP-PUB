import shutil
import os
import json
import logging
import asyncio
import aiofiles
import tarfile
import tempfile
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

class Archiver:
    def __init__(self, storage_base: str = "/app/storage"):
        """
        Archiver for packaging domain images with incremental/delta support.
        
        Structure:
        - Images: {storage_base}/images/{domain}/produit-2/...
        - Manifest: {storage_base}/images/{domain}/manifest.json
        - Archives: {storage_base}/archives/{domain}_delta_{timestamp}.tar.gz
        """
        self.storage_base = storage_base
        self.images_base = os.path.join(storage_base, "images")
        self.archive_base = os.path.join(storage_base, "archives")
        os.makedirs(self.archive_base, exist_ok=True)

    async def get_manifest(self, domain: str) -> Optional[Dict]:
        """Load the manifest for a domain."""
        manifest_path = os.path.join(self.images_base, domain, "manifest.json")
        
        if not os.path.exists(manifest_path):
            return None
            
        try:
            async with aiofiles.open(manifest_path, 'r') as f:
                content = await f.read()
                return json.loads(content) if content else None
        except Exception as e:
            logger.error(f"Error reading manifest for {domain}: {e}")
            return None

    async def save_manifest(self, domain: str, manifest: Dict):
        """Save the manifest for a domain."""
        manifest_path = os.path.join(self.images_base, domain, "manifest.json")
        
        try:
            async with aiofiles.open(manifest_path, 'w') as f:
                await f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Error saving manifest for {domain}: {e}")

    async def get_unsynced_products(self, domain: str) -> List[Dict]:
        """Get list of products that haven't been synced yet."""
        manifest = await self.get_manifest(domain)
        
        if not manifest or "products" not in manifest:
            return []
        
        return [p for p in manifest["products"] if not p.get("synced", False)]

    async def mark_products_synced(self, domain: str, product_ids: List[str] = None):
        """
        Mark products as synced after successful download by BO.
        If product_ids is None, mark ALL products as synced.
        """
        manifest = await self.get_manifest(domain)
        
        if not manifest or "products" not in manifest:
            raise ValueError(f"No manifest found for domain: {domain}")
        
        synced_count = 0
        for product in manifest["products"]:
            if product_ids is None or product["id_produit"] in product_ids:
                product["synced"] = True
                product["synced_at"] = datetime.now().isoformat()
                synced_count += 1
        
        manifest["last_sync"] = datetime.now().isoformat()
        await self.save_manifest(domain, manifest)
        
        logger.info(f"Marked {synced_count} products as synced for {domain}")
        return synced_count

    async def create_delta_archive(self, domain: str) -> Optional[Dict]:
        """
        Creates a delta archive containing only unsynced products.
        
        Returns:
            dict: {
                "archive_path": "/path/to/archive.tar.gz",
                "product_count": 5,
                "product_ids": ["60001", "60002", ...],
                "manifest": { ... delta manifest ... }
            }
        """
        domain_dir = os.path.join(self.images_base, domain)
        if not os.path.exists(domain_dir):
            raise ValueError(f"No images found for domain: {domain}")
        
        # Get unsynced products
        unsynced = await self.get_unsynced_products(domain)
        
        if not unsynced:
            logger.info(f"No unsynced products for {domain}")
            return {
                "archive_path": None,
                "product_count": 0,
                "product_ids": [],
                "message": "All products already synced"
            }
        
        logger.info(f"Creating delta archive for {domain}: {len(unsynced)} products")
        
        # Create temp directory for delta files
        with tempfile.TemporaryDirectory() as temp_dir:
            delta_dir = os.path.join(temp_dir, domain)
            os.makedirs(delta_dir)
            
            # Copy only the files for unsynced products
            product_ids = []
            for product in unsynced:
                product_ids.append(product["id_produit"])
                
                for img in product.get("images", []):
                    # Copy main image
                    main_rel = img.get("main", "")
                    if main_rel:
                        src = os.path.join(domain_dir, main_rel)
                        dst = os.path.join(delta_dir, main_rel)
                        if os.path.exists(src):
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
                    
                    # Copy thumbnail
                    thumb_rel = img.get("thumb", "")
                    if thumb_rel:
                        src = os.path.join(domain_dir, thumb_rel)
                        dst = os.path.join(delta_dir, thumb_rel)
                        if os.path.exists(src):
                            os.makedirs(os.path.dirname(dst), exist_ok=True)
                            shutil.copy2(src, dst)
            
            # Create delta manifest
            delta_manifest = {
                "domain": domain,
                "created_at": datetime.now().isoformat(),
                "is_delta": True,
                "product_count": len(unsynced),
                "products": unsynced
            }
            
            # Write manifest to delta dir
            manifest_path = os.path.join(delta_dir, "manifest.json")
            with open(manifest_path, 'w') as f:
                json.dump(delta_manifest, f, indent=2, ensure_ascii=False)
            
            # Create archive
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"{domain}_delta_{timestamp}"
            archive_path = os.path.join(self.archive_base, f"{archive_name}.tar.gz")
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: shutil.make_archive(
                    os.path.join(self.archive_base, archive_name),
                    'gztar',
                    root_dir=temp_dir,
                    base_dir=domain
                )
            )
        
        logger.info(f"Created delta archive: {archive_path}")
        
        return {
            "archive_path": archive_path,
            "product_count": len(unsynced),
            "product_ids": product_ids,
            "manifest": delta_manifest
        }

    async def create_full_archive(self, domain: str) -> str:
        """
        Creates a full archive of all images for a domain.
        Use this for initial sync or disaster recovery.
        """
        domain_dir = os.path.join(self.images_base, domain)
        if not os.path.exists(domain_dir):
            raise ValueError(f"No images found for domain: {domain}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{domain}_full_{timestamp}"
        base_name = os.path.join(self.archive_base, archive_name)
        
        loop = asyncio.get_running_loop()
        archive_path = await loop.run_in_executor(
            None,
            lambda: shutil.make_archive(base_name, 'gztar', root_dir=self.images_base, base_dir=domain)
        )
        
        logger.info(f"Created full archive for {domain} at {archive_path}")
        return archive_path

    async def get_sync_status(self, domain: str) -> Dict:
        """Get sync status for a domain."""
        manifest = await self.get_manifest(domain)
        
        if not manifest:
            return {
                "domain": domain,
                "exists": False,
                "total_products": 0,
                "synced_products": 0,
                "unsynced_products": 0
            }
        
        products = manifest.get("products", [])
        synced = sum(1 for p in products if p.get("synced", False))
        
        return {
            "domain": domain,
            "exists": True,
            "total_products": len(products),
            "synced_products": synced,
            "unsynced_products": len(products) - synced,
            "last_updated": manifest.get("last_updated"),
            "last_sync": manifest.get("last_sync")
        }

    async def list_domains(self) -> List[str]:
        """List all domains with images."""
        if not os.path.exists(self.images_base):
            return []
        
        return [
            d for d in os.listdir(self.images_base)
            if os.path.isdir(os.path.join(self.images_base, d))
        ]

    async def get_recent_domains(self, hours: int = 6) -> List[Dict]:
        """
        Get domains that have been updated in the last X hours.
        Checks the manifest.json last_updated timestamp for each domain.
        
        Args:
            hours: Number of hours to look back (default 6)
            
        Returns:
            List of domains with activity info
        """
        from datetime import timedelta
        
        if not os.path.exists(self.images_base):
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_domains = []
        
        for domain in os.listdir(self.images_base):
            domain_path = os.path.join(self.images_base, domain)
            if not os.path.isdir(domain_path):
                continue
            
            manifest = await self.get_manifest(domain)
            if not manifest:
                continue
            
            last_updated_str = manifest.get("last_updated")
            if not last_updated_str:
                continue
            
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                if last_updated >= cutoff_time:
                    products = manifest.get("products", [])
                    unsynced = sum(1 for p in products if not p.get("synced", False))
                    
                    recent_domains.append({
                        "domain": domain,
                        "last_updated": last_updated_str,
                        "total_products": len(products),
                        "unsynced_products": unsynced,
                        "hours_ago": round((datetime.now() - last_updated).total_seconds() / 3600, 2)
                    })
            except ValueError:
                continue
        
        # Sort by most recent first
        return sorted(recent_domains, key=lambda x: x["last_updated"], reverse=True)

    async def list_archives(self) -> List[Dict]:
        """List all archives with metadata."""
        if not os.path.exists(self.archive_base):
            return []
        
        archives = []
        for f in os.listdir(self.archive_base):
            if f.endswith('.tar.gz'):
                path = os.path.join(self.archive_base, f)
                stat = os.stat(path)
                archives.append({
                    "filename": f,
                    "path": path,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
        
        return sorted(archives, key=lambda x: x["created_at"], reverse=True)

    async def cleanup_old_archives(self, domain: str = None, keep_latest: int = 3):
        """
        Remove old archives, keeping only the N most recent per domain.
        
        Args:
            domain: If specified, only cleanup this domain. Otherwise, all domains.
            keep_latest: Number of recent archives to keep per domain (default 3)
        
        Returns:
            Number of archives deleted
        """
        from datetime import timedelta
        
        if not os.path.exists(self.archive_base):
            return 0
        
        # Group archives by domain
        archives_by_domain = {}
        for f in os.listdir(self.archive_base):
            if not f.endswith('.tar.gz'):
                continue
            
            # Extract domain from filename (e.g., "tech-shop.com_delta_20260126_100000.tar.gz")
            parts = f.rsplit('_delta_', 1)
            if len(parts) < 2:
                parts = f.rsplit('_full_', 1)
            
            if len(parts) >= 1:
                dom = parts[0]
                
                if domain and dom != domain:
                    continue
                
                if dom not in archives_by_domain:
                    archives_by_domain[dom] = []
                
                path = os.path.join(self.archive_base, f)
                stat = os.stat(path)
                archives_by_domain[dom].append({
                    "path": path,
                    "filename": f,
                    "mtime": stat.st_mtime
                })
        
        # Clean up old archives
        deleted_count = 0
        for dom, archives in archives_by_domain.items():
            # Sort by modification time (newest first)
            archives.sort(key=lambda x: x["mtime"], reverse=True)
            
            # Delete archives beyond the keep_latest
            for archive in archives[keep_latest:]:
                try:
                    os.remove(archive["path"])
                    logger.info(f"Deleted old archive: {archive['filename']}")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {archive['filename']}: {e}")
        
        return deleted_count
