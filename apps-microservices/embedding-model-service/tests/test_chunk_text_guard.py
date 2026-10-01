"""Pathological-input guard for chunk_text.

Root cause: RecursiveCharacterTextSplitter with a tokenizer-based length_function
degrades to one encode() PER CHARACTER when the text has a long run with no
whitespace/newline separator (base64 blobs, minified JS, OCR noise), blowing the
gRPC deadline -> DEADLINE_EXCEEDED -> DLQ. These payloads must take a single-pass
token-window path instead.

application.chunking has no heavy ML deps, so it loads locally (only `re`). We
load it by file path to avoid importing embedding_use_case (torch, tritonclient,
sentence_transformers, langchain), which are absent on dev machines.
"""
import importlib.util
from pathlib import Path

CHUNKING_PATH = (
    Path(__file__).resolve().parents[1] / "application" / "chunking.py"
)


def _load_chunking():
    spec = importlib.util.spec_from_file_location("chunking_under_test", CHUNKING_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ch = _load_chunking()

# Fake tokenizer: 1 token id per character. encode/decode round-trip losslessly,
# so we can assert exact windows without the real sentencepiece tokenizer.
def _encode(text):
    return [ord(c) for c in text]


def _decode(ids):
    return "".join(chr(i) for i in ids)


def test_normal_text_stays_on_rcts_path():
    assert ch.needs_token_window("un texte normal avec des espaces\net des lignes") is False


def test_separatorless_blob_triggers_fallback():
    blob = "A" * (ch.MAX_SEPARATORLESS_RUN + 1)  # no whitespace at all
    assert ch.longest_separatorless_run(blob) == len(blob)
    assert ch.needs_token_window(blob) is True


def test_huge_but_separated_text_triggers_fallback():
    huge = ("mot " * (ch.MAX_RCTS_CHARS // 4 + 10))  # separators present, but > MAX_RCTS_CHARS
    assert ch.longest_separatorless_run(huge) <= 3
    assert ch.needs_token_window(huge) is True


def test_token_window_short_text_returns_single_chunk():
    text = "abc"
    assert ch.chunk_by_token_window(_encode, _decode, text, chunk_size=10, chunk_overlap=3) == ["abc"]


def test_token_window_splits_with_overlap_and_bounds():
    text = "".join(chr(ord("a") + (i % 26)) for i in range(25))  # 25 chars
    chunks = ch.chunk_by_token_window(_encode, _decode, text, chunk_size=10, chunk_overlap=3)
    # step = 10 - 3 = 7 -> starts 0,7,14,21 -> 4 chunks
    assert len(chunks) == 4
    assert all(len(c) <= 10 for c in chunks)          # never exceeds chunk_size
    assert chunks[0] == text[0:10]
    assert chunks[1] == text[7:17]                    # 3-char overlap with prev
    assert chunks[-1] == text[21:25]


def test_token_window_bounded_on_pathological_input():
    """The regression guard: a huge separatorless blob must NOT hang and must
    produce a bounded number of chunks (this is what the deadline bug could not do)."""
    blob = "Z" * 100_000
    chunks = ch.chunk_by_token_window(_encode, _decode, blob, chunk_size=500, chunk_overlap=100)
    step = 500 - 100
    expected = (100_000 - 500 + step - 1) // step + 1  # ceil over the stride, +first window
    assert len(chunks) == expected
    assert all(len(c) <= 500 for c in chunks)


def test_overlap_ge_size_does_not_infinite_loop():
    text = "x" * 50
    chunks = ch.chunk_by_token_window(_encode, _decode, text, chunk_size=10, chunk_overlap=10)
    # step clamps to >=1, so it terminates
    assert len(chunks) >= 1
    assert all(len(c) <= 10 for c in chunks)


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run()
