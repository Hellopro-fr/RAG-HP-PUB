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
import tarfile

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


# --- Archived branch (GCS retrieve + extract) ------------------------------
#
# Drives the archived sub-block of get_single_url_html. The local dataset is
# ABSENT so the branch fires: _retrieve_from_gcs_daemon (mocked) returns a REAL
# tmp .tar.gz holding storage/datasets/{domain}/000000001.json + html_index.json,
# which the manager extracts into job_info["storage_path"] so _dataset_dir_for_job
# then resolves. The ownership-lock helpers are stubbed so no live Redis is needed.


def _build_archive_tar(tmp_path, domain="x.fr"):
    """Write a real {tmp}/src.tar.gz whose members are storage/datasets/{domain}/...
    mirroring _generate_archive_sync's layout. Returns (tar_path, record_url, content)."""
    src_dir = tmp_path / "src"
    dataset_dir = src_dir / "storage" / "datasets" / domain
    dataset_dir.mkdir(parents=True, exist_ok=True)

    record_url = "https://www.x.fr/produit/abc"
    content = "<html>ARCHIVED ABC</html>"
    (dataset_dir / "000000001.json").write_text(
        json.dumps({"url": record_url, "content": content}), encoding="utf-8"
    )
    mgr = _make_manager()
    index = {mgr._normalize_url_key(record_url): "000000001.json"}
    (dataset_dir / "html_index.json").write_text(
        json.dumps({"version": "1.0", "domain": domain, "index": index}), encoding="utf-8"
    )

    tar_path = str(tmp_path / "src.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        # arcname "" so members are stored as storage/datasets/{domain}/...
        tar.add(str(src_dir), arcname="")
    return tar_path, record_url, content


def _stub_locks(mgr, granted=True):
    """Stub the ownership-lock helpers on the instance so no Redis is touched.
    granted=False simulates a competing holder (acquire returns None)."""
    async def _acquire(lock_key, ttl_seconds):
        return "test-lock-value" if granted else None

    async def _release(lock_key, expected_value):
        return True

    mgr._acquire_ownership_lock = _acquire
    mgr._release_ownership_lock = _release


@pytest.mark.asyncio
async def test_archived_extracts_then_serves(tmp_path, monkeypatch):
    """Archived crawl, no local dataset -> retrieve tar from GCS, extract, serve.
    A SECOND call must NOT re-retrieve/re-extract (double-checked lock skip) yet
    still return the content from the now-present dataset."""
    tar_path, record_url, content = _build_archive_tar(tmp_path)
    storage_path = str(tmp_path / "job")  # empty: forces the archived branch

    mgr = _make_manager()
    _stub_locks(mgr, granted=True)

    calls = {"n": 0}

    async def _fake_retrieve(crawl_id):
        calls["n"] += 1
        return tar_path

    mgr._retrieve_from_gcs_daemon = _fake_retrieve

    job_info = {"crawl_id": "99", "status": "archived",
                "storage_path": storage_path, "domain": "x.fr"}

    # First call: branch fires, extracts, serves.
    first = await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc/")
    assert first == content
    assert calls["n"] == 1
    assert os.path.isdir(os.path.join(storage_path, "storage", "datasets", "x.fr"))

    # Second call: dataset now exists -> archived branch's `not dataset_dir` is
    # False at the top, so retrieve/extract never run again.
    second = await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc/")
    assert second == content
    assert calls["n"] == 1, "extract/retrieve must not run a second time"


@pytest.mark.asyncio
async def test_archived_double_checked_skip_when_dir_appears_under_lock(tmp_path, monkeypatch):
    """Double-checked locking: if the dataset dir materializes AFTER lock acquire
    (another caller extracted while we waited), we must NOT re-extract — we serve
    the existing dir. Simulated by having the acquire stub create the dataset."""
    tar_path, record_url, content = _build_archive_tar(tmp_path)
    storage_path = str(tmp_path / "job")

    mgr = _make_manager()

    calls = {"n": 0}

    async def _fake_retrieve(crawl_id):
        calls["n"] += 1
        return tar_path

    mgr._retrieve_from_gcs_daemon = _fake_retrieve

    # acquire stub extracts the tar into storage_path BEFORE returning the lock,
    # mimicking a competitor that finished extraction while we were blocked.
    async def _acquire(lock_key, ttl_seconds):
        dataset_dir = os.path.join(storage_path, "storage", "datasets", "x.fr")
        os.makedirs(dataset_dir, exist_ok=True)
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=storage_path, filter="data")
        return "test-lock-value"

    async def _release(lock_key, expected_value):
        return True

    mgr._acquire_ownership_lock = _acquire
    mgr._release_ownership_lock = _release

    job_info = {"crawl_id": "99", "status": "archived",
                "storage_path": storage_path, "domain": "x.fr"}

    result = await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc/")
    assert result == content
    assert calls["n"] == 0, "post-lock re-check must skip retrieve/extract when dir exists"


@pytest.mark.asyncio
async def test_archived_extract_failure_cleans_partial_dir(tmp_path, monkeypatch):
    """A corrupt archive (extract raises) -> 502 EXTRACT_FAILED and the partial
    extract target is removed (no partial dir left for a later call to mis-serve)."""
    from fastapi import HTTPException

    storage_path = str(tmp_path / "job")
    bad_tar = str(tmp_path / "bad.tar.gz")
    # Not a gzip/tar at all -> tarfile.open(...,'r:gz') raises inside _extract.
    with open(bad_tar, "wb") as f:
        f.write(b"this is not a tar archive")

    mgr = _make_manager()
    _stub_locks(mgr, granted=True)

    async def _fake_retrieve(crawl_id):
        return bad_tar

    mgr._retrieve_from_gcs_daemon = _fake_retrieve

    job_info = {"crawl_id": "99", "status": "archived",
                "storage_path": storage_path, "domain": "x.fr"}

    with pytest.raises(HTTPException) as exc_info:
        await mgr.get_single_url_html(job_info, "http://www.x.fr/produit/abc/")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error_code"] == "EXTRACT_FAILED"
    # Partial extract target must be gone.
    assert not os.path.isdir(storage_path)
