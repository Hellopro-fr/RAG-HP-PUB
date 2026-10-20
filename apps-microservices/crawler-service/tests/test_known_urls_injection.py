"""A312 T01 : injection de l'ensemble SFPI actif (known_urls) cote Python.

Deux blocs : le module `app.core.known_urls` (sans lancer start_crawl), puis le cablage
(CrawlRequest, routeur, signature et argv de start_crawl). start_crawl est exerce avec le
meme montage que tests/test_auto_stash_resume_on_start.py : cache_service mocke, spawn mocke.
"""
import ast
import base64
import gzip
import inspect
import json
import os
import textwrap
from collections import namedtuple
from unittest.mock import AsyncMock, Mock

import pytest

from app.core import crawler_manager, known_urls
from app.core.config import settings
from app.core.crawler_manager import CrawlerManager
from app.router import crawler as crawler_router
from app.schemas.crawler import CrawlRequest

URLS = ["https://x.fr/p/a", "https://x.fr/p/b/", "https://x.fr/café?x=1&y=2"]


def make_gz(urls):
    raw = json.dumps(urls, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def make_gz_value(value):
    raw = json.dumps(value).encode("utf-8")
    return base64.b64encode(gzip.compress(raw)).decode("ascii")


def target(tmp_path):
    return os.path.join(str(tmp_path), known_urls.KNOWN_URLS_FILENAME)


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def fake_logger(monkeypatch):
    stub = Mock()
    monkeypatch.setattr(known_urls, "logger", stub)
    return stub


# --------------------------------------------------------------------------- module


def test_valid_payload_writes_file_and_returns_absolute_path(tmp_path, fake_logger):
    result = known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), len(URLS), False)
    assert result == os.path.abspath(target(tmp_path))
    assert read_json(result) == URLS


def test_roundtrip_preserves_unicode_and_slashes(tmp_path, fake_logger):
    result = known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), len(URLS), False)
    with open(result, "rb") as fh:
        content = fh.read().decode("utf-8")
    assert "é" in content
    assert "https://x.fr/p/b/" in content


def test_no_tmp_file_left_after_success(tmp_path, fake_logger):
    known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), len(URLS), False)
    assert sorted(os.listdir(str(tmp_path))) == [known_urls.KNOWN_URLS_FILENAME]


def test_count_mismatch_returns_none_and_removes_existing_file(tmp_path, fake_logger):
    with open(target(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    result = known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), len(URLS) + 1, False)
    assert result is None
    assert not os.path.exists(target(tmp_path))
    assert fake_logger.warning.called


def test_invalid_base64_returns_none(tmp_path, fake_logger):
    assert known_urls.prepare_known_urls_file(str(tmp_path), "!!!not-base64!!!", 1, False) is None
    assert not os.path.exists(target(tmp_path))
    assert fake_logger.warning.called


def test_valid_base64_not_gzip_returns_none(tmp_path, fake_logger):
    not_gzip = base64.b64encode(b'["https://x.fr/"]').decode("ascii")
    assert known_urls.prepare_known_urls_file(str(tmp_path), not_gzip, 1, False) is None
    assert not os.path.exists(target(tmp_path))


def test_payload_not_a_list_of_strings_returns_none(tmp_path, fake_logger):
    for value, count in (({"a": 1}, 1), ([1, 2], 2), (["https://x.fr/", 2], 2)):
        result = known_urls.prepare_known_urls_file(str(tmp_path), make_gz_value(value), count, False)
        assert result is None
        assert not os.path.exists(target(tmp_path))


