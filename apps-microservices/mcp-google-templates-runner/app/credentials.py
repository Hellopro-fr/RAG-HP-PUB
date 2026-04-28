from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class CredentialsStore:
    # mcp-gsc hardcodes this exact filename and searches for it in the process's
    # current working directory (os.getcwd()). analytics-mcp uses the standard
    # GOOGLE_APPLICATION_CREDENTIALS env var. Using this filename inside a
    # per-instance directory satisfies both: GSC finds it via cwd, GA finds it
    # via the env var that points at the same path.
    CRED_FILENAME = "service_account_credentials.json"

    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        os.chmod(self._base, 0o700)

    @staticmethod
    def _validate_id(instance_id: str) -> None:
        if (
            not instance_id
            or "/" in instance_id
            or "\\" in instance_id
            or "\x00" in instance_id
            or "%" in instance_id
            or instance_id.startswith(".")
        ):
            raise ValueError(f"invalid instance_id: {instance_id!r}")

    def path_for(self, instance_id: str) -> str:
        """Returns the per-instance directory (not a file). Callers spawn the
        child process with cwd=this so hardcoded-filename lookups succeed."""
        self._validate_id(instance_id)
        return str(self._base / instance_id)

    def credential_file_for(self, instance_id: str) -> str:
        return str(Path(self.path_for(instance_id)) / self.CRED_FILENAME)

    def write(self, instance_id: str, plaintext: str) -> str:
        """Create the per-instance directory (mode 0700) and write
        service_account_credentials.json inside (mode 0600). Returns the
        directory path — callers use it as the child process cwd."""
        dir_path = Path(self.path_for(instance_id))
        dir_path.mkdir(parents=True, exist_ok=True)
        os.chmod(dir_path, 0o700)
        file_path = dir_path / self.CRED_FILENAME
        fd = os.open(str(file_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, plaintext.encode("utf-8"))
        finally:
            os.close(fd)
        return str(dir_path)

    def shred(self, instance_id: str) -> None:
        dir_path = Path(self.path_for(instance_id))
        if not dir_path.exists():
            return
        file_path = dir_path / self.CRED_FILENAME
        if file_path.exists():
            # Best-effort shred. On tmpfs this is roughly equivalent to unlink
            # (no persistent media), but keep the call for defence in depth.
            try:
                subprocess.run(["shred", "-u", str(file_path)], check=False, timeout=5)
            except Exception:
                pass
            if file_path.exists():
                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass
        # Remove any other stray files inside then drop the dir.
        try:
            shutil.rmtree(dir_path, ignore_errors=True)
        except Exception:
            pass
