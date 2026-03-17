"""
NFS-safe locking mechanism using os.mkdir() (atomic on NFS).

Unlike fcntl.flock which is process-local and doesn't work across containers
sharing an NFS volume, os.mkdir() is guaranteed atomic by POSIX — only one
process succeeds, others get FileExistsError.

Usage:
    from image_download_service.core.nfs_lock import nfs_lock

    with nfs_lock("/path/to/manifest.json"):
        # read-modify-write under exclusive lock
        ...
"""

import os
import json
import time
import socket
import logging

logger = logging.getLogger(__name__)

# Lock timeout: if a lock is older than this, consider it stale (seconds)
STALE_LOCK_TIMEOUT = 60

# Max wait time to acquire lock (seconds)
MAX_WAIT_TIME = 30

# Retry interval (seconds)
RETRY_INTERVAL = 0.1


class NFSLockError(Exception):
    """Raised when the lock cannot be acquired within the timeout."""
    pass


class NFSLock:
    """
    NFS-safe exclusive lock using os.mkdir().
    
    os.mkdir() is atomic on NFS — only one process can create a directory.
    A stale lock (from a crashed process) is automatically cleaned up
    after STALE_LOCK_TIMEOUT seconds.
    """
    
    def __init__(self, file_path: str, stale_timeout: int = STALE_LOCK_TIMEOUT, max_wait: int = MAX_WAIT_TIME):
        self.lock_dir = f"{file_path}.nfslock"
        self.info_file = os.path.join(self.lock_dir, "info.json")
        self.stale_timeout = stale_timeout
        self.max_wait = max_wait
        self._acquired = False
    
    def acquire(self):
        """Acquire the lock, waiting up to max_wait seconds."""
        start_time = time.time()
        
        while True:
            try:
                os.mkdir(self.lock_dir)
                # Lock acquired — write info for debugging
                self._write_info()
                self._acquired = True
                return
            except FileExistsError:
                # Lock exists — check if it's stale
                if self._is_stale():
                    logger.warning(f"Removing stale NFS lock: {self.lock_dir}")
                    self._force_remove()
                    continue
                
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed >= self.max_wait:
                    raise NFSLockError(
                        f"Could not acquire NFS lock {self.lock_dir} after {self.max_wait}s"
                    )
                
                time.sleep(RETRY_INTERVAL)
    
    def release(self):
        """Release the lock by removing the directory."""
        if self._acquired:
            self._force_remove()
            self._acquired = False
    
    def _write_info(self):
        """Write lock info for debugging and stale detection."""
        try:
            info = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "acquired_at": time.time(),
                "acquired_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(self.info_file, 'w') as f:
                json.dump(info, f)
        except Exception:
            pass  # Info file is best-effort, don't fail the lock
    
    def _is_stale(self) -> bool:
        """Check if the lock is stale (older than stale_timeout)."""
        try:
            # Try reading the info file first
            if os.path.exists(self.info_file):
                with open(self.info_file, 'r') as f:
                    info = json.load(f)
                acquired_at = info.get("acquired_at", 0)
                return (time.time() - acquired_at) > self.stale_timeout
            
            # No info file — check directory mtime
            stat = os.stat(self.lock_dir)
            return (time.time() - stat.st_mtime) > self.stale_timeout
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            # If we can't determine, assume stale to avoid deadlocks
            return True
    
    def _force_remove(self):
        """Force remove the lock directory and its contents."""
        try:
            if os.path.exists(self.info_file):
                os.unlink(self.info_file)
            os.rmdir(self.lock_dir)
        except FileNotFoundError:
            pass  # Already removed by another process
        except OSError as e:
            logger.error(f"Failed to remove NFS lock {self.lock_dir}: {e}")
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def nfs_lock(file_path: str, stale_timeout: int = STALE_LOCK_TIMEOUT, max_wait: int = MAX_WAIT_TIME) -> NFSLock:
    """
    Convenience function to create an NFSLock context manager.
    
    Usage:
        with nfs_lock("/path/to/manifest.json"):
            # exclusive access
            ...
    """
    return NFSLock(file_path, stale_timeout, max_wait)
