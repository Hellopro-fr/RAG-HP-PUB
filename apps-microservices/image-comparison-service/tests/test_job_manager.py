import asyncio
import json

from common_utils.redis import cache_service
from app.core.job_manager import job_manager
from app.schemas.comparator import ImageInput, JobStatus


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, ex=None):
        self.kv[k] = v
        return True


def test_write_inputs_pending_then_resolved(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    imgs = [ImageInput(url="https://e.com/a.jpg"), ImageInput(content="Zm9v")]
    url_id, b64_id = imgs[0].id, imgs[1].id

    asyncio.run(job_manager._write_inputs("J1", imgs))
    payload = json.loads(fake.kv["job:J1:inputs"])
    assert {p["source"] for p in payload} == {"pending"}
    assert any(p["url"] and p["id"] == url_id for p in payload)
    assert any(p["url"] is None and p["id"] == b64_id for p in payload)

    asyncio.run(job_manager._write_inputs("J1", imgs, {url_id: "cached", b64_id: "fresh"}))
    resolved = {p["id"]: p["source"] for p in json.loads(fake.kv["job:J1:inputs"])}
    assert resolved[url_id] == "cached"
    assert resolved[b64_id] == "fresh"


def test_get_job_status_attaches_inputs(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    fake.kv["job:J2:status"] = JobStatus(job_id="J2", status="processing", progress=40.0).json()
    fake.kv["job:J2:inputs"] = json.dumps([{"id": "x", "url": "https://e.com/a.jpg", "source": "cached"}])
    st = asyncio.run(job_manager.get_job_status("J2"))
    assert st.inputs is not None and st.inputs[0].source == "cached"


def test_get_job_status_no_inputs_key_is_none(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    fake.kv["job:J3:status"] = JobStatus(job_id="J3", status="queued", progress=0.0).json()
    assert asyncio.run(job_manager.get_job_status("J3")).inputs is None


def test_process_job_logic_classifies_input_sources(monkeypatch):
    """End-to-end: a cache-hit -> 'cached', a downloaded miss -> 'fresh', a load
    failure -> 'failed', persisted to job:{id}:inputs. Validates the cache-source
    signal this feature exists for."""
    from unittest.mock import AsyncMock, Mock
    from app.core import feature_cache
    from app.core.image_processor import ImageProcessor
    from app.schemas.comparator import FailedImage

    fake = FakeRedis()

    async def _incr(k):
        fake.kv[k] = int(fake.kv.get(k, 0)) + 1
        return fake.kv[k]

    fake.incr = _incr
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    monkeypatch.setattr(cache_service, "safe_decrement_key", AsyncMock())

    a = ImageInput(url="https://x/a.jpg")  # cache hit  -> cached
    b = ImageInput(url="https://x/b.jpg")  # miss+loads -> fresh
    c = ImageInput(url="https://x/c.jpg")  # miss+fails -> failed
    feat = {"phash": object(), "hist": object()}
    monkeypatch.setattr(feature_cache, "get_features", AsyncMock(return_value={str(a.url): feat}))
    monkeypatch.setattr(feature_cache, "set_features", AsyncMock())
    monkeypatch.setattr(ImageProcessor, "load_images",
                        AsyncMock(return_value=({b.id: object()}, [FailedImage(id=c.id, url=c.url)])))
    monkeypatch.setattr(ImageProcessor, "extract_features_for", Mock(return_value={b.id: feat}))
    monkeypatch.setattr(ImageProcessor, "compare_features", Mock(return_value=[]))

    asyncio.run(job_manager.process_job_logic("job6", [a, b, c], 90.0))

    sources = {p["id"]: p["source"] for p in json.loads(fake.kv["job:job6:inputs"])}
    assert sources == {a.id: "cached", b.id: "fresh", c.id: "failed"}
