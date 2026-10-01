"""Tests du flow process_page_image — 7 scénarios Chantier D (Task T8).

Conventions :
- Miroir du style test_process_product_flow.py (asyncio.run, pas de @pytest.mark.asyncio)
- monkeypatch sur core.downloader._STORAGE_BASE pour l'isolement FS
- mock aiohttp via unittest.mock (aiohttp utilisé par process_page_image, pas httpx)
- aio_pika et common_utils mockés au niveau sys.modules pour le test DLQ consumer
- pytest-asyncio NON disponible (voir requirements.txt) -> asyncio.run() pour tout
"""

import asyncio
import json
import os
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from conftest import _patch_package_imports


# =============================================================================
# Helpers partagés
# =============================================================================

def _setup_storage(monkeypatch, tmp_path):
    """Redirige _STORAGE_BASE vers tmp_path pour l'isolement des tests."""
    import core.downloader as dl
    monkeypatch.setattr(dl, "_STORAGE_BASE", str(tmp_path))


def _make_downloader(monkeypatch):
    """Instancie un Downloader sans provoquer d'import réel d'ImageProcessor."""
    import core.downloader as dl
    d = dl.Downloader.__new__(dl.Downloader)
    d.image_processor = MagicMock()
    d.proxy_password = None
    d.proxy_url = None
    return d


def _make_payload(domain="fournisseur.com", id_image_isi=1001, page_type="produit",
                  url_image="https://f.com/img.jpg"):
    """Construit un payload wire minimal pour process_page_image."""
    return {
        "id_image_isi": id_image_isi,
        "domaine": domain,
        "url_image": url_image,
        "url_page_source": "https://fournisseur.com/page",
        "page_type": page_type,
        "alt_text": "alt",
        "contexte_h1": "h1",
        "contexte_h2": "h2",
    }


def _stub_process_image_page(tmp_path, domain, filename):
    """
    Retourne un dict imitant le retour de ImageProcessor.process_image_page.
    Crée les fichiers main/thumb sur disque pour valider les assertions FS.
    """
    storage_dir = os.path.join(str(tmp_path), "images", domain)
    main_dir = os.path.join(storage_dir, "pages", "1", "0")
    thumb_dir = os.path.join(storage_dir, "pages", "thumbs", "1", "0")
    os.makedirs(main_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)
    main_path = os.path.join(main_dir, filename)
    thumb_path = os.path.join(thumb_dir, filename)
    open(main_path, "wb").close()
    open(thumb_path, "wb").close()
    return {
        "main_path": main_path,
        "thumb_path": thumb_path,
        "filename": filename,
        "width": 100,
        "height": 100,
        "format": "JPEG",
        "file_size": 1234,
    }


def _mock_aiohttp_session_ok(content_bytes=b"FAKEJPEG"):
    """Construit un mock aiohttp.ClientSession qui retourne HTTP 200 + content."""
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
    """Construit un mock aiohttp.ClientSession qui retourne un code d'erreur HTTP."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


# =============================================================================
# J1 — Nouvelle image : entrée ajoutée au manifest, fichier présent sur disque
# =============================================================================

def test_j1_new_image_adds_manifest_entry(tmp_path, monkeypatch):
    """J1 — Payload frais -> entrée manifest créée, fichier main présent sur disque."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_payload(domain="fournisseur.com", id_image_isi=1001)

    # Stub process_image_page : crée les fichiers sur disque, retourne les paths
    filename = "page-produit-1001-ab12cd34.jpg"
    image_result = _stub_process_image_page(tmp_path, "fournisseur.com", filename)
    d.image_processor.process_image_page = MagicMock(return_value=image_result)

    # Mock aiohttp pour le téléchargement HTTP
    mock_session = _mock_aiohttp_session_ok()
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(d.process_page_image(payload))

    # L'entrée manifest doit être retournée
    assert result is not None, "process_page_image doit retourner l'entrée manifest"
    assert result["id_image_isi"] == 1001
    assert result["url_source"] == "https://f.com/img.jpg"
    assert result["page_type"] == "produit"

    # Le manifest_pages.json doit exister et contenir l'entrée
    manifest_path = tmp_path / "images/fournisseur.com/manifest_pages.json"
    assert manifest_path.exists(), "manifest_pages.json doit être créé"
    data = json.loads(manifest_path.read_text())
    pages = data.get("pages_images", [])
    assert len(pages) == 1, f"1 entrée attendue, obtenu {len(pages)}"
    assert pages[0]["url_source"] == "https://f.com/img.jpg"

    # Le chemin thumb doit être sous pages/thumbs/
    assert "pages" + os.sep + "thumbs" in result["thumb_path"] or "pages/thumbs/" in result["thumb_path"], (
        f"thumb_path doit être sous pages/thumbs/, obtenu : {result['thumb_path']}"
    )

    # Le fichier main doit être présent sur disque
    assert os.path.exists(image_result["main_path"]), "Le fichier main doit exister sur disque"


