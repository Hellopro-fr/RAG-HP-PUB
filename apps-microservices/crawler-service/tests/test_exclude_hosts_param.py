"""A545 : paramètre exclude_hosts (alias excludehosts) côté Python.

Preuve de « Réussi si » 3 : un démarrage avec exclude_hosts produit --excludehosts=… sur la ligne
de commande du job ; sans le champ (ou avec une liste vide), la ligne de commande est identique à
celle d'avant ; après une relance OOM (crawler_manager.py reprend job_info["params"]), l'argument
est toujours là. Même montage que tests/test_known_urls_injection.py : cache_service mocké, spawn
mocké, aucun crawler lancé.
"""
import os
from collections import namedtuple
from unittest.mock import AsyncMock, Mock

import pytest

from app.core import crawler_manager
from app.core.config import settings
from app.core.crawler_manager import CrawlerManager
from app.router import crawler as crawler_router
from app.schemas.crawler import CrawlRequest


# Montage repris de tests/test_known_urls_injection.py (make_request, start_env, spawned_argv) :
# recopié plutôt qu'importé, tests/ n'étant pas un paquet.
def make_request(**extra):
    return CrawlRequest(id="900", domain="x.fr", start_url="https://x.fr/",
                        callback_url="https://cb.example/", **extra)


def start_env(monkeypatch, tmp_path):
    """CrawlerManager dont start_crawl va jusqu'au spawn (mocké). Rend (manager, spawn)."""
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


def spawned_argv(spawn):
    return list(spawn.await_args.args)


async def router_params(monkeypatch, request):
    """params que le routeur transmet à start_crawl pour `request`."""
    start = AsyncMock(return_value="900")
    monkeypatch.setattr(crawler_router.crawler_manager, "start_crawl", start)
    await crawler_router.start_new_crawl(request)
    return start.await_args.kwargs["params"]


async def spawn_argv(monkeypatch, tmp_path, params, is_restart=False):
    """argv du job lancé par start_crawl avec `params` (spawn mocké)."""
    manager, spawn = start_env(monkeypatch, tmp_path)
    await manager.start_crawl(
        domain="x.fr", start_url="https://x.fr/", crawl_id="900",
        callback_url="https://cb", failure_callback_url=None,
        params=dict(params), is_restart=is_restart)
    return spawned_argv(spawn), manager


def test_schema_accepts_the_field_and_its_alias():
    assert CrawlRequest.model_fields["exclude_hosts"].default is None
    assert make_request(exclude_hosts=["a.example.com"]).exclude_hosts == ["a.example.com"]
    assert make_request(excludehosts=["a.example.com"]).exclude_hosts == ["a.example.com"]


@pytest.mark.asyncio
async def test_router_joins_the_hosts(monkeypatch):
    params = await router_params(monkeypatch, make_request(exclude_hosts=["a.example.com", " b.example.com ", ""]))
    assert params["excludehosts"] == "a.example.com;b.example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"exclude_hosts": []}, {"exclude_hosts": ["", "  "]}])
async def test_router_without_hosts_sends_none(monkeypatch, extra):
    params = await router_params(monkeypatch, make_request(**extra))
    assert params["excludehosts"] is None


@pytest.mark.asyncio
async def test_argv_carries_the_hosts(monkeypatch, tmp_path):
    params = await router_params(monkeypatch, make_request(exclude_hosts=["a.example.com"]))
    argv, _ = await spawn_argv(monkeypatch, tmp_path, params)
    assert argv.count("--excludehosts=a.example.com") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{}, {"exclude_hosts": []}])
async def test_argv_without_hosts_is_identical_to_before(monkeypatch, tmp_path, extra):
    params = await router_params(monkeypatch, make_request(**extra))
    # « Avant » = les mêmes params sans la clé ajoutée par A545.
    before = {k: v for k, v in params.items() if k != "excludehosts"}
    argv_before, _ = await spawn_argv(monkeypatch, tmp_path / "before", before)
    argv_after, _ = await spawn_argv(monkeypatch, tmp_path / "after", params)
    strip = lambda argv: [a.replace(str(tmp_path / "before"), "<storage>").replace(str(tmp_path / "after"), "<storage>") for a in argv]
    assert strip(argv_after) == strip(argv_before)
    assert not [a for a in argv_after if a.startswith("--excludehosts")]


@pytest.mark.asyncio
async def test_oom_relaunch_keeps_the_hosts(monkeypatch, tmp_path):
    params = await router_params(monkeypatch, make_request(exclude_hosts=["a.example.com"]))
    # 1. Démarrage : start_crawl range les params dans job_info (Redis).
    _, manager = await spawn_argv(monkeypatch, tmp_path, params)
    stored = [c.args[1] for c in crawler_manager.cache_service.set_json.await_args_list
              if isinstance(c.args[1], dict) and "params" in c.args[1]]
    assert stored, "start_crawl must store job_info with its params"
    job_info = dict(stored[0], status="restarting_oom", oom_restart_count=0)
    assert job_info["params"]["excludehosts"] == "a.example.com"

    # 2. Relance OOM : _relaunch_oom_crawl reprend job_info["params"].
    monkeypatch.setattr(crawler_manager.cache_service, "get_json",
                        AsyncMock(return_value={"status": "restarting_oom"}), raising=False)
    monkeypatch.setattr(crawler_manager.asyncio, "sleep", AsyncMock())
    relaunch = AsyncMock(return_value="900")
    monkeypatch.setattr(manager, "start_crawl", relaunch)
    await manager._relaunch_oom_crawl(job_info)
    kwargs = relaunch.await_args.kwargs
    assert kwargs["is_restart"] is True
    assert kwargs["params"]["excludehosts"] == "a.example.com"

    # 3. Le job relancé porte toujours l'argument.
    argv, _ = await spawn_argv(monkeypatch, tmp_path / "restart", kwargs["params"], is_restart=True)
    assert "--excludehosts=a.example.com" in argv
