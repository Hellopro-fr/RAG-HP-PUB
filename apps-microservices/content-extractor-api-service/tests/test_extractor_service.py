import asyncio

from app.core import extractor_service
from app.schemas.clean import OutputFormat

MAIN = "<html><body><header>Nav</header><main>Body text here.</main><footer>Footer</footer></body></html>"
REF1 = "<html><body><header>Nav</header><main>Other.</main><footer>Footer</footer></body></html>"
REF2 = "<html><body><header>Nav</header><main>Third.</main><footer>Footer</footer></body></html>"


def test_run_clean_returns_body_dict():
    body = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))
    assert set(body) == {"content", "format", "content_length"}
    assert body["format"] == "text"
    assert body["content_length"] == len(body["content"])


def test_run_header_footer_returns_body_dict():
    body = asyncio.run(extractor_service.run_header_footer(MAIN, [REF1, REF2], debug=False))
    assert {"header", "footer", "header_method", "footer_method"} <= set(body)


def test_run_clean_does_not_block_event_loop():
    async def scenario():
        ticked = {"n": 0}

        async def ticker():
            for _ in range(5):
                await asyncio.sleep(0.001)
                ticked["n"] += 1

        big = "<html><body>" + ("<p>x</p>" * 20000) + "</body></html>"
        await asyncio.gather(extractor_service.run_clean(big, OutputFormat.TEXT), ticker())
        return ticked["n"]

    assert asyncio.run(scenario()) == 5


def test_run_clean_uses_cache(monkeypatch):
    calls = {"n": 0}

    async def fake_get(key):
        return {"content": "CACHED", "format": "text", "content_length": 6} if calls["n"] else None

    async def fake_set(key, body):
        calls["n"] += 1

    monkeypatch.setattr(extractor_service.result_cache, "get", fake_get)
    monkeypatch.setattr(extractor_service.result_cache, "set", fake_set)

    first = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))   # miss -> compute + set
    second = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))  # hit
    assert second["content"] == "CACHED"
    assert first["content"] != "CACHED"


def test_force_refresh_skips_read(monkeypatch):
    seen = {"get": 0}

    async def fake_get(key):
        seen["get"] += 1
        return {"content": "CACHED", "format": "text", "content_length": 6}

    async def fake_set(key, body):
        pass

    monkeypatch.setattr(extractor_service.result_cache, "get", fake_get)
    monkeypatch.setattr(extractor_service.result_cache, "set", fake_set)
    body = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT, force_refresh=True))
    assert seen["get"] == 0
    assert body["content"] != "CACHED"


import types


def test_run_batch_order_and_failure_isolation(monkeypatch):
    async def fake_run_clean(html, fmt, force_refresh=False):
        if html == "BOOM":
            raise RuntimeError("kaboom")
        return {"content": html, "format": fmt.value, "content_length": len(html)}

    monkeypatch.setattr(extractor_service, "run_clean", fake_run_clean)

    items = [
        types.SimpleNamespace(html="A", format=OutputFormat.TEXT),
        types.SimpleNamespace(html="BOOM", format=OutputFormat.TEXT),
        types.SimpleNamespace(html="C", format=OutputFormat.TEXT),
    ]
    seen = {"max": 0}
    results = asyncio.run(extractor_service.run_batch(
        "clean", items, max_concurrency=2, force_refresh=False,
        progress_cb=lambda d: seen.__setitem__("max", d),
    ))
    assert [r.get("content", r.get("error")) for r in results] == ["A", "kaboom", "C"]
    assert seen["max"] == 3