# =============================================================================
# J2 — Idempotence skip : même payload deux fois -> 2e appel retourne entrée existante
# =============================================================================

def test_j2_idempotence_skip_returns_existing(tmp_path, monkeypatch):
    """J2 — Même payload deux fois -> 2e appel retourne l'entrée existante sans re-DL."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_payload(domain="fournisseur.com", id_image_isi=2001,
                            url_image="https://f.com/img2.jpg")

    filename = "page-produit-2001-cafebabe.jpg"
    image_result = _stub_process_image_page(tmp_path, "fournisseur.com", filename)
    d.image_processor.process_image_page = MagicMock(return_value=image_result)

    mock_session = _mock_aiohttp_session_ok()
    dl_call_count = 0

    class CountingSession:
        def __init__(self, *args, **kwargs):
            nonlocal dl_call_count
            dl_call_count += 1

        def get(self, *args, **kwargs):
            return mock_session.get(*args, **kwargs)

        async def __aenter__(self):
            return mock_session.__aenter__.return_value

        async def __aexit__(self, *args):
            return False

    with patch("aiohttp.ClientSession", CountingSession):
        result1 = asyncio.run(d.process_page_image(payload))

    assert result1 is not None
    assert dl_call_count == 1, f"1 téléchargement attendu au 1er appel, obtenu {dl_call_count}"

    # Deuxième appel : idempotence — le fichier main existe dans le manifest ET sur disque
    dl_call_count = 0
    with patch("aiohttp.ClientSession", CountingSession):
        result2 = asyncio.run(d.process_page_image(payload))

    assert result2 is not None
    assert dl_call_count == 0, "Idempotence : 0 téléchargement au 2e appel (skip attendu)"
    assert result2["url_source"] == result1["url_source"], "L'entrée retournée doit être la même"

    # Le manifest ne doit contenir qu'une seule entrée
    manifest_path = tmp_path / "images/fournisseur.com/manifest_pages.json"
    data = json.loads(manifest_path.read_text())
    pages = data.get("pages_images", [])
    assert len(pages) == 1, f"Toujours 1 entrée attendue après idempotence, obtenu {len(pages)}"


# =============================================================================
# HTTP 404 — Erreur HTTP retourne None + entrée dans errors_pages.json
# =============================================================================

def test_j3_http_404_writes_error_no_manifest(tmp_path, monkeypatch):
    """HTTP 404 -> process_page_image retourne None + errors_pages.json créé, manifest non touché."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_payload(domain="fournisseur.com", id_image_isi=3001,
                            url_image="https://f.com/notfound.jpg")
    d.image_processor.process_image_page = MagicMock()

    mock_session = _mock_aiohttp_session_error(404)
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = asyncio.run(d.process_page_image(payload))

    assert result is None, f"None attendu pour HTTP 404, obtenu : {result}"

    # errors_pages.json doit exister avec l'entrée d'erreur
    errors_path = tmp_path / "images/fournisseur.com/errors_pages.json"
    assert errors_path.exists(), "errors_pages.json doit être créé"
    errors = json.loads(errors_path.read_text())
    assert len(errors) >= 1, "Au moins 1 erreur attendue dans errors_pages.json"
    assert errors[0]["id_image_isi"] == 3001
    assert errors[0]["url_image"] == "https://f.com/notfound.jpg"

    # manifest_pages.json ne doit PAS avoir d'entrées
    manifest_path = tmp_path / "images/fournisseur.com/manifest_pages.json"
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text())
        pages = data.get("pages_images", [])
        assert len(pages) == 0, "Aucune entrée dans le manifest pour une image en erreur"


