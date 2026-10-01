"""Chunk-count ceiling guard for embed_data_clean.

A pathological item (multi-MB text / base64 blob) chunks into thousands of
pieces; each carries a 1024-float vector (~18 KB serialized), so the published
output blows RabbitMQ's 128 MiB max_message_size. enforce_chunk_ceiling rejects
such items EARLY (before embedding) as a permanent ValueError -> DLQ, no retry.

limits.py has only `os` as a dependency, so it loads locally by file path
(the rest of common_utils.embedding pulls grpc/tokenizer stacks absent here).
No pytest dependency: runnable via `python tests/test_embedding_limits.py`.
"""
import importlib.util
from pathlib import Path

LIMITS_PATH = (
    Path(__file__).resolve().parents[1]
    / "src" / "common_utils" / "embedding" / "limits.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("limits_under_test", LIMITS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _raises_value_error(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ValueError as e:
        return str(e)
    raise AssertionError("expected ValueError, none raised")


def test_over_ceiling_raises_payload_too_large():
    lim = _load()
    msg = _raises_value_error(lim.enforce_chunk_ceiling, 5001, max_chunks=5000)
    assert "payload_too_large" in msg


def test_at_ceiling_does_not_raise():
    lim = _load()
    lim.enforce_chunk_ceiling(5000, max_chunks=5000)  # boundary: allowed


def test_under_ceiling_does_not_raise():
    lim = _load()
    lim.enforce_chunk_ceiling(3, max_chunks=5000)


def test_default_ceiling_is_5000():
    lim = _load()
    assert lim.MAX_CHUNKS_PER_ITEM == 5000


def test_message_includes_count_and_source():
    lim = _load()
    msg = _raises_value_error(lim.enforce_chunk_ceiling, 9999, max_chunks=100, source="siteweb")
    assert "9999" in msg
    assert "siteweb" in msg


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run()
