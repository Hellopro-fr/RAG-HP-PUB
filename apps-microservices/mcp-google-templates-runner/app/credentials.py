from __future__ import annotations

import os
import subprocess
from pathlib import Path


class CredentialsStore:
    def __init__(self, base_dir: str):
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        os.chmod(self._base, 0o700)

    @staticmethod
    def _validate_id(instance_id: str) -> None:
        if "/" in instance_id or "\\" in instance_id or instance_id.startswith("."):
            raise ValueError(f"invalid instance_id: {instance_id!r}")

    def path_for(self, instance_id: str) -> str:
        self._validate_id(instance_id)
        return str(self._base / f"{instance_id}.json")

    def write(self, instance_id: str, plaintext: str) -> str:
        p = self.path_for(instance_id)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, plaintext.encode("utf-8"))
        finally:
            os.close(fd)
        return p

    def shred(self, instance_id: str) -> None:
        p = self.path_for(instance_id)
        if not os.path.exists(p):
            return
        # Best-effort shred. On tmpfs this is roughly equivalent to unlink
        # (no persistent media), but keep the call for defence in depth.
        try:
            subprocess.run(["shred", "-u", p], check=False, timeout=5)
        except Exception:
            pass
        if os.path.exists(p):
            os.remove(p)