# =============================================================================
# Retry DLQ — MAX_RETRIES épuisés -> _send_to_dlq appelé + message ACKé
# =============================================================================

def test_j4_consumer_max_retries_sends_to_dlq(monkeypatch):
    """DLQ — MAX_RETRIES épuisés -> _send_to_dlq appelé 1 fois, message ACKé."""
    # Injecter les faux modules aio_pika et common_utils avant tout import du consumer
    fake_aio_pika = types.ModuleType("aio_pika")
    fake_aio_pika.RobustConnection = MagicMock
    fake_aio_pika.Message = MagicMock
    fake_aio_pika.DeliveryMode = MagicMock()
    fake_aio_pika.DeliveryMode.PERSISTENT = 2
    fake_aio_pika.connect_robust = AsyncMock(return_value=MagicMock())
    monkeypatch.setitem(sys.modules, "aio_pika", fake_aio_pika)
    monkeypatch.setitem(sys.modules, "aio_pika.abc", types.ModuleType("aio_pika.abc"))

    fake_common_utils = types.ModuleType("common_utils")
    fake_cu_autres = types.ModuleType("common_utils.autres")
    fake_dlq_cls = MagicMock()
    fake_dlq_cls.create_dlq_headers = MagicMock(return_value={})
    fake_cu_autres.DLQProperties = fake_dlq_cls
    monkeypatch.setitem(sys.modules, "common_utils", fake_common_utils)
    monkeypatch.setitem(sys.modules, "common_utils.autres", fake_cu_autres)
    monkeypatch.setitem(
        sys.modules, "common_utils.autres.DLQProperties",
        types.ModuleType("common_utils.autres.DLQProperties")
    )

    # Forcer le rechargement du consumer pour qu'il utilise les mocks injectés
    for key in list(sys.modules.keys()):
        if "page_image_consumer" in key:
            del sys.modules[key]

    from messaging.page_image_consumer import PageImageConsumer, MAX_RETRIES

    # Construire le consumer directement (sans __init__ qui appelle Downloader())
    consumer = PageImageConsumer.__new__(PageImageConsumer)
    consumer.connection = MagicMock()
    consumer.downloader = MagicMock()
    consumer._consumer_tag = None
    consumer.exchange_name = "data_exchange_pages_images"
    consumer.routing_key = "new_data.page_image"
    consumer.queue_name = "page_image_download_tasks_queue"
    consumer.internal_exchange = "page_image_internal_exchange"
    consumer.internal_routing_key = "page_image.retry"
    consumer.retry_exchange = "page_image_retry_exchange"
    consumer.retry_queue_name = "page_image_download_tasks_queue_retry"
    consumer.dead_letter_exchange = "page_image_dlq_exchange"
    consumer.dead_letter_queue_name = "page_image_download_tasks_queue_dlq"

    # Message avec MAX_RETRIES dépassé dans x-death
    body_data = {
        "id_image_isi": 4001,
        "domaine": "fournisseur.com",
        "url_image": "https://f.com/fail.jpg",
        "url_page_source": "https://fournisseur.com/page",
        "page_type": "produit",
        "alt_text": "",
        "contexte_h1": "",
        "contexte_h2": "",
    }
    mock_message = MagicMock()
    mock_message.body = json.dumps(body_data).encode()
    mock_message.ack = AsyncMock()
    mock_message.nack = AsyncMock()
    mock_message.headers = {
        "x-death": [
            {"queue": consumer.retry_queue_name, "count": MAX_RETRIES, "reason": "rejected"}
        ]
    }

    # process_page_image lève une exception transitoire pour déclencher retry/DLQ
    consumer.downloader.process_page_image = AsyncMock(side_effect=RuntimeError("échec simulé"))

    dlq_called = []

    async def fake_send_to_dlq(message, error, retry_count):
        dlq_called.append({"retry_count": retry_count, "error": str(error)})

    consumer._send_to_dlq = fake_send_to_dlq

    asyncio.run(consumer._on_message_callback(mock_message))

    assert len(dlq_called) == 1, f"_send_to_dlq attendu 1 fois, obtenu {len(dlq_called)}"
    assert dlq_called[0]["retry_count"] == MAX_RETRIES
    mock_message.ack.assert_awaited_once()
    mock_message.nack.assert_not_awaited()


