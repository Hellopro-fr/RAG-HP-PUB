"""Tests pour le service album_products."""

import asyncio
import json
from pathlib import Path

import pytest

from conftest import _patch_package_imports


def _setup(monkeypatch, tmp_path):
    _patch_package_imports(monkeypatch)
    images_base = tmp_path / "images"
    images_base.mkdir()
    return images_base


def _seed_domain(images_base: Path, domain: str, products: list, last_updated: str = "2026-04-26T10:00:00"):
    d = images_base / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"products": products, "last_updated": last_updated}))


def _make_product(id_produit: str, nom: str, images: list, synced: bool = True, last_update: str = "2026-04-26T10:00:00"):
    return {"id_produit": id_produit, "nom": nom, "synced": synced, "last_update": last_update, "images": images}


def _make_image(filename: str, url: str = "https://x/y.jpg"):
    return {"filename": filename, "url_source": url, "main": f"produit-2/0/0/0/{filename}", "thumb": f"produit-3/0/0/0/{filename}"}


def test_unknown_domain_raises(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    from services.album_products import list_products
    with pytest.raises(FileNotFoundError):
        asyncio.run(list_products(str(tmp_path), "ghost.com"))


def test_empty_domain_returns_empty_paginated(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    (images_base / "alpha.com").mkdir()
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com"))
    assert r == {"domain": "alpha.com", "products": [], "page": 1, "page_size": 100, "total": 0, "next_page": None}


def test_pagination_basic(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    products = [_make_product(str(i), f"nom-{i}", []) for i in range(150)]
    _seed_domain(images_base, "alpha.com", products)
    from services.album_products import list_products
    r1 = asyncio.run(list_products(str(tmp_path), "alpha.com", page=1, page_size=100))
    assert len(r1["products"]) == 100
    assert r1["total"] == 150
    assert r1["next_page"] == 2
    r2 = asyncio.run(list_products(str(tmp_path), "alpha.com", page=2, page_size=100))
    assert len(r2["products"]) == 50
    assert r2["next_page"] is None


def test_search_q_substring(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed_domain(images_base, "alpha.com", [
        _make_product("60001", "perceuse-bosch", []),
        _make_product("60002", "scie-makita", []),
        _make_product("60003", "PERCEUSE-Dewalt", []),
    ])
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com", q="perceuse"))
    assert {p["id_produit"] for p in r["products"]} == {"60001", "60003"}


def test_filter_pending(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed_domain(images_base, "alpha.com", [
        _make_product("1", "a", [], synced=True),
        _make_product("2", "b", [], synced=False),
    ])
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com", filter="pending"))
    assert [p["id_produit"] for p in r["products"]] == ["2"]


def test_sort_name_desc(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed_domain(images_base, "alpha.com", [
        _make_product("1", "alpha", []),
        _make_product("2", "charlie", []),
        _make_product("3", "bravo", []),
    ])
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com", sort="name_desc"))
    assert [p["nom"] for p in r["products"]] == ["charlie", "bravo", "alpha"]


def test_image_status_ok_when_file_exists(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    main_rel = "produit-2/0/0/0/file.jpg"
    (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0").mkdir(parents=True)
    (images_base / "alpha.com" / "produit-2" / "0" / "0" / "0" / "file.jpg").write_bytes(b"x")
    _seed_domain(images_base, "alpha.com", [_make_product("1", "p", [_make_image("file.jpg")])])
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com"))
    assert r["products"][0]["images"][0]["status"] == "ok"


def test_image_status_orphan_manifest_when_file_missing(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _seed_domain(images_base, "alpha.com", [_make_product("1", "p", [_make_image("missing.jpg")])])
    from services.album_products import list_products
    r = asyncio.run(list_products(str(tmp_path), "alpha.com"))
    assert r["products"][0]["images"][0]["status"] == "orphan_manifest"
