"""Tests pour album_actions."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from conftest import _patch_package_imports


def _setup(monkeypatch, tmp_path):
    _patch_package_imports(monkeypatch)
    images_base = tmp_path / "images"
    images_base.mkdir()
    return images_base


def _seed(images_base: Path, domain: str, products: list, last_updated="2026-04-26T10:00:00"):
    d = images_base / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"products": products, "last_updated": last_updated}))


def _img(filename, url="https://x/y.jpg"):
    return {"filename": filename, "url_source": url,
            "main": f"produit-2/0/0/0/{filename}", "thumb": f"produit-3/0/0/0/{filename}"}


def _create_files(domain_dir: Path, filename: str):
    for sub in ("produit-2", "produit-3"):
        p = domain_dir / sub / "0" / "0" / "0"
        p.mkdir(parents=True, exist_ok=True)
        (p / filename).write_bytes(b"x")


def test_delete_image_removes_files_and_manifest_entry(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "synced": True,
                                       "images": [_img("a.jpg"), _img("b.jpg")]}])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")

    from services.album_actions import delete_image
    asyncio.run(delete_image(str(tmp_path), "alpha.com", "1", "a.jpg"))

    # Fichiers a.* supprimés
    assert not (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "a.jpg").exists()
    assert not (images_base / "alpha.com" / "produit-3" / "0" / "0" / "0" / "a.jpg").exists()
    # b.jpg reste
    assert (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "b.jpg").exists()
    # Manifest mis à jour
    manifest = json.loads((images_base / "alpha.com" / "manifest.json").read_text())
    images = manifest["products"][0]["images"]
    assert len(images) == 1
    assert images[0]["filename"] == "b.jpg"


def test_delete_image_unknown_raises_filenotfound(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "images": []}])
    from services.album_actions import delete_image
    with pytest.raises(FileNotFoundError):
        asyncio.run(delete_image(str(tmp_path), "alpha.com", "1", "ghost.jpg"))


def test_delete_product_removes_all_and_manifest(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [
        {"id_produit": "1", "nom": "p1", "images": [_img("a.jpg"), _img("b.jpg")]},
        {"id_produit": "2", "nom": "p2", "images": [_img("c.jpg")]},
    ])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")
    _create_files(images_base / "alpha.com", "c.jpg")

    from services.album_actions import delete_product
    asyncio.run(delete_product(str(tmp_path), "alpha.com", "1"))

    assert not (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "a.jpg").exists()
    assert (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "c.jpg").exists()
    manifest = json.loads((images_base / "alpha.com" / "manifest.json").read_text())
    assert [p["id_produit"] for p in manifest["products"]] == ["2"]


def test_delete_product_unknown_raises(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [])
    from services.album_actions import delete_product
    with pytest.raises(FileNotFoundError):
        asyncio.run(delete_product(str(tmp_path), "alpha.com", "ghost"))


def test_redownload_product_calls_downloader_for_each_url(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "synced": True,
                                       "images": [_img("a.jpg", "https://x/a.jpg"),
                                                  _img("b.jpg", "https://x/b.jpg")]}])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")

    calls = []

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        calls.append(url)
        # Mirror real downloader : filename dérivé de l'URL (sha1[:8]).
        import hashlib
        fname = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8] + ".jpg"
        return {"status": "ok", "paths": {"main_path": str(images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / fname),
                                          "thumb_path": "/x", "filename": fname,
                                          "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    result = asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    assert sorted(calls) == ["https://x/a.jpg", "https://x/b.jpg"]
    assert result["downloaded"] == 2
    assert result["failed"] == 0


def test_redownload_image_unknown_filename_raises(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "images": []}])
    downloader = MagicMock()
    from services.album_actions import redownload_image, ManifestEntryMissingError
    with pytest.raises(ManifestEntryMissingError):
        asyncio.run(redownload_image(str(tmp_path), "alpha.com", "1", "ghost.jpg", downloader))


def test_redownload_product_partial_failure_returned_in_errors(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "synced": True,
                                       "images": [_img("a.jpg", "https://x/a"), _img("b.jpg", "https://x/b")]}])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        if "b" in url:
            return {"status": "error", "error": "404"}
        import hashlib
        fname = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8] + ".jpg"
        return {"status": "ok", "paths": {"main_path": "/x", "thumb_path": "/x",
                                          "filename": fname, "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    result = asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))
    assert result["downloaded"] == 1
    assert result["failed"] == 1
    assert len(result["errors"]) == 1


def test_lock_timeout_raises(tmp_path, monkeypatch):
    """Si le lock est occupé > 3s, on lève LockTimeoutError."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "images": []}])
    # Acquérir le lock dans un thread séparé puis appeler delete_product
    import core.nfs_lock as lk
    import threading, time
    manifest_path = str(images_base / "alpha.com" / "manifest.json")
    holder_done = threading.Event()
    def hold():
        with lk.nfs_lock(manifest_path):
            holder_done.wait(timeout=5)
    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.1)  # laisser le holder acquérir
    try:
        from services.album_actions import delete_product, LockTimeoutError
        with pytest.raises(LockTimeoutError):
            asyncio.run(delete_product(str(tmp_path), "alpha.com", "1"))
    finally:
        holder_done.set()
        t.join()
