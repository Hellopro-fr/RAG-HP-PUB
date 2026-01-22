import shutil
import os
import logging
import asyncio

logger = logging.getLogger(__name__)

class Archiver:
    def __init__(self, storage_base: str = "/app/storage/images", archive_base: str = "/app/storage/archives"):
        self.storage_base = storage_base
        self.archive_base = archive_base
        os.makedirs(self.archive_base, exist_ok=True)

    async def create_archive(self, domain: str) -> str:
        """
        Creates a .tar.gz archive for the given domain.
        Returns the path to the archive.
        """
        domain_dir = os.path.join(self.storage_base, domain)
        if not os.path.exists(domain_dir):
            raise ValueError(f"No images found for domain: {domain}")

        # Archive name: domain_timestamp.tar.gz
        # For simplicity, just domain.tar.gz or domain_latest.tar.gz
        # Or better: mimic crawler: just archive the folder
        base_name = os.path.join(self.archive_base, domain)
        
        loop = asyncio.get_running_loop()
        # shutil.make_archive is blocking, run in executor
        archive_path = await loop.run_in_executor(
            None,
            lambda: shutil.make_archive(base_name, 'gztar', root_dir=domain_dir)
        )
        
        logger.info(f"Created archive for {domain} at {archive_path}")
        return archive_path

    async def list_archives(self) -> list:
        return [f for f in os.listdir(self.archive_base) if f.endswith('.tar.gz')]
