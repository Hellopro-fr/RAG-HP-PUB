"""Tests pour le service album_summary."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from conftest import _patch_package_imports


def _write_manifest(domain_dir: Path, manifest: dict):
    domain_dir.mkdir(parents=True, exist_ok=True)
    (domain_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _setup(monkeypatch, tmp_path):
    _patch_package_imports(monkeypatch)
    images_base = tmp_path / "images"
    images_base.mkdir()
    monkeypatch.setenv("STORAGE_BASE", str(tmp_path))
    return images_base


def test_empty_filesystem_returns_empty(tmp_path, monkeypatch):
    _setup(monkeypatch, tmp_path)
    from services.album_summary import list_domains_with_stats
    result = asyncio.run(list_domains_with_stats(str(tmp_path)))
    assert result == {"domains": [], "total": 0}


def test_two_domains_with_manifests(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    _write_manifest(images_base / "alpha.com", {
        "products": [
            {"id_produit": "1", "synced": True, "images": [{"filename": "a.jpg"}, {"filename": "b.jpg"}]},
            {"id_produit": "2", "synced": False, "images": [{"filename": "c.jpg"}]},
        ],
        "last_updated": "2026-04-26T10:00:00",
    })
    _write_manifest(images_base / "beta.com", {
        "products": [{"id_produit": "9", "synced": True, "images": []}],
        "last_updated": "2026-04-25T08:30:00",
    })

    from services.album_summary import list_domains_with_stats
    result = asyncio.run(list_domains_with_stats(str(tmp_path)))

    assert result["total"] == 2
    domains = {d["domain"]: d for d in result["domains"]}
    assert domains["alpha.com"]["product_count"] == 2
    assert domains["alpha.com"]["image_count"] == 3
    assert domains["alpha.com"]["synced_count"] == 1
    assert domains["alpha.com"]["unsynced_count"] == 1
    assert domains["alpha.com"]["last_update"] == "2026-04-26T10:00:00"
    assert domains["beta.com"]["product_count"] == 1
    # Tri ASC
    assert [d["domain"] for d in result["domains"]] == ["alpha.com", "beta.com"]


def test_corrupted_manifest_yields_zero_counts(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    (images_base / "broken.com").mkdir(parents=True)
    (images_base / "broken.com" / "manifest.json").write_text("not json{")

    from services.album_summary import list_domains_with_stats
    result = asyncio.run(list_domains_with_stats(str(tmp_path)))

    assert len(result["domains"]) == 1
    assert result["domains"][0]["domain"] == "broken.com"
    assert result["domains"][0]["product_count"] == 0
    assert result["domains"][0]["last_update"] is None


def test_missing_manifest_yields_zero_counts(tmp_path, monkeypatch):
    images_base = _setup(monkeypatch, tmp_path)
    (images_base / "no-manifest.com").mkdir(parents=True)

    from services.album_summary import list_domains_with_stats
    result = asyncio.run(list_domains_with_stats(str(tmp_path)))

    assert len(result["domains"]) == 1
    assert result["domains"][0]["product_count"] == 0
