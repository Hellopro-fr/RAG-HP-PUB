import shutil
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

class Archiver:
    def __init__(self, storage_base: str = "/app/storage"):
        """
        Archiver for packaging domain images.
        - storage_base: Root storage path
        - Images are at: {storage_base}/images/{domain}/...
        - Archives go to: {storage_base}/archives/{domain}.tar.gz
        """
        self.storage_base = storage_base
        self.images_base = os.path.join(storage_base, "images")
        self.archive_base = os.path.join(storage_base, "archives")
        os.makedirs(self.archive_base, exist_ok=True)

    async def create_archive(self, domain: str) -> str:
        """
        Creates a .tar.gz archive for the given domain.
        Archives the entire domain folder (including produit-2 and produit-3).
        Returns the path to the archive.
        """
        domain_dir = os.path.join(self.images_base, domain)
        if not os.path.exists(domain_dir):
            raise ValueError(f"No images found for domain: {domain}")

        # Archive name: {domain}.tar.gz in /archives/
        base_name = os.path.join(self.archive_base, domain)
        
        loop = asyncio.get_running_loop()
        # shutil.make_archive is blocking, run in executor
        archive_path = await loop.run_in_executor(
            None,
            lambda: shutil.make_archive(base_name, 'gztar', root_dir=self.images_base, base_dir=domain)
        )
        
        logger.info(f"Created archive for {domain} at {archive_path}")
        return archive_path

    async def list_archives(self) -> list:
        if not os.path.exists(self.archive_base):
            return []
        return [f for f in os.listdir(self.archive_base) if f.endswith('.tar.gz')]
