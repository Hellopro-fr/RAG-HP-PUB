"""Tests TDD -- chantier logo fournisseur (Task 2).

Couvre :
  - POST /logos/enqueue (miroir POST /pages/enqueue, publish RabbitMQ mocke)
  - GET  /logos/{domaine} (lecture manifest_logo.json)
  - Downloader.process_logo_download (flux direct : telechargement HTTP mocke
    + process_logo (Task 1) + ecriture disque + manifest_logo.json)

Conventions (miroir test_process_page_image_flow.py / test_albums_router.py) :
  - asyncio.run() pour le flux direct (pas de pytest-asyncio dans requirements.txt)
  - monkeypatch sur core.downloader._STORAGE_BASE pour l'isolement FS
  - mock aiohttp via unittest.mock (aiohttp utilise par process_logo_download)
  - TestClient(main_module.app) sans lifespan -> app.state.rabbitmq_connection
    injecte manuellement en mock (miroir du constat fait dans test_albums_router.py :
    TestClient() sans `with` n'execute pas le lifespan startup)
"""

import asyncio
import hashlib
import json
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from conftest import _patch_package_imports


# =============================================================================
# Fixture TestClient -- miroir test_albums_router.py::_alias_main_dependencies,
# etendu aux modules logos (router + consumer)
# =============================================================================

def _alias_main_dependencies(monkeypatch):
    _patch_package_imports(monkeypatch)

    import core.archiver as real_archiver
    _orig_archiver_init = real_archiver.Archiver.__init__

    def _archiver_init_envaware(self, storage_base: str = None):
        if storage_base is None:
            storage_base = os.environ.get("STORAGE_BASE", "/app/storage")
        return _orig_archiver_init(self, storage_base)

    monkeypatch.setattr(real_archiver.Archiver, "__init__", _archiver_init_envaware)
    monkeypatch.setitem(sys.modules, "image_download_service.core.archiver", real_archiver)

    import core.downloader as real_downloader
    monkeypatch.setitem(sys.modules, "image_download_service.core.downloader", real_downloader)

    import messaging as real_messaging
    monkeypatch.setitem(sys.modules, "image_download_service.messaging", real_messaging)
    import messaging.consumer as real_consumer
    monkeypatch.setitem(sys.modules, "image_download_service.messaging.consumer", real_consumer)
    import messaging.page_image_consumer as real_page_image_consumer
    monkeypatch.setitem(
        sys.modules, "image_download_service.messaging.page_image_consumer", real_page_image_consumer
    )
    import messaging.logo_consumer as real_logo_consumer
    monkeypatch.setitem(sys.modules, "image_download_service.messaging.logo_consumer", real_logo_consumer)

    import routers as real_routers
    monkeypatch.setitem(sys.modules, "image_download_service.routers", real_routers)
    import routers.albums as real_routers_albums
    monkeypatch.setitem(sys.modules, "image_download_service.routers.albums", real_routers_albums)
    import routers.pages as real_routers_pages
    monkeypatch.setitem(sys.modules, "image_download_service.routers.pages", real_routers_pages)
    import routers.logos as real_routers_logos
    monkeypatch.setitem(sys.modules, "image_download_service.routers.logos", real_routers_logos)


@pytest.fixture
def client(tmp_path, monkeypatch):
    _alias_main_dependencies(monkeypatch)
    monkeypatch.setenv("STORAGE_BASE", str(tmp_path))
    (tmp_path / "images").mkdir()

    for mod_key in ("main", "image_download_service.main"):
        if mod_key in sys.modules:
            del sys.modules[mod_key]

    import main as main_module
    monkeypatch.setitem(sys.modules, "image_download_service.main", main_module)

    # main.py monte un lifespan reel (connexion RabbitMQ) mais TestClient(app)
    # sans `with` n'execute pas le startup -> app.state.rabbitmq_connection est
    # absent par defaut (cf. test_albums_router.py, meme constat). On injecte un
    # mock de connexion pour exercer POST /logos/enqueue sans RabbitMQ reel.
    mock_channel = MagicMock()
    mock_exchange = MagicMock()
    mock_exchange.publish = AsyncMock()
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    mock_channel_cm = MagicMock()
    mock_channel_cm.__aenter__ = AsyncMock(return_value=mock_channel)
    mock_channel_cm.__aexit__ = AsyncMock(return_value=False)

    mock_connection = MagicMock()
    mock_connection.is_closed = False
    mock_connection.channel = MagicMock(return_value=mock_channel_cm)

    main_module.app.state.rabbitmq_connection = mock_connection

    from fastapi.testclient import TestClient
    return TestClient(main_module.app), tmp_path, mock_connection, mock_channel, mock_exchange


# =============================================================================
# POST /logos/enqueue
# =============================================================================