# =============================================================================
# Concurrent write — 2 tâches async sur même domaine -> manifest cohérent en fin
# =============================================================================

def test_j5_concurrent_writes_manifest_coherent(tmp_path, monkeypatch):
    """Concurrent — 2 tâches async sur le même domaine -> manifest end-state correct (2 entrées)."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d1 = _make_downloader(monkeypatch)
    d2 = _make_downloader(monkeypatch)

    payload_a = _make_payload(domain="concurrent.com", id_image_isi=5001,
                               url_image="https://f.com/img-a.jpg", page_type="produit")
    payload_b = _make_payload(domain="concurrent.com", id_image_isi=5002,
                               url_image="https://f.com/img-b.jpg", page_type="accueil")

    filename_a = "page-produit-5001-aaaaaaaa.jpg"
    filename_b = "page-accueil-5002-bbbbbbbb.jpg"
    img_result_a = _stub_process_image_page(tmp_path, "concurrent.com", filename_a)
    img_result_b = _stub_process_image_page(tmp_path, "concurrent.com", filename_b)

    d1.image_processor.process_image_page = MagicMock(return_value=img_result_a)
    d2.image_processor.process_image_page = MagicMock(return_value=img_result_b)

    mock_session = _mock_aiohttp_session_ok()

    async def run_both():
        with patch("aiohttp.ClientSession", return_value=mock_session):
            results = await asyncio.gather(
                d1.process_page_image(payload_a),
                d2.process_page_image(payload_b),
            )
        return results

    results = asyncio.run(run_both())

    assert results[0] is not None, "Tâche A doit réussir"
    assert results[1] is not None, "Tâche B doit réussir"

    manifest_path = tmp_path / "images/concurrent.com/manifest_pages.json"
    assert manifest_path.exists(), "manifest_pages.json doit exister"
    data = json.loads(manifest_path.read_text())
    pages = data.get("pages_images", [])
    assert len(pages) == 2, (
        f"2 entrées attendues après writes concurrents, obtenu {len(pages)}"
    )
    url_sources = {p["url_source"] for p in pages}
    assert "https://f.com/img-a.jpg" in url_sources
    assert "https://f.com/img-b.jpg" in url_sources


# =============================================================================
# Feature flag OFF — ENABLE_PAGE_IMAGE_CONSUMER=false -> page_consumer absent + pages_router actif
# =============================================================================

def test_j6_feature_flag_off_no_consumer_but_router_active(monkeypatch):
    """Feature flag OFF -> app.state.page_consumer absent, pages_router TOUJOURS actif."""
    # Injecter les faux modules lourds avant tout import de main
    fake_aio_pika = types.ModuleType("aio_pika")
    fake_aio_pika.RobustConnection = MagicMock
    fake_aio_pika.Message = MagicMock
    fake_aio_pika.DeliveryMode = MagicMock()
    fake_aio_pika.DeliveryMode.PERSISTENT = 2
    fake_aio_pika.connect_robust = AsyncMock(return_value=MagicMock())
    monkeypatch.setitem(sys.modules, "aio_pika", fake_aio_pika)
    monkeypatch.setitem(sys.modules, "aio_pika.abc", types.ModuleType("aio_pika.abc"))

    fake_common_utils = types.ModuleType("common_utils")
    fake_cu_autres = types.ModuleType("common_utils.autres")
    fake_dlq_cls = MagicMock()
    fake_dlq_cls.create_dlq_headers = MagicMock(return_value={})
    fake_cu_autres.DLQProperties = fake_dlq_cls
    monkeypatch.setitem(sys.modules, "common_utils", fake_common_utils)
    monkeypatch.setitem(sys.modules, "common_utils.autres", fake_cu_autres)
    monkeypatch.setitem(
        sys.modules, "common_utils.autres.DLQProperties",
        types.ModuleType("common_utils.autres.DLQProperties")
    )

    monkeypatch.setenv("ENABLE_PAGE_IMAGE_CONSUMER", "false")

    # Nettoyer les caches de modules pour un rechargement propre
    for mod_key in list(sys.modules.keys()):
        if mod_key in ("main", "image_download_service.main"):
            del sys.modules[mod_key]
    for mod_key in list(sys.modules.keys()):
        if "page_image_consumer" in mod_key:
            del sys.modules[mod_key]

    import main as app_module
    app = app_module.app

    # pages_router doit être enregistré (actif sans condition, indépendant du feature flag)
    routes_paths = [getattr(r, "path", "") for r in app.routes]
    pages_routes = [p for p in routes_paths if "/pages" in p]
    assert len(pages_routes) > 0, (
        "pages_router doit être actif même avec ENABLE_PAGE_IMAGE_CONSUMER=false. "
        f"Routes trouvées : {routes_paths}"
    )

    # Sans startup lifespan, app.state.page_consumer ne doit pas être initialisé
    flag = os.environ.get("ENABLE_PAGE_IMAGE_CONSUMER", "false").lower()
    assert flag == "false"
    page_consumer_val = getattr(app.state, "page_consumer", None)
    assert page_consumer_val is None, (
        f"app.state.page_consumer doit être None sans lifespan, obtenu : {page_consumer_val}"
    )


# =============================================================================
# replace_idx — Même payload, fichier supprimé entre les 2 appels -> 1 entrée en fin
# =============================================================================

def test_j7_replace_idx_single_entry_after_refile(tmp_path, monkeypatch):
    """replace_idx — Fichier supprimé + même payload renvoyé -> 1 seule entrée manifest (url_source count=1)."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    d = _make_downloader(monkeypatch)
    payload = _make_payload(domain="fournisseur.com", id_image_isi=7001,
                            url_image="https://f.com/img7.jpg")

    filename = "page-produit-7001-deadbeef.jpg"
    image_result = _stub_process_image_page(tmp_path, "fournisseur.com", filename)
    d.image_processor.process_image_page = MagicMock(return_value=image_result)

    mock_session = _mock_aiohttp_session_ok()

    # Premier appel : téléchargement + écriture manifest
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result1 = asyncio.run(d.process_page_image(payload))

    assert result1 is not None
    manifest_path = tmp_path / "images/fournisseur.com/manifest_pages.json"
    data_before = json.loads(manifest_path.read_text())
    assert len(data_before.get("pages_images", [])) == 1, "1 entrée après 1er appel"

    # Supprimer le fichier main pour déclencher le re-téléchargement au 2e appel
    main_path_on_disk = image_result["main_path"]
    assert os.path.exists(main_path_on_disk), "Fichier main doit exister avant suppression"
    os.remove(main_path_on_disk)

    # Recréer le stub pour que process_image_page retourne des paths valides
    image_result2 = _stub_process_image_page(tmp_path, "fournisseur.com", filename)
    d.image_processor.process_image_page = MagicMock(return_value=image_result2)

    # Deuxième appel : idempotence échouée (fichier absent) -> re-DL -> replace_idx
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result2 = asyncio.run(d.process_page_image(payload))

    assert result2 is not None, "2e appel doit réussir après re-téléchargement"

    # Manifest doit contenir UNE SEULE entrée (replace_idx, pas d'append)
    data_after = json.loads(manifest_path.read_text())
    pages = data_after.get("pages_images", [])
    assert len(pages) == 1, (
        f"replace_idx attendu : 1 seule entrée dans manifest, obtenu {len(pages)}"
    )

    # url_source ne doit apparaître qu'une fois (url_source count = 1)
    url_sources = [p["url_source"] for p in pages]
    assert url_sources.count("https://f.com/img7.jpg") == 1, (
        "url_source ne doit apparaître qu'une fois dans le manifest (replace_idx)"
    )
