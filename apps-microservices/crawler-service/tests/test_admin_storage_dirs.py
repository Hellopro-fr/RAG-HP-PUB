"""Tests for GET /admin/storage-dirs (per-crawl storage inventory)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_root(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    root = tmp_path / "storage"
    root.mkdir()
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(root), raising=False)
    # Default Redis fake: no blob for any crawl (present: false).
    from common_utils.redis import cache_service

    async def no_blob(key):
        return None

    monkeypatch.setattr(cache_service, "get_json", no_blob, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app), root


def _plant_three_dirs(root):
    """crawl-a: storage/ subtree with a nested file; crawl-b: empty;
    crawl-c: sidecar files only. Plus a stray file at root (must be skipped)."""
    a = root / "crawl-a"
    (a / "storage" / "datasets").mkdir(parents=True)
    (a / "storage" / "datasets" / "item.json").write_text("x" * 100, encoding="utf-8")
    (a / "crawler.log").write_text("y" * 50, encoding="utf-8")
    (root / "crawl-b").mkdir()
    c = root / "crawl-c"
    c.mkdir()
    (c / "_exit_reason.json").write_text("{}", encoding="utf-8")
    (c / "timing-summary.json").write_text("{}", encoding="utf-8")
    (root / "stray-file.txt").write_text("not a dir", encoding="utf-8")


def test_empty_root(client_and_root):
    client, _ = client_and_root
    resp = client.get("/admin/storage-dirs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_dirs"] == 0
    assert body["dirs"] == []
    assert body["returned"] == 0
    assert "error" not in body


def test_lists_dirs_sorted_skips_root_files(client_and_root):
    client, root = client_and_root
    _plant_three_dirs(root)
    body = client.get("/admin/storage-dirs").json()
    assert body["total_dirs"] == 3
    names = [d["name"] for d in body["dirs"]]
    assert names == ["crawl-a", "crawl-b", "crawl-c"]  # sorted, no stray-file.txt
    by_name = {d["name"]: d for d in body["dirs"]}
    assert by_name["crawl-a"]["has_storage_subtree"] is True
    assert by_name["crawl-b"]["has_storage_subtree"] is False
    assert by_name["crawl-c"]["has_storage_subtree"] is False
    assert by_name["crawl-a"]["top_entry_count"] == 2  # storage/ + crawler.log
    assert by_name["crawl-b"]["top_entry_count"] == 0
    assert by_name["crawl-c"]["top_entry_count"] == 2
    for d in body["dirs"]:
        assert d["mtime_age_seconds"] >= 0
        assert "size_bytes" not in d  # only present when sizes=true


def test_pagination(client_and_root):
    client, root = client_and_root
    _plant_three_dirs(root)
    body = client.get("/admin/storage-dirs", params={"offset": 1, "limit": 1}).json()
    assert body["total_dirs"] == 3
    assert body["returned"] == 1
    assert [d["name"] for d in body["dirs"]] == ["crawl-b"]


def test_limit_clamped(client_and_root):
    client, _ = client_and_root
    body = client.get("/admin/storage-dirs", params={"limit": 9999}).json()
    assert body["limit"] == 500


def test_sizes_true_computes_recursive_size(client_and_root):
    client, root = client_and_root
    _plant_three_dirs(root)
    body = client.get("/admin/storage-dirs", params={"sizes": "true"}).json()
    assert body["sizes"] is True
    assert body["sizing_budget_hit"] is False
    by_name = {d["name"]: d for d in body["dirs"]}
    assert by_name["crawl-a"]["size_bytes"] == 150  # 100 nested + 50 crawler.log
    assert by_name["crawl-b"]["size_bytes"] == 0


def test_sizing_budget_exhausted(client_and_root, monkeypatch):
    import app.router.admin as admin_mod
    monkeypatch.setattr(admin_mod, "_STORAGE_DIRS_SIZING_BUDGET_S", 0)
    client, root = client_and_root
    _plant_three_dirs(root)
    body = client.get("/admin/storage-dirs", params={"sizes": "true"}).json()
    assert body["sizing_budget_hit"] is True
    assert all(d["size_bytes"] is None for d in body["dirs"])


def test_redis_join_status(client_and_root, monkeypatch):
    from common_utils.redis import cache_service

    async def fake_get_json(key):
        if key == "crawl_job:crawl-a":
            return {"status": "archived", "stashed_at": None}
        return None

    monkeypatch.setattr(cache_service, "get_json", fake_get_json, raising=False)
    client, root = client_and_root
    _plant_three_dirs(root)
    body = client.get("/admin/storage-dirs").json()
    by_name = {d["name"]: d for d in body["dirs"]}
    assert by_name["crawl-a"]["redis"] == {
        "present": True, "status": "archived", "stashed_at": None}
    assert by_name["crawl-b"]["redis"] == {
        "present": False, "status": None, "stashed_at": None}


def test_redis_failure_fail_open(client_and_root, monkeypatch):
    from common_utils.redis import cache_service

    async def boom(key):
        raise ConnectionError("Redis is not connected.")

    monkeypatch.setattr(cache_service, "get_json", boom, raising=False)
    client, root = client_and_root
    _plant_three_dirs(root)
    resp = client.get("/admin/storage-dirs")
    assert resp.status_code == 200
    for d in resp.json()["dirs"]:
        assert "error" in d["redis"]


def test_missing_root_fail_open(client_and_root, monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH",
                        str(tmp_path / "does-not-exist"), raising=False)
    client, _ = client_and_root
    resp = client.get("/admin/storage-dirs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_dirs"] == 0
    assert body["dirs"] == []
    assert body["error"]


def test_auth_enforced_when_key_set(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", "k", raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    c = TestClient(app)
    assert c.get("/admin/storage-dirs").status_code == 401
