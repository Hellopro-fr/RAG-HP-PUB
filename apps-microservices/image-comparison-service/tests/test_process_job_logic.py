"""Unit tests for JobManager.process_job_logic — the Design-C cache-aside
orchestration (all-hit / partial-hit / content partition / empty-guard /
feature-cache kill-switch). Everything I/O is mocked; patch where used.

Run on the VM (or any box with the service deps cv2/imagehash/pillow installed):
    cd apps-microservices/image-comparison-service
    python -m pytest tests/test_process_job_logic.py -v

HIGHEST-VALUE REGRESSION SPOT (test_all_cache_hit_skips_download):
process_job_logic guards emptiness on the MERGED feature map
    all_features = {**cached_features, **fresh_features}
NOT on the freshly-downloaded features. A naive cache-aside refactor that
guards on `fresh_features` would make an all-cache-hit job (nothing
downloaded -> fresh empty) wrongly raise "No valid images", silently
breaking the entire cache-hit fast path — the whole point of Design-C.
The all-hit test pins exactly that, and also that the cached features
(keyed by inp.id) still flow into compare_features.
"""
import json
import pytest
from unittest.mock import AsyncMock, Mock

from common_utils.redis import cache_service
from app.core import feature_cache, job_manager as jm_mod
from app.core.config import settings
from app.core.image_processor import ImageProcessor
from app.schemas.comparator import ImageInput


@pytest.fixture
def patched(monkeypatch):
    """Mock every I/O seam process_job_logic touches (patched where used).

    - cache_service.redis_client: AsyncMock — process_job_logic calls .incr/.set on it directly.
    - cache_service.safe_decrement_key: AsyncMock — the finally-block global-counter decrement.
    - feature_cache.get_features / set_features: AsyncMock — the cache-aside read/write seam.
    - ImageProcessor.load_images: AsyncMock — the download seam.
    - ImageProcessor.extract_features_for / compare_features: sync Mock — both run via
      anyio.to_thread.run_sync, so plain (non-async) mocks are correct.
    """
    monkeypatch.setattr(cache_service, "redis_client", AsyncMock())
    monkeypatch.setattr(cache_service, "safe_decrement_key", AsyncMock())
    monkeypatch.setattr(feature_cache, "get_features", AsyncMock(return_value={}))
    monkeypatch.setattr(feature_cache, "set_features", AsyncMock())
    monkeypatch.setattr(ImageProcessor, "load_images", AsyncMock(return_value=({}, [])))
    monkeypatch.setattr(ImageProcessor, "extract_features_for", Mock(return_value={}))
    monkeypatch.setattr(ImageProcessor, "compare_features", Mock(return_value=[]))


def _feat():
    """Sentinel feature; extract_features_for/compare_features are mocked, so contents never matter."""
    return {"phash": object(), "hist": object()}


@pytest.mark.asyncio
async def test_all_cache_hit_skips_download(patched):
    # Every URL hits the cache -> nothing downloaded, nothing cached, fresh map empty.
    # The empty-guard must pass on the MERGED map; cached features (keyed by id) must
    # still reach the comparison stage. This is the highest-value regression spot.
    jm = jm_mod.JobManager()
    a = ImageInput(url="https://x/a.jpg")
    b = ImageInput(url="https://x/b.jpg")
    feature_cache.get_features.return_value = {str(a.url): _feat(), str(b.url): _feat()}

    res = await jm.process_job_logic("job1", [a, b], 90.0)

    ImageProcessor.load_images.assert_awaited_once_with([])      # nothing downloaded
    feature_cache.set_features.assert_awaited_once_with({})      # nothing to cache
    compared = ImageProcessor.compare_features.call_args.args[0]  # merged map -> comparison
    assert set(compared.keys()) == {a.id, b.id}                 # cached features keyed by id
    assert res.status == "finished"


@pytest.mark.asyncio
async def test_partial_hit_downloads_only_misses(patched):
    # a hits cache, b misses -> only b downloaded, only b's URL cached. The merged map
    # fed to compare_features is cached(a, by id) + fresh(b, by id).
    jm = jm_mod.JobManager()
    a = ImageInput(url="https://x/a.jpg")
    b = ImageInput(url="https://x/b.jpg")
    feature_cache.get_features.return_value = {str(a.url): _feat()}     # a hit, b miss
    ImageProcessor.load_images.return_value = ({b.id: object()}, [])
    ImageProcessor.extract_features_for.return_value = {b.id: _feat()}

    await jm.process_job_logic("job2", [a, b], 90.0)

    (to_load,), _ = ImageProcessor.load_images.await_args
    assert [i.id for i in to_load] == [b.id]                          # only the miss downloaded
    cached_keys = feature_cache.set_features.await_args.args[0].keys()
    assert set(cached_keys) == {str(b.url)}                           # only the fresh url-miss cached
    compared = ImageProcessor.compare_features.call_args.args[0]
    assert set(compared.keys()) == {a.id, b.id}                       # merge keyed by id, not url


