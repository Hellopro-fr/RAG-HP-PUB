"""Tests d'intégration du routeur /albums (FastAPI TestClient)."""

import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import _patch_package_imports


def _alias_main_dependencies(monkeypatch):
    """Étend les alias `image_download_service.*` pour rendre `main.py` importable.

    `main.py` fait `from image_download_service.messaging.consumer import Consumer`
    et `from image_download_service.core.archiver import Archiver`. Comme le
    pythonpath des tests est `app`, ces sous-modules existent sous les noms
    `messaging.consumer` et `core.archiver` mais pas sous le préfixe
    `image_download_service.*`. On crée les alias dans sys.modules.
    """
    _patch_package_imports(monkeypatch)

    # core.archiver — on patche __init__ pour qu'il pointe vers STORAGE_BASE
    # (et ne tente pas de créer /app/storage/archives en environnement de test).
    import core.archiver as real_archiver
    import os as _os
    _orig_archiver_init = real_archiver.Archiver.__init__

    def _archiver_init_envaware(self, storage_base: str = None):
        if storage_base is None:
            storage_base = _os.environ.get("STORAGE_BASE", "/app/storage")
        return _orig_archiver_init(self, storage_base)

    monkeypatch.setattr(real_archiver.Archiver, "__init__", _archiver_init_envaware)
    monkeypatch.setitem(sys.modules, "image_download_service.core.archiver", real_archiver)

    # core.downloader (utilisé par messaging.consumer et album_actions via downloader injecté)
    import core.downloader as real_downloader
    monkeypatch.setitem(sys.modules, "image_download_service.core.downloader", real_downloader)

    # messaging package + consumer
    import messaging as real_messaging
    monkeypatch.setitem(sys.modules, "image_download_service.messaging", real_messaging)
    import messaging.consumer as real_consumer
    monkeypatch.setitem(sys.modules, "image_download_service.messaging.consumer", real_consumer)

    # routers package + albums
    import routers as real_routers
    monkeypatch.setitem(sys.modules, "image_download_service.routers", real_routers)
    import routers.albums as real_routers_albums
    monkeypatch.setitem(sys.modules, "image_download_service.routers.albums", real_routers_albums)


@pytest.fixture
def client(tmp_path, monkeypatch):
    _alias_main_dependencies(monkeypatch)
    monkeypatch.setenv("STORAGE_BASE", str(tmp_path))
    (tmp_path / "images").mkdir()

    # Forcer un re-import de main pour qu'il prenne en compte STORAGE_BASE
    # et qu'il soit ré-instancié avec un Archiver qui pointera vers /app/storage par défaut
    # (l'archiver est utilisé par les routes Sync/Domains existantes ; les routes
    # /domains/_summary du nouveau routeur lisent STORAGE_BASE via _storage_base()).
    if "main" in sys.modules:
        del sys.modules["main"]
    if "image_download_service.main" in sys.modules:
        del sys.modules["image_download_service.main"]

    import main as main_module
    # Aliaser pour que les imports `image_download_service.main` fonctionnent aussi
    monkeypatch.setitem(sys.modules, "image_download_service.main", main_module)

    from services.album_jobs import reset_jobs
    reset_jobs()

    return TestClient(main_module.app), tmp_path


def _seed(images_base: Path, domain: str, products):
    d = images_base / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"products": products, "last_updated": "2026-04-26"})
    )


def test_summary_empty(client):
    c, tmp = client
    r = c.get("/domains/_summary")
    assert r.status_code == 200
    assert r.json() == {"domains": [], "total": 0}


def test_summary_with_data(client):
    c, tmp = client
    _seed(tmp / "images", "alpha.com", [{"id_produit": "1", "synced": True, "images": []}])
    r = c.get("/domains/_summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["domains"][0]["domain"] == "alpha.com"


def test_products_404_unknown_domain(client):
    c, _ = client
    r = c.get("/domains/ghost.com/products")
    assert r.status_code == 404


def test_products_paginated(client):
    c, tmp = client
    products = [
        {"id_produit": str(i), "nom": f"p{i}", "synced": True, "images": []}
        for i in range(150)
    ]
    _seed(tmp / "images", "alpha.com", products)
    r = c.get("/domains/alpha.com/products?page=1&page_size=100")
    assert r.status_code == 200
    body = r.json()
    assert len(body["products"]) == 100
    assert body["next_page"] == 2


def test_delete_image_204(client):
    c, tmp = client
    images_base = tmp / "images"
    _seed(images_base, "alpha.com", [{
        "id_produit": "1", "nom": "p", "images": [
            {"filename": "a.jpg", "url_source": "u",
             "main": "produit-2/0/0/0/a.jpg", "thumb": "produit-3/0/0/0/a.jpg"},
        ]}])
    (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0").mkdir(parents=True)
    (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "a.jpg").write_bytes(b"x")
    r = c.delete("/images/alpha.com/1/a.jpg")
    assert r.status_code == 204


def test_delete_image_404_unknown_filename(client):
    c, tmp = client
    _seed(tmp / "images", "alpha.com", [{"id_produit": "1", "nom": "p", "images": []}])
    r = c.delete("/images/alpha.com/1/ghost.jpg")
    assert r.status_code == 404


def test_redownload_image_422_unknown(client):
    c, tmp = client
    _seed(tmp / "images", "alpha.com", [{"id_produit": "1", "nom": "p", "images": []}])
    r = c.post("/images/alpha.com/1/ghost.jpg/redownload")
    assert r.status_code == 422


def test_delete_album_returns_202_with_job_id(client):
    c, tmp = client
    _seed(tmp / "images", "alpha.com", [{"id_produit": "1", "synced": True, "images": []}])
    r = c.delete("/domains/alpha.com")
    assert r.status_code == 202
    body = r.json()
    assert body["domain"] == "alpha.com"
    assert body["job_id"].startswith("del_")
    assert body["poll_url"] == f"/jobs/{body['job_id']}"


def test_get_job_unknown_404(client):
    c, _ = client
    r = c.get("/jobs/ghost")
    assert r.status_code == 404


def test_get_job_returns_status(client):
    c, tmp = client
    _seed(tmp / "images", "alpha.com", [{"id_produit": "1", "synced": True, "images": []}])
    r = c.delete("/domains/alpha.com")
    job_id = r.json()["job_id"]
    r2 = c.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id