def test_post_logos_enqueue_202(client):
    c, _tmp, _conn, mock_channel, mock_exchange = client
    payload = {"domaine": "acme.fr", "url_logo": "https://acme.fr/logo.svg", "key": "logo-principal"}

    r = c.post("/logos/enqueue", json=payload)

    assert r.status_code == 202
    assert r.json() == {"status": "accepted", "domaine": "acme.fr", "key": "logo-principal"}

    # Exchange declare avec les defauts attendus (env non surcharge dans ce test)
    mock_channel.declare_exchange.assert_awaited_once()
    exchange_args, _exchange_kwargs = mock_channel.declare_exchange.call_args
    assert exchange_args[0] == "data_exchange_logos"

    # Message publie avec la routing key attendue + le body JSON du payload
    mock_exchange.publish.assert_awaited_once()
    publish_args, publish_kwargs = mock_exchange.publish.call_args
    assert publish_kwargs["routing_key"] == "new_data.logo"
    published_message = publish_args[0]
    assert json.loads(published_message.body.decode()) == payload


def test_post_logos_enqueue_503_when_rabbitmq_unavailable(client):
    c, _tmp, _conn, _channel, _exchange = client
    import main as main_module
    main_module.app.state.rabbitmq_connection = None

    r = c.post(
        "/logos/enqueue",
        json={"domaine": "acme.fr", "url_logo": "https://acme.fr/logo.svg", "key": "logo-principal"},
    )
    assert r.status_code == 503


def test_post_logos_enqueue_422_missing_fields(client):
    c, *_ = client
    r = c.post("/logos/enqueue", json={"domaine": "acme.fr"})
    assert r.status_code == 422


# =============================================================================
# GET /logos/{domaine}
# =============================================================================

def test_get_logos_unknown_domain_returns_empty_structure(client):
    c, *_ = client
    r = c.get("/logos/never-seen-domain.com")
    assert r.status_code == 200
    assert r.json() == {"logos": [], "last_updated": None}


def test_get_logos_invalid_domain_400(client):
    c, *_ = client
    r = c.get("/logos/bad domain")
    assert r.status_code == 400


# =============================================================================
# Downloader.process_logo_download -- flux direct (telechargement HTTP mocke)
# =============================================================================

def _setup_storage(monkeypatch, tmp_path):
    import core.downloader as dl
    monkeypatch.setattr(dl, "_STORAGE_BASE", str(tmp_path))


def _make_downloader(monkeypatch):
    """Instancie un Downloader sans import reel d'ImageProcessor, avec le vrai
    process_logo (Task 1) branche (le process_logo_download appelle self.process_logo,
    assigne normalement dans __init__ -- ici on bypasse __init__ via __new__)."""
    import core.downloader as dl
    from core.image_processor import process_logo

    d = dl.Downloader.__new__(dl.Downloader)
    d.image_processor = MagicMock()
    d.process_logo = process_logo
    d.proxy_password = None
    d.proxy_url = None
    return d


def _make_logo_payload(domain="fournisseur.com", url_logo="https://f.com/logo.svg", key="logo-principal"):
    return {"domaine": domain, "url_logo": url_logo, "key": key}


def _mock_aiohttp_session_ok(content_bytes: bytes):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=content_bytes)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def _mock_aiohttp_session_error(status=404):
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


def test_process_logo_download_svg_passthrough(tmp_path, monkeypatch):
    """SVG -- octets ecrits sur disque == octets source (passthrough), manifest OK."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    raw_svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><rect/></svg>'
    payload = _make_logo_payload(domain="fournisseur.com", url_logo="https://f.com/logo.svg", key="logo-principal")

    mock_session = _mock_aiohttp_session_ok(raw_svg)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(d.process_logo_download(payload))

    assert result is not None, "process_logo_download doit retourner l'entree manifest"
    assert result["key"] == "logo-principal"
    assert result["format"] == "svg"
    assert result["width"] == 200 and result["height"] == 60
    assert len(result["content_hash"]) == 64, "content_hash doit etre un SHA-256 hex (64 chars)"
    assert result["content_hash"] == hashlib.sha256(raw_svg).hexdigest()

    # Fichier ecrit sur disque, octets identiques a la source (passthrough SVG)
    hosted_abs = os.path.join(str(tmp_path), "images", "fournisseur.com", result["hosted_path"])
    assert os.path.exists(hosted_abs), f"fichier logo attendu sur disque : {hosted_abs}"
    with open(hosted_abs, "rb") as f:
        assert f.read() == raw_svg, "les octets ecrits doivent etre identiques a la source (passthrough SVG)"

    # manifest_logo.json cree sous images/{domain}/logo/
    manifest_path = tmp_path / "images" / "fournisseur.com" / "logo" / "manifest_logo.json"
    assert manifest_path.exists(), "manifest_logo.json doit etre cree"
    data = json.loads(manifest_path.read_text())
    logos = data.get("logos", [])
    assert len(logos) == 1
    assert logos[0]["key"] == "logo-principal"
    assert logos[0]["content_hash"] == result["content_hash"]


def test_process_logo_download_png_transparent(tmp_path, monkeypatch, transparent_png_bytes):
    """PNG transparent -- format/width/height/content_hash corrects, passthrough (pas de flatten)."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_logo_payload(domain="fournisseur.com", url_logo="https://f.com/logo.png", key="logo-png")

    mock_session = _mock_aiohttp_session_ok(transparent_png_bytes)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(d.process_logo_download(payload))

    assert result is not None
    assert result["format"] == "png"
    assert result["width"] == 10 and result["height"] == 10
    assert result["content_hash"] == hashlib.sha256(transparent_png_bytes).hexdigest()
    assert len(result["content_hash"]) == 64

    hosted_abs = os.path.join(str(tmp_path), "images", "fournisseur.com", result["hosted_path"])
    with open(hosted_abs, "rb") as f:
        on_disk = f.read()
    assert on_disk == transparent_png_bytes, "PNG passthrough : octets sur disque == octets source"

    manifest_path = tmp_path / "images" / "fournisseur.com" / "logo" / "manifest_logo.json"
    data = json.loads(manifest_path.read_text())
    logos = data.get("logos", [])
    assert len(logos) == 1
    assert logos[0]["format"] == "png"
    assert logos[0]["width"] == 10 and logos[0]["height"] == 10