@pytest.mark.asyncio
async def test_content_input_downloaded_not_cached(patched):
    # base64 `content` input: downloaded + extracted, but NEVER cached (no cacheable URL key).
    jm = jm_mod.JobManager()
    c = ImageInput(content="data:image/png;base64,AAAA")
    ImageProcessor.load_images.return_value = ({c.id: object()}, [])
    ImageProcessor.extract_features_for.return_value = {c.id: _feat()}

    await jm.process_job_logic("job3", [c], 90.0)

    (to_load,), _ = ImageProcessor.load_images.await_args
    assert c.id in [i.id for i in to_load]                            # content IS downloaded
    feature_cache.set_features.assert_awaited_once_with({})           # content NOT cached


@pytest.mark.asyncio
async def test_no_valid_images_raises(patched):
    # all miss + nothing loads + nothing extracted -> merged map empty -> raise.
    jm = jm_mod.JobManager()
    a = ImageInput(url="https://x/a.jpg")
    with pytest.raises(Exception, match="No valid images"):
        await jm.process_job_logic("job4", [a], 90.0)


@pytest.mark.asyncio
async def test_processing_status_uses_short_ttl_terminal_uses_long(patched):
    # Regression for the stuck-'processing'-after-restart bug. A 'processing' status write must
    # expire after PROCESSING_STATUS_TTL_S (worker max runtime + grace), NOT the 24h JOB_RESULT_TTL,
    # so an orphaned job (worker restarted mid-job, nothing flips it terminal) self-heals to 404.
    # Terminal 'finished' status + the result payload keep the long TTL.
    jm = jm_mod.JobManager()
    a = ImageInput(url="https://x/a.jpg")
    feature_cache.get_features.return_value = {str(a.url): _feat()}

    await jm.process_job_logic("jobttl", [a], 90.0)

    status_ttls = {}   # status string -> ex applied
    result_ttl = None
    for call in cache_service.redis_client.set.call_args_list:
        key, val = call.args[0], call.args[1]
        ex = call.kwargs.get("ex")
        if key == "job:jobttl:status":
            status_ttls[json.loads(val)["status"]] = ex
        elif key == "job:jobttl:result":
            result_ttl = ex

    assert status_ttls["processing"] == settings.PROCESSING_STATUS_TTL_S   # non-terminal -> short
    assert status_ttls["finished"] == settings.JOB_RESULT_TTL              # terminal -> long
    assert result_ttl == settings.JOB_RESULT_TTL                          # result payload -> long
    # Safety invariant: TTL must exceed the deadline (a live job refreshes on each write, gaps
    # <= deadline) or a real in-flight job would expire mid-flight; and stay under the 24h floor.
    assert settings.PROCESSING_DEADLINE_S < settings.PROCESSING_STATUS_TTL_S < settings.JOB_RESULT_TTL


@pytest.mark.asyncio
async def test_feature_cache_killswitch_disabled_downloads_all(monkeypatch):
    # Kill-switch end-to-end through the REAL feature_cache (get_features/set_features NOT
    # mocked): FEATURE_CACHE_ENABLED=false => get_features returns {} (all-miss) before
    # touching Redis, set_features no-ops. Behaves like the pre-cache path: every URL is
    # downloaded, nothing is written to the cache.
    monkeypatch.setattr(settings, "FEATURE_CACHE_ENABLED", False)
    redis_mock = AsyncMock()
    monkeypatch.setattr(cache_service, "redis_client", redis_mock)
    monkeypatch.setattr(cache_service, "safe_decrement_key", AsyncMock())
    monkeypatch.setattr(ImageProcessor, "compare_features", Mock(return_value=[]))

    jm = jm_mod.JobManager()
    a = ImageInput(url="https://x/a.jpg")
    b = ImageInput(url="https://x/b.jpg")
    monkeypatch.setattr(
        ImageProcessor, "load_images",
        AsyncMock(return_value=({a.id: object(), b.id: object()}, [])),
    )
    monkeypatch.setattr(
        ImageProcessor, "extract_features_for",
        Mock(return_value={a.id: _feat(), b.id: _feat()}),
    )

    res = await jm.process_job_logic("job5", [a, b], 90.0)

    (to_load,), _ = ImageProcessor.load_images.await_args
    assert {i.id for i in to_load} == {a.id, b.id}                    # both downloaded (cache off)
    redis_mock.mget.assert_not_called()                              # real get_features short-circuited (no read)
    redis_mock.pipeline.assert_not_called()                          # real set_features no-op (no cache write)
    assert res.status == "finished"
