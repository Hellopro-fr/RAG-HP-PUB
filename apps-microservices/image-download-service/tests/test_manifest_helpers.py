import json
import logging
import os
import pytest
from core.downloader import _load_manifest_entry, _delete_image_files


def test_load_entry_missing_file(tmp_path):
    manifest_path = str(tmp_path / "manifest.json")
    assert _load_manifest_entry(manifest_path, "0001") is None


def test_load_entry_product_absent(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"products": [{"id_produit": "0002", "nom": "X", "images": []}]}))
    assert _load_manifest_entry(str(manifest_path), "0001") is None


def test_load_entry_product_present(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    entry = {"id_produit": "0001", "nom": "prodA",
             "images": [{"url_source": "http://x/a.jpg", "main": "m", "thumb": "t", "filename": "f"}]}
    manifest_path.write_text(json.dumps({"products": [entry]}))
    result = _load_manifest_entry(str(manifest_path), "0001")
    assert result == entry


def test_load_entry_corrupt_json(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{ this is not json")
    assert _load_manifest_entry(str(manifest_path), "0001") is None


def test_delete_image_files_removes_both(tmp_path):
    main = tmp_path / "main.jpg"
    thumb = tmp_path / "thumb.jpg"
    main.write_bytes(b"data")
    thumb.write_bytes(b"data")
    _delete_image_files({"main": str(main), "thumb": str(thumb)})
    assert not main.exists()
    assert not thumb.exists()


def test_delete_image_files_missing_logs_warning_no_raise(tmp_path, caplog):
    ghost = tmp_path / "missing.jpg"
    # Doit ne pas lever d'exception même si le fichier n'existe pas
    with caplog.at_level(logging.WARNING):
        _delete_image_files({"main": str(ghost), "thumb": str(ghost)})
    # Le test name promet "logs warning" — vérifier qu'au moins un warning a été émis
    assert any("File to delete not found" in r.message for r in caplog.records), \
        f"Expected warning about missing file, got records: {[r.message for r in caplog.records]}"


def test_delete_image_files_resolves_relative_path(tmp_path):
    # Quand on fournit un chemin relatif + domain, reconstruit le chemin absolu
    storage_base = tmp_path
    domain = "fournisseur.com"
    img_dir = storage_base / "images" / domain / "produit-2" / "1" / "0" / "0"
    img_dir.mkdir(parents=True)
    main_rel = "produit-2/1/0/0/test.jpg"
    thumb_rel = "produit-3/1/0/0/test.jpg"
    (img_dir / "test.jpg").write_bytes(b"x")
    thumb_dir = storage_base / "images" / domain / "produit-3" / "1" / "0" / "0"
    thumb_dir.mkdir(parents=True)
    (thumb_dir / "test.jpg").write_bytes(b"x")
    _delete_image_files({"main": main_rel, "thumb": thumb_rel},
                        storage_base=str(storage_base), domain=domain)
    assert not (img_dir / "test.jpg").exists()
    assert not (thumb_dir / "test.jpg").exists()
