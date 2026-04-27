"""Tests d'intégration pour _save_to_manifest — vérifient que url_source est persisté."""

import json
import asyncio
import sys
import os
import types
import pytest


def _patch_package_imports(monkeypatch):
    """
    Injecte les modules internes sous les deux alias de chemin d'import :
      - core.*                          (pythonpath = app, convention des tests)
      - image_download_service.core.*   (import absolu utilisé par _save_to_manifest
                                         et save_error en production)

    Cela évite ModuleNotFoundError sans avoir à installer le package.
    """
    import core.nfs_lock as real_nfs_lock
    import core.image_processor as real_image_processor

    # Crée un package virtuel image_download_service si absent
    if "image_download_service" not in sys.modules:
        pkg = types.ModuleType("image_download_service")
        monkeypatch.setitem(sys.modules, "image_download_service", pkg)

    if "image_download_service.core" not in sys.modules:
        core_pkg = types.ModuleType("image_download_service.core")
        monkeypatch.setitem(sys.modules, "image_download_service.core", core_pkg)

    monkeypatch.setitem(sys.modules, "image_download_service.core.nfs_lock", real_nfs_lock)
    monkeypatch.setitem(sys.modules, "image_download_service.core.image_processor", real_image_processor)


def test_save_to_manifest_persists_url_source(tmp_path, monkeypatch):
    """_save_to_manifest doit écrire url_source dans chaque entrée image du manifest.

    Scénario :
    - On crée un répertoire temporaire simulant /app/storage
    - On monkey-patche _STORAGE_BASE pour pointer vers tmp_path
    - On appelle _save_to_manifest avec processed_images contenant url_source
    - On vérifie que manifest.json contient url_source dans la première image
    """
    _patch_package_imports(monkeypatch)

    import core.downloader as downloader_module

    monkeypatch.setattr(downloader_module, "_STORAGE_BASE", str(tmp_path))

    domain = "example.com"
    product_id = "42001"
    product_name = "produit-test"
    url = "https://example.com/images/photo.jpg"

    # Simuler le résultat d'un download_and_process réussi
    product_id_str = str(product_id).zfill(3)
    rep1 = product_id_str[-1]
    rep2 = product_id_str[-2]
    rep3 = product_id_str[-3]

    main_dir = tmp_path / "images" / domain / "produit-2" / rep1 / rep2 / rep3
    thumb_dir = tmp_path / "images" / domain / "produit-3" / rep1 / rep2 / rep3
    main_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)

    filename = "produit-test-42001-abcd1234.jpg"
    processed_images = [
        {
            "main_path": str(main_dir / filename),
            "thumb_path": str(thumb_dir / filename),
            "filename": filename,
            "url_source": url,
        }
    ]

    # Instanciation du Downloader — on court-circuite __init__ via __new__ car
    # ce test ne fait qu'appeler _save_to_manifest (pas de download ni ImageProcessor).
    from unittest.mock import MagicMock

    downloader = downloader_module.Downloader.__new__(downloader_module.Downloader)
    downloader.image_processor = MagicMock()
    downloader.proxy_password = None
    downloader.proxy_url = None

    asyncio.run(downloader._save_to_manifest(domain, product_id, product_name, processed_images))

    manifest_path = tmp_path / "images" / domain / "manifest.json"
    assert manifest_path.exists(), "manifest.json doit être créé"

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    products = manifest.get("products", [])
    assert len(products) == 1
    images = products[0]["images"]
    assert len(images) == 1

    first_image = images[0]
    assert "url_source" in first_image, \
        f"url_source doit être présent dans l'entrée image, obtenu : {first_image}"
    assert first_image["url_source"] == url, \
        f"url_source attendu '{url}', obtenu '{first_image['url_source']}'"
