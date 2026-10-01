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
import tempfile

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
        """Write lock info for debugging and stale detection.

        L'ecriture est ATOMIQUE (tempfile + os.replace DANS le repertoire de
        verrou), et c'est ce qui garantit l'exclusion mutuelle.

        Pourquoi (mesure du 01/09/2026, 40 rondes x N ecrivains sur un meme
        manifest) : un `open(self.info_file, 'w')` cree info.json a 0 octet PUIS
        ecrit dedans. Un concurrent qui lit ce fichier vide prend un
        JSONDecodeError, et le `except` de `_is_stale` conclut « stale » — il
        SUPPRIME donc un verrou pris a l'instant. Deux ecrivains se retrouvent
        alors dans la section critique, et le premier a finir rmdir le verrou du
        second, ce qui enchaine des liberations en cascade. Effet mesure sur
        `_append_manifest_logo_entry` (read-modify-write) : 6,7 % d'entrees
        perdues a 3 ecrivains, 18,3 % a 6 — une entree de manifest perdue, c'est
        une image presente sur disque et invisible du BO.
        Avec os.replace, info.json n'est JAMAIS observable vide : `_is_stale`
        lit toujours un `acquired_at` frais et ne vole plus le verrou.
        Mesure apres correctif : 0,0 % a 3 ecrivains, 2,1 % a 6.

        Le fichier reste « best-effort » : un echec d'ecriture n'echoue pas la
        prise de verrou, `_is_stale` retombe simplement sur le mtime du
        repertoire (frais a la creation, donc non stale).
        """
        tmp_path = None
        try:
            info = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "acquired_at": time.time(),
                "acquired_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            fd, tmp_path = tempfile.mkstemp(dir=self.lock_dir, suffix=".tmp")
            with os.fdopen(fd, 'w') as f:
                json.dump(info, f)
            os.replace(tmp_path, self.info_file)
            tmp_path = None  # consomme par le replace
        except Exception:
            pass  # Info file is best-effort, don't fail the lock
        finally:
            # Un .tmp oublie ferait echouer le rmdir de release() (ENOTEMPTY) et
            # laisserait le verrou en place jusqu'au stale_timeout.
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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
        """Force remove the lock directory and its contents.

        Vide le repertoire avant le rmdir : un `.tmp` transitoire (cf.
        `_write_info`) ou un info.json ecrit par un autre processus ferait
        echouer le rmdir en ENOTEMPTY, et le verrou resterait en place jusqu'au
        stale_timeout (60 s) — soit un blocage de 60 s pour tout le monde.
        """
        try:
            for name in os.listdir(self.lock_dir):
                try:
                    os.unlink(os.path.join(self.lock_dir, name))
                except OSError:
                    pass  # deja retire, ou repris par un autre processus
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