def test_absent_fields_fresh_run_removes_stale_file(tmp_path, fake_logger):
    with open(target(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    assert known_urls.prepare_known_urls_file(str(tmp_path), None, None, False) is None
    assert not os.path.exists(target(tmp_path))
    assert fake_logger.info.called
    assert not fake_logger.warning.called


def test_absent_fields_restart_keeps_existing_file(tmp_path, fake_logger):
    with open(target(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    result = known_urls.prepare_known_urls_file(str(tmp_path), None, None, True)
    assert result == os.path.abspath(target(tmp_path))
    assert read_json(result) == ["https://old.fr/"]
    assert not fake_logger.warning.called


def test_absent_fields_restart_without_file_returns_none(tmp_path, fake_logger):
    assert known_urls.prepare_known_urls_file(str(tmp_path), None, None, True) is None


def test_only_one_field_counts_as_absent(tmp_path, fake_logger):
    with open(target(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    assert known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), None, False) is None
    assert not os.path.exists(target(tmp_path))


def test_missing_storage_dir_never_raises(tmp_path, fake_logger):
    missing = os.path.join(str(tmp_path), "absent")
    assert known_urls.prepare_known_urls_file(missing, make_gz(URLS), len(URLS), False) is None
    assert fake_logger.warning.called


def test_replace_failure_leaves_no_tmp_and_no_target(tmp_path, fake_logger, monkeypatch):
    def boom(src, dst):
        raise OSError("replace refused")
    monkeypatch.setattr(known_urls.os, "replace", boom)
    assert known_urls.prepare_known_urls_file(str(tmp_path), make_gz(URLS), len(URLS), False) is None
    assert os.listdir(str(tmp_path)) == []


def test_warning_does_not_echo_payload(tmp_path, fake_logger):
    marker = "ZZ-PAYLOAD-MARKER-ZZ"
    known_urls.prepare_known_urls_file(str(tmp_path), marker, 1, False)
    assert fake_logger.warning.called
    assert marker not in str(fake_logger.warning.call_args_list)


# --------------------------------------------------------------------------- wiring


def keyword_names_of_calls(func):
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return {kw.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for kw in node.keywords}


def make_request(**extra):
    return CrawlRequest(id="900", domain="x.fr", start_url="https://x.fr/",
                        callback_url="https://cb.example/", **extra)


def test_crawl_request_declares_the_two_optional_fields():
    fields = CrawlRequest.model_fields
    assert fields["known_urls_gz"].default is None
    assert fields["known_urls_count"].default is None


def test_start_crawl_signature_ends_with_the_two_keywords():
    params = inspect.signature(CrawlerManager.start_crawl).parameters
    names = list(params)
    assert names[-2:] == ["known_urls_gz", "known_urls_count"]
    assert params["known_urls_gz"].default is None
    assert params["known_urls_count"].default is None


@pytest.mark.asyncio
async def test_router_forwards_fields_as_kwargs_not_params(monkeypatch):
    start = AsyncMock(return_value="900")
    monkeypatch.setattr(crawler_router.crawler_manager, "start_crawl", start)
    gz = make_gz(URLS)
    await crawler_router.start_new_crawl(make_request(known_urls_gz=gz, known_urls_count=len(URLS)))
    kwargs = start.await_args.kwargs
    assert kwargs["known_urls_gz"] == gz
    assert kwargs["known_urls_count"] == len(URLS)
    assert not [k for k in kwargs["params"] if k.lower().startswith("knownurls")]


@pytest.mark.asyncio
async def test_router_without_fields_forwards_none(monkeypatch):
    start = AsyncMock(return_value="900")
    monkeypatch.setattr(crawler_router.crawler_manager, "start_crawl", start)
    await crawler_router.start_new_crawl(make_request())
    kwargs = start.await_args.kwargs
    assert kwargs["known_urls_gz"] is None
    assert kwargs["known_urls_count"] is None


def test_oom_relaunch_does_not_forward_the_fields():
    names = keyword_names_of_calls(CrawlerManager._relaunch_oom_crawl)
    assert "is_restart" in names  # temoin : l'appel a start_crawl est bien vu
    assert {"known_urls_gz", "known_urls_count"}.isdisjoint(names)


def start_env(monkeypatch, tmp_path):
    """CrawlerManager dont start_crawl va jusqu'au spawn (mocke). Rend (manager, spawn)."""
    uname_result = namedtuple("uname_result", ["sysname", "nodename", "release", "version", "machine"])
    monkeypatch.setattr(os, "uname",
                        lambda: uname_result("Linux", "test-replica", "5.0", "#1", "x86_64"),
                        raising=False)
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))
    cache_mocks = {
        "get_key": AsyncMock(side_effect=["10", "1"]),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(return_value=2),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
        "get_json": AsyncMock(return_value=None),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(crawler_manager.cache_service, name, mock, raising=False)
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)

    manager = CrawlerManager()
    manager.local_processes = {}
    monkeypatch.setattr(manager, "_publish_update", AsyncMock())

    async def noop_monitor(*a, **k):
        return None
    monkeypatch.setattr(manager, "_monitor_process", noop_monitor)

    fake_proc = Mock()
    fake_proc.pid = 12345
    spawn = AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(crawler_manager.asyncio, "create_subprocess_exec", spawn)
    return manager, spawn


def job_known_urls_path(tmp_path):
    return os.path.abspath(os.path.join(str(tmp_path), "900", known_urls.KNOWN_URLS_FILENAME))


async def call_start(manager, is_restart=False, **extra):
    return await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None,
        params={"perminute": 100}, is_restart=is_restart, **extra)


def spawned_argv(spawn):
    return list(spawn.await_args.args)


@pytest.mark.asyncio
async def test_start_crawl_writes_file_and_adds_argv_after_params(monkeypatch, tmp_path):
    manager, spawn = start_env(monkeypatch, tmp_path)
    await call_start(manager, known_urls_gz=make_gz(URLS), known_urls_count=len(URLS))
    argv = spawned_argv(spawn)
    expected = f"--knownUrlsFile={job_known_urls_path(tmp_path)}"
    assert argv.count(expected) == 1
    assert argv.index(expected) > argv.index("--perminute=100")
    assert read_json(job_known_urls_path(tmp_path)) == URLS
    assert not [a for a in argv if len(a) > 1000]  # le base64 n'entre jamais dans l'argv


@pytest.mark.asyncio
async def test_start_crawl_without_fields_removes_stale_file_and_no_argv(monkeypatch, tmp_path):
    manager, spawn = start_env(monkeypatch, tmp_path)
    os.makedirs(os.path.join(str(tmp_path), "900"))
    with open(job_known_urls_path(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    await call_start(manager)
    assert not os.path.exists(job_known_urls_path(tmp_path))
    assert not [a for a in spawned_argv(spawn) if a.startswith("--knownUrlsFile")]


@pytest.mark.asyncio
async def test_start_crawl_restart_keeps_file_and_readds_argv(monkeypatch, tmp_path):
    manager, spawn = start_env(monkeypatch, tmp_path)
    os.makedirs(os.path.join(str(tmp_path), "900"))
    with open(job_known_urls_path(tmp_path), "w", encoding="utf-8") as fh:
        fh.write('["https://old.fr/"]')
    await call_start(manager, is_restart=True)
    assert f"--knownUrlsFile={job_known_urls_path(tmp_path)}" in spawned_argv(spawn)
    assert read_json(job_known_urls_path(tmp_path)) == ["https://old.fr/"]


@pytest.mark.asyncio
async def test_start_crawl_with_bad_payload_still_spawns_without_argv(monkeypatch, tmp_path):
    manager, spawn = start_env(monkeypatch, tmp_path)
    crawl_id = await call_start(manager, known_urls_gz="!!!not-base64!!!", known_urls_count=3)
    assert crawl_id == "900"
    assert spawn.await_count == 1
    assert not [a for a in spawned_argv(spawn) if a.startswith("--knownUrlsFile")]
