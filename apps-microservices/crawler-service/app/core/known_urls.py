"""A312 : ensemble SFPI actif transmis par le BO (POST /start) -> <job>/known_urls.json.

Le BO envoie `known_urls_gz` = base64(gzip(JSON liste de str)) et `known_urls_count`.
`prepare_known_urls_file` decode, controle, ecrit le fichier de facon atomique et rend
le chemin a passer au crawler Node (`--knownUrlsFile=<chemin>`), ou None.
Ne leve jamais : un ensemble inutilisable ne doit pas empecher la MAJ de demarrer.
"""
import base64
import gzip
import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

KNOWN_URLS_FILENAME = "known_urls.json"


def _decode_known_urls(known_urls_gz: str, known_urls_count: int) -> List[str]:
    raw = base64.b64decode(known_urls_gz, validate=True)
    urls = json.loads(gzip.decompress(raw).decode("utf-8"))
    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        raise ValueError("payload is not a JSON list of strings")
    if len(urls) != known_urls_count:
        raise ValueError(f"count mismatch: declared {known_urls_count}, decoded {len(urls)}")
    return urls


def _write_atomic(path: str, urls: List[str]) -> None:
    """Contenu complet dans un temporaire du meme dossier, puis os.replace."""
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(urls, fh, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _remove_if_present(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def prepare_known_urls_file(job_storage_path: str, known_urls_gz: Optional[str],
                            known_urls_count: Optional[int], is_restart: bool) -> Optional[str]:
    path = os.path.join(job_storage_path, KNOWN_URLS_FILENAME)
    try:
        if known_urls_gz is not None and known_urls_count is not None:
            urls = _decode_known_urls(known_urls_gz, known_urls_count)
            _write_atomic(path, urls)
            logger.info(f"known_urls: wrote {len(urls)} URLs to '{path}'")
            return os.path.abspath(path)
        if is_restart and os.path.isfile(path):
            logger.info(f"known_urls: restart keeps existing '{path}'")
            return os.path.abspath(path)
        if _remove_if_present(path):
            logger.info(f"known_urls: no injection requested, removed stale '{path}'")
        return None
    except Exception as exc:
        logger.warning(f"known_urls: injection skipped ({type(exc).__name__}: {exc})")
        try:
            _remove_if_present(path)
        except OSError:
            pass
        return None
