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


def _legacy_img(filename):
    """Image entry façon manifest v1 : pas de `url_source`."""
    return {"filename": filename,
            "main": f"produit-2/0/0/0/{filename}", "thumb": f"produit-3/0/0/0/{filename}"}


def test_redownload_product_legacy_v1_raises_legacy_error(tmp_path, monkeypatch):
    """Manifest v1 (toutes les images sans url_source) → LegacyManifestError sans rien casser."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "synced": True,
                                       "images": [_legacy_img("a.jpg"), _legacy_img("b.jpg")]}])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")

    downloader = MagicMock()
    downloader.download_and_process = MagicMock(side_effect=AssertionError("ne doit pas être appelé"))

    from services.album_actions import redownload_product, LegacyManifestError
    with pytest.raises(LegacyManifestError):
        asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    # Fichiers existants doivent être préservés (pas de mutation FS sur legacy).
    assert (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "a.jpg").exists()
    assert (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "b.jpg").exists()


def test_redownload_image_legacy_v1_raises_legacy_error(tmp_path, monkeypatch):
    """Image entry sans url_source → LegacyManifestError, fichier préservé."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{"id_produit": "1", "nom": "p", "synced": True,
                                       "images": [_legacy_img("a.jpg")]}])
    _create_files(images_base / "alpha.com", "a.jpg")

    downloader = MagicMock()
    downloader.download_and_process = MagicMock(side_effect=AssertionError("ne doit pas être appelé"))

    from services.album_actions import redownload_image, LegacyManifestError
    with pytest.raises(LegacyManifestError):
        asyncio.run(redownload_image(str(tmp_path), "alpha.com", "1", "a.jpg", downloader))

    assert (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "a.jpg").exists()


def test_redownload_product_mixed_manifest_skips_legacy_entries(tmp_path, monkeypatch):
    """Manifest mixte (certaines images avec url_source, d'autres sans) → on download
    celles qui ont url_source, on skip les autres en signalant la raison."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "synced": True,
        "images": [
            _img("modern.jpg", "https://x/modern.jpg"),
            _legacy_img("legacy.jpg"),
        ],
    }])
    _create_files(images_base / "alpha.com", "modern.jpg")
    _create_files(images_base / "alpha.com", "legacy.jpg")

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        return {"status": "ok", "paths": {"main_path": "/x", "thumb_path": "/x",
                                          "filename": "x", "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    result = asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    assert result["downloaded"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert any("legacy" in (e.get("reason", "")).lower() for e in result["errors"])


def _seed_errors_json(images_base: Path, domain: str, entries: list):
    """Helper : crée errors.json (format identique à downloader.save_error)."""
    p = images_base / domain / "errors.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries))


def test_redownload_product_success_clears_errors_json_entries(tmp_path, monkeypatch):
    """Après un redownload réussi, les entrées de errors.json correspondant aux URLs
    téléchargées doivent être retirées. Sans ça, _detect_image_status garderait le
    statut 'error' en priorité.
    """
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "synced": True,
        "images": [_img("a.jpg", "https://x/a.jpg"), _img("b.jpg", "https://x/b.jpg")],
    }])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")
    _seed_errors_json(images_base, "alpha.com", [
        {"id_produit": "1", "url": "https://x/a.jpg", "erreur": "old 404"},
        {"id_produit": "1", "url": "https://x/b.jpg", "erreur": "old timeout"},
        {"id_produit": "2", "url": "https://other/c.jpg", "erreur": "unrelated"},
    ])

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        return {"status": "ok", "paths": {"main_path": "/x", "thumb_path": "/x",
                                          "filename": "x", "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    # errors.json doit conserver UNIQUEMENT l'entrée pour l'autre produit (id 2)
    err_path = images_base / "alpha.com" / "errors.json"
    assert err_path.exists()
    remaining = json.loads(err_path.read_text())
    assert len(remaining) == 1
    assert remaining[0]["url"] == "https://other/c.jpg"


def test_redownload_product_clears_file_when_all_errors_resolved(tmp_path, monkeypatch):
    """Si après nettoyage la liste devient vide, errors.json est supprimé."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "synced": True,
        "images": [_img("a.jpg", "https://x/a.jpg")],
    }])
    _create_files(images_base / "alpha.com", "a.jpg")
    _seed_errors_json(images_base, "alpha.com", [
        {"id_produit": "1", "url": "https://x/a.jpg", "erreur": "old"},
    ])

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        return {"status": "ok", "paths": {"main_path": "/x", "thumb_path": "/x",
                                          "filename": "x", "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    err_path = images_base / "alpha.com" / "errors.json"
    assert not err_path.exists(), "errors.json should be deleted when empty"


def test_redownload_product_failure_does_not_clear_errors(tmp_path, monkeypatch):
    """Si le download échoue, l'entrée d'erreur doit rester (sinon on perdrait
    la trace d'un échec persistant)."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "synced": True,
        "images": [_img("a.jpg", "https://x/a.jpg")],
    }])
    _create_files(images_base / "alpha.com", "a.jpg")
    _seed_errors_json(images_base, "alpha.com", [
        {"id_produit": "1", "url": "https://x/a.jpg", "erreur": "still 404"},
    ])

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        return {"status": "error", "error": "still 404"}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_product
    asyncio.run(redownload_product(str(tmp_path), "alpha.com", "1", downloader))

    err_path = images_base / "alpha.com" / "errors.json"
    assert err_path.exists()
    remaining = json.loads(err_path.read_text())
    assert len(remaining) == 1
    assert remaining[0]["url"] == "https://x/a.jpg"


def test_redownload_image_success_clears_errors_json_entry(tmp_path, monkeypatch):
    """redownload_image qui réussit nettoie son URL spécifiquement."""
    images_base = _setup(monkeypatch, tmp_path)
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "synced": True,
        "images": [_img("a.jpg", "https://x/a.jpg"), _img("b.jpg", "https://x/b.jpg")],
    }])
    _create_files(images_base / "alpha.com", "a.jpg")
    _create_files(images_base / "alpha.com", "b.jpg")
    _seed_errors_json(images_base, "alpha.com", [
        {"id_produit": "1", "url": "https://x/a.jpg", "erreur": "old"},
        {"id_produit": "1", "url": "https://x/b.jpg", "erreur": "old"},
    ])

    async def fake_download(url, domain, product_id, product_name, storage_base=None, index=0):
        return {"status": "ok", "paths": {"main_path": "/x", "thumb_path": "/x",
                                          "filename": "x", "url_source": url}}

    downloader = MagicMock()
    downloader.download_and_process = fake_download

    from services.album_actions import redownload_image
    asyncio.run(redownload_image(str(tmp_path), "alpha.com", "1", "a.jpg", downloader))

    err_path = images_base / "alpha.com" / "errors.json"
    assert err_path.exists()
    remaining = json.loads(err_path.read_text())
    assert len(remaining) == 1
    assert remaining[0]["url"] == "https://x/b.jpg"
