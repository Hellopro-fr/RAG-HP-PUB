"""Tests du flow process_product avec logique set-based (Task 2).

Conventions :
- Import via `from core.*` (pythonpath = app dans pytest.ini)
- asyncio.run() au lieu de @pytest.mark.asyncio (pytest-asyncio non installé)
- monkeypatch sur core.downloader._STORAGE_BASE pour isoler le storage
- mock de download_and_process via monkeypatch.setattr(instance, ...)
"""

import json
import asyncio
import os
import pytest

from conftest import _patch_package_imports


def _setup_storage(monkeypatch, tmp_path):
    """Redirige _STORAGE_BASE vers tmp_path pour l'isolement des tests."""
    import core.downloader as dl
    monkeypatch.setattr(dl, "_STORAGE_BASE", str(tmp_path))


def _make_downloader(monkeypatch):
    """Instancie un Downloader sans déclencher l'import réel d'ImageProcessor."""
    from unittest.mock import MagicMock
    import core.downloader as dl

    d = dl.Downloader.__new__(dl.Downloader)
    d.image_processor = MagicMock()
    d.proxy_password = None
    d.proxy_url = None
    return d


def _fake_dl_factory(storage_base, domain, slug, product_id, create_stub_files):
    """
    Construit une fonction async qui simule download_and_process :
    crée les fichiers main+thumb sur disque et retourne la structure attendue.
    """
    async def fake(url, domain=domain, product_id=product_id,
                   product_name=None, index=0, **kwargs):
        ext = ".jpg"
        from core.downloader import _build_filename
        fn = _build_filename(slug, product_id, url, ext)
        # Sharding par id_produit (3 derniers chiffres inversés, zero-padded)
        pid_str = str(product_id).zfill(3)
        rep1, rep2, rep3 = pid_str[-1], pid_str[-2], pid_str[-3]
        main_path = f"{storage_base}/images/{domain}/produit-2/{rep1}/{rep2}/{rep3}/{fn}"
        thumb_path = f"{storage_base}/images/{domain}/produit-3/{rep1}/{rep2}/{rep3}/{fn}"
        create_stub_files(main_path, thumb_path)
        return {
            "status": "ok",
            "paths": {
                "main_path": main_path,
                "thumb_path": thumb_path,
                "filename": fn,
                "url_source": url,
            },
        }
    return fake


# =============================================================================
# J1 — Nouveau produit : manifest absent, toutes les URLs téléchargées
# =============================================================================

def test_j1_new_product_downloads_all(tmp_path, monkeypatch, create_stub_files):
    """Nouveau produit (pas de manifest) : 3 URLs → 3 DL, manifest créé avec url_source."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)
    dl_calls = []

    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)

    async def wrapper(url, **kwargs):
        dl_calls.append(url)
        return await fake(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper)

    urls = ["https://f.com/a.jpg", "https://f.com/b.jpg", "https://f.com/c.jpg"]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com",
        "id_produit": "60001",
        "nom_produit": "prodA",
        "url_images": urls,
    }))

    assert dl_calls == urls
    manifest_path = tmp_path / "images/fournisseur.com/manifest.json"
    data = json.loads(manifest_path.read_text())
    assert len(data["products"][0]["images"]) == 3
    for img in data["products"][0]["images"]:
        assert img["url_source"] in urls
        assert img["filename"].startswith("proda-60001-")


# =============================================================================
# J2 — Ajout + substitution : [A,B,C] → [A,B',C,D]
# =============================================================================

def test_j2_reuse_unchanged_urls(tmp_path, monkeypatch, create_stub_files):
    """[A,B,C]→[A,B',C,D] : A et C réutilisés, B' et D téléchargés, B supprimé."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)
    dl_calls = []

    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)

    async def wrapper(url, **kwargs):
        dl_calls.append(url)
        return await fake(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper)

    # Premier passage : [A, B, C]
    urls_j1 = ["https://f.com/a.jpg", "https://f.com/b.jpg", "https://f.com/c.jpg"]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j1,
    }))
    assert len(dl_calls) == 3
    dl_calls.clear()

    # Deuxième passage : [A, B', C, D]
    urls_j2 = [
        "https://f.com/a.jpg", "https://f.com/b-new.jpg",
        "https://f.com/c.jpg", "https://f.com/d.jpg",
    ]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j2,
    }))
    # Seules B' et D doivent avoir été téléchargées (A et C réutilisés)
    assert dl_calls == ["https://f.com/b-new.jpg", "https://f.com/d.jpg"]

    # B doit avoir été supprimé du FS (orphelin)
    from core.downloader import _build_filename
    b_fn = _build_filename("proda", "60001", "https://f.com/b.jpg", ".jpg")
    b_main = tmp_path / f"images/fournisseur.com/produit-2/1/0/0/{b_fn}"
    assert not b_main.exists(), "Le fichier orphelin B doit être supprimé"


