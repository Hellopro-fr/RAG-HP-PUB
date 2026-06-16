"""Unit tests for the cold-tier GET /html endpoint logic.

Tested at the manager level (CrawlerManager.get_single_url_html) to avoid the
HTTP/Depends wiring. The happy paths use REAL local files in a tmp dir and must
NOT touch cache_service or GCS — job_info["status"] is kept non-archived and
non-stashed so the unstash / GCS-retrieve branches are never reached.

The dataset layout mirrors the real one: {storage_path}/storage/datasets/{domain}.
The html_index.json shape mirrors what the crawler TS buildHtmlIndex() writes:
{"version": "1.0", "domain": ..., "index": {normalized_url: filename}}.
"""
import json
import os

import pytest

from app.core.crawler_manager import CrawlerManager


def _make_manager():
    """Construct a CrawlerManager without running __init__ (no Redis/daemon side-effects)."""
    return CrawlerManager.__new__(CrawlerManager)


def _write_dataset(tmp_path, domain="x.fr", with_index=True):
    """Create {tmp}/storage/datasets/{domain} with one HTML record + optional index.
    The record's url is HTTPS; the index key is built from that same url via the
    manager's own normalizer so an http query collapses onto it. Returns storage_path."""
    storage_path = str(tmp_path)
    dataset_dir = os.path.join(storage_path, "storage", "datasets", domain)
    os.makedirs(dataset_dir, exist_ok=True)

    record_url = "https://www.x.fr/produit/abc"
    record = {"url": record_url, "content": "<html>ABC PAGE</html>"}
    with open(os.path.join(dataset_dir, "000000001.json"), "w", encoding="utf-8") as f:
        json.dump(record, f)

    if with_index:
        mgr = _make_manager()
        index = {mgr._normalize_url_key(record_url): "000000001.json"}
        with open(os.path.join(dataset_dir, "html_index.json"), "w", encoding="utf-8") as f:
            json.dump({"version": "1.0", "domain": domain, "index": index}, f)

    return storage_path


@pytest.mark.asyncio
async def test_index_hit_returns_content_http_https_collapse(tmp_path):
    """Index hit: query with an http:// URL while the index key was built from the
    https:// record url — proves http/https collapse + that the index is used."""
    storage_path = _write_dataset(tmp_path, with_index=True)
    mgr = _make_manager()
    job_info = {"crawl_id": "42", "status": "finished",
                "storage_path": storage_path, "domain": "x.fr"}

    # http scheme + www + trailing slash — all collapse to the indexed https key.
    content = await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc/")
    assert content == "<html>ABC PAGE</html>"


@pytest.mark.asyncio
async def test_missing_url_returns_none(tmp_path):
    """A URL absent from the dataset returns None (router maps None -> 404)."""
    storage_path = _write_dataset(tmp_path, with_index=True)
    mgr = _make_manager()
    job_info = {"crawl_id": "42", "status": "finished",
                "storage_path": storage_path, "domain": "x.fr"}

    content = await mgr.get_single_url_html(job_info, "https://x.fr/does/not/exist")
    assert content is None


@pytest.mark.asyncio
async def test_scan_fallback_without_index(tmp_path):
    """No html_index.json present -> the dataset scan fallback finds the record."""
    storage_path = _write_dataset(tmp_path, with_index=False)
    mgr = _make_manager()
    job_info = {"crawl_id": "42", "status": "finished",
                "storage_path": storage_path, "domain": "x.fr"}

    assert not os.path.exists(
        os.path.join(storage_path, "storage", "datasets", "x.fr", "html_index.json")
    )
    content = await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc")
    assert content == "<html>ABC PAGE</html>"


@pytest.mark.asyncio
async def test_no_dataset_dir_returns_none(tmp_path):
    """No dataset dir on disk (non-archived) returns None without touching GCS."""
    storage_path = str(tmp_path)  # nothing created under storage/datasets
    mgr = _make_manager()
    job_info = {"crawl_id": "42", "status": "finished",
                "storage_path": storage_path, "domain": "x.fr"}

    content = await mgr.get_single_url_html(job_info, "https://x.fr/produit/abc")
    assert content is None


def test_normalize_url_key_contract():
    """Direct _normalize_url_key assertions — MUST match PHP / TS byte-for-byte."""
    mgr = _make_manager()

    # scheme + www + port + trailing slash dropped; host lowercased
    assert mgr._normalize_url_key("HTTPS://WWW.X.FR:443/Produit/ABC/") == "x.fr/Produit/ABC"
    # http/https collapse (scheme dropped entirely)
    assert mgr._normalize_url_key("http://x.fr/a") == mgr._normalize_url_key("https://x.fr/a")
    # empty query dropped; fragment dropped
    assert mgr._normalize_url_key("https://x.fr/a?#frag") == "x.fr/a"
    # non-empty query kept RAW (no re-encoding)
    assert mgr._normalize_url_key("https://x.fr/a?b=c&d=e") == "x.fr/a?b=c&d=e"
    # accented path kept RAW (no percent-encoding)
    assert mgr._normalize_url_key("https://x.fr/références/") == "x.fr/références"
    # userinfo dropped
    assert mgr._normalize_url_key("https://user:pass@x.fr/a") == "x.fr/a"
    # schemeless / no-authority input returned verbatim minus trailing slash (www NOT stripped)
    assert mgr._normalize_url_key("www.x.fr/a/") == "www.x.fr/a"