def test_process_logo_download_replace_same_key(tmp_path, monkeypatch):
    """2 ingestions successives avec la meme key -> 1 seule entree manifest (replace_idx, cycle MAJ)."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    svg_v1 = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 40"><rect/></svg>'
    svg_v2 = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 50"><rect fill="red"/></svg>'
    payload = _make_logo_payload(domain="fournisseur.com", url_logo="https://f.com/logo.svg", key="logo-principal")

    with patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session_ok(svg_v1)):
        result1 = asyncio.run(d.process_logo_download(payload))
    with patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session_ok(svg_v2)):
        result2 = asyncio.run(d.process_logo_download(payload))

    assert result1["content_hash"] != result2["content_hash"]

    manifest_path = tmp_path / "images" / "fournisseur.com" / "logo" / "manifest_logo.json"
    data = json.loads(manifest_path.read_text())
    logos = data.get("logos", [])
    assert len(logos) == 1, f"replace_idx attendu : 1 seule entree pour la meme key, obtenu {len(logos)}"
    assert logos[0]["content_hash"] == result2["content_hash"], "la MAJ doit remplacer l'entree (dernier contenu)"


def test_process_logo_download_http_error_writes_errors_logo(tmp_path, monkeypatch):
    """HTTP 404 -> process_logo_download retourne None + errors_logo.json cree, manifest absent."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_logo_payload(domain="fournisseur.com", url_logo="https://f.com/notfound.svg", key="logo-404")

    with patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session_error(404)):
        result = asyncio.run(d.process_logo_download(payload))

    assert result is None

    errors_path = tmp_path / "images" / "fournisseur.com" / "logo" / "errors_logo.json"
    assert errors_path.exists(), "errors_logo.json doit etre cree"
    errors = json.loads(errors_path.read_text())
    assert len(errors) >= 1
    assert errors[0]["key"] == "logo-404"

    manifest_path = tmp_path / "images" / "fournisseur.com" / "logo" / "manifest_logo.json"
    assert not manifest_path.exists(), "manifest_logo.json ne doit pas etre cree pour un echec de telechargement"


# =============================================================================
# Boucle GET <- process_logo_download : verifie que le contenu ecrit par le flux
# direct est bien celui expose par l'endpoint GET /logos/{domaine}
# =============================================================================

def test_get_logos_reflects_processed_entry(client, monkeypatch):
    c, tmp_path, _conn, _channel, _exchange = client
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    raw_svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 60"><rect/></svg>'
    payload = _make_logo_payload(domain="acme.fr", url_logo="https://acme.fr/logo.svg", key="logo-principal")

    with patch("aiohttp.ClientSession", return_value=_mock_aiohttp_session_ok(raw_svg)):
        asyncio.run(d.process_logo_download(payload))

    r = c.get("/logos/acme.fr")
    assert r.status_code == 200
    body = r.json()
    logos = body.get("logos", [])
    assert len(logos) == 1
    entry = logos[0]
    assert entry["key"] == "logo-principal"
    assert entry["format"] == "svg"
    assert entry["width"] == 200 and entry["height"] == 60
    assert len(entry["content_hash"]) == 64
    assert entry["content_hash"] == hashlib.sha256(raw_svg).hexdigest()
    assert entry["hosted_path"].startswith("logo" + os.sep) or entry["hosted_path"].startswith("logo/")