# =============================================================================
# J2bis — Réordonnancement : [A,B,C] → [B,A,C] : 0 téléchargement
# =============================================================================

def test_j2bis_reorder_no_download(tmp_path, monkeypatch, create_stub_files):
    """[A,B,C]→[B,A,C] : simple réordonnancement → 0 téléchargement."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)
    dl_calls = []

    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)

    async def wrapper(url, **kwargs):
        dl_calls.append(url)
        return await fake(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper)

    urls_j1 = ["https://f.com/a.jpg", "https://f.com/b.jpg", "https://f.com/c.jpg"]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j1,
    }))
    dl_calls.clear()

    # Même URLs dans un ordre différent
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": [urls_j1[1], urls_j1[0], urls_j1[2]],
    }))
    assert dl_calls == [], "Réordonnancement ne doit produire aucun téléchargement"


# =============================================================================
# J3 — Réduction : [A,B,C,D,E] → [A,X] : B/C/D/E orphelins supprimés
# =============================================================================

def test_j3_shrink_deletes_orphans(tmp_path, monkeypatch, create_stub_files):
    """[A,B,C,D,E]→[A,X] : A réutilisé, X téléchargé, B/C/D/E supprimés du FS."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)

    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)
    monkeypatch.setattr(d, "download_and_process", fake)

    urls_j1 = [f"https://f.com/{c}.jpg" for c in ["a", "b", "c", "d", "e"]]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j1,
    }))

    # Réduction à [A, X]
    urls_j3 = ["https://f.com/a.jpg", "https://f.com/x-new.jpg"]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j3,
    }))

    from core.downloader import _build_filename
    for c in ["b", "c", "d", "e"]:
        fn = _build_filename("proda", "60001", f"https://f.com/{c}.jpg", ".jpg")
        assert not (tmp_path / f"images/fournisseur.com/produit-2/1/0/0/{fn}").exists(), \
            f"Le fichier orphelin {c} doit être supprimé"


# =============================================================================
# V1 legacy — Manifest sans url_source → rebuild complet + suppression fichiers legacy
# =============================================================================

def test_v1_legacy_manifest_triggers_full_rebuild(tmp_path, monkeypatch, create_stub_files):
    """Manifest v1 (sans url_source) → rebuild complet + suppression des fichiers legacy."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)

    # Pré-créer un manifest v1 (sans url_source) + fichiers legacy sur disque
    domain_dir = tmp_path / "images/fournisseur.com"
    (domain_dir / "produit-2/1/0/0").mkdir(parents=True)
    (domain_dir / "produit-3/1/0/0").mkdir(parents=True)
    legacy_fn = "proda-60001-1.jpg"
    (domain_dir / f"produit-2/1/0/0/{legacy_fn}").write_bytes(b"old")
    (domain_dir / f"produit-3/1/0/0/{legacy_fn}").write_bytes(b"old")

    manifest_v1 = {
        "products": [{
            "id_produit": "60001",
            "nom": "prodA",
            "images": [{
                "main": f"produit-2/1/0/0/{legacy_fn}",
                "thumb": f"produit-3/1/0/0/{legacy_fn}",
                "filename": legacy_fn,
                # PAS de url_source — c'est un manifest v1 legacy
            }],
        }],
        "last_updated": "2026-04-20T00:00:00",
    }
    (domain_dir / "manifest.json").write_text(json.dumps(manifest_v1))

    d = _make_downloader(monkeypatch)
    dl_calls = []
    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)

    async def wrapper(url, **kwargs):
        dl_calls.append(url)
        return await fake(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper)

    # Nouveau message avec 2 URLs
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": ["https://f.com/a.jpg", "https://f.com/b.jpg"],
    }))

    # Les 2 URLs doivent avoir été téléchargées (rebuild complet)
    assert len(dl_calls) == 2, f"Rebuild complet attendu, obtenu {dl_calls}"

    # Le fichier legacy doit avoir été supprimé (main et thumb)
    assert not (domain_dir / f"produit-2/1/0/0/{legacy_fn}").exists(), \
        "Le fichier legacy v1 doit être supprimé"
    assert not (domain_dir / f"produit-3/1/0/0/{legacy_fn}").exists(), \
        "Le thumb legacy doit aussi être supprimé"


# =============================================================================
# Échec partiel — Les URLs réussies sont conservées, l'erreur n'arrête pas le traitement
# =============================================================================

def test_download_failure_preserves_others(tmp_path, monkeypatch, create_stub_files):
    """Échec de DL partiel : les URLs réussies conservées, erreurs comptées séparément."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)

    fake = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)

    async def wrapper(url, **kwargs):
        if "bad" in url:
            return {
                "status": "error",
                "reason": "HTTP 500",
                "categorie": "http_server",
                "severite": "error",
            }
        return await fake(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper)

    # Monkeypatch save_error pour éviter les écritures réelles sur FS
    async def noop_save_error(*args, **kwargs):
        pass

    monkeypatch.setattr(d, "save_error", noop_save_error)

    urls = ["https://f.com/a.jpg", "https://f.com/bad.jpg", "https://f.com/c.jpg"]
    result = asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls,
    }))

    # 2 URLs OK, 1 en erreur
    assert len(result.get("processed_images", [])) == 2, \
        f"2 images traitées attendues, obtenu {result.get('processed_images')}"
    assert result.get("download_errors_count", 0) == 1, \
        f"1 erreur attendue, obtenu {result.get('download_errors_count')}"


# =============================================================================
# Échec total — Si toutes les URLs échouent, l'ancien manifest est préservé
# =============================================================================

def test_download_failure_all_fail_preserves_old_manifest(tmp_path, monkeypatch, create_stub_files):
    """Si TOUTES les URLs d'un re-message échouent et qu'un manifest existait → préserver l'ancien manifest."""
    _patch_package_imports(monkeypatch)
    _setup_storage(monkeypatch, tmp_path)
    d = _make_downloader(monkeypatch)

    # Étape 1 : J1 normal — DL initial réussi pour [A, B, C]
    fake_ok = _fake_dl_factory(str(tmp_path), "fournisseur.com", "proda", "60001", create_stub_files)
    dl_calls = []

    async def wrapper_ok(url, **kwargs):
        dl_calls.append(url)
        return await fake_ok(url, **kwargs)

    monkeypatch.setattr(d, "download_and_process", wrapper_ok)

    urls_j1 = ["https://f.com/a.jpg", "https://f.com/b.jpg", "https://f.com/c.jpg"]
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j1,
    }))

    # Vérifier état J1 du manifest
    manifest_path = tmp_path / "images/fournisseur.com/manifest.json"
    manifest_j1 = json.loads(manifest_path.read_text())
    assert len(manifest_j1["products"][0]["images"]) == 3

    # Étape 2 : J2 — toutes les URLs échouent, et URLs sont nouvelles (donc pas réutilisées)
    async def wrapper_all_fail(url, **kwargs):
        return {"status": "error", "reason": "HTTP 500", "categorie": "http_server", "severite": "error"}

    monkeypatch.setattr(d, "download_and_process", wrapper_all_fail)

    async def noop_save_error(*args, **kwargs):
        pass

    monkeypatch.setattr(d, "save_error", noop_save_error)

    urls_j2 = ["https://f.com/x.jpg", "https://f.com/y.jpg"]  # totalement différentes de J1
    asyncio.run(d.process_product({
        "domaine": "fournisseur.com", "id_produit": "60001", "nom_produit": "prodA",
        "url_images": urls_j2,
    }))

    # Vérifier que l'ancien manifest est préservé : 3 images (A, B, C) avec leurs URLs originales
    manifest_after = json.loads(manifest_path.read_text())
    assert len(manifest_after["products"][0]["images"]) == 3, \
        "L'ancien manifest doit être préservé quand tous les DL échouent"
    urls_in_manifest = {img["url_source"] for img in manifest_after["products"][0]["images"]}
    assert urls_in_manifest == set(urls_j1), \
        f"Les URLs du manifest doivent rester celles de J1, got: {urls_in_manifest}"
