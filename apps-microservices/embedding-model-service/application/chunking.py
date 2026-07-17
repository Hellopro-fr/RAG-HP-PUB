"""Pure chunking helpers — no ML deps, so the pathological-input guard is unit-testable.

RecursiveCharacterTextSplitter with a tokenizer-based length_function calls
encode() once PER CHARACTER when the text has a long run with no whitespace /
newline separator (base64 blobs, minified JS/CSS, OCR noise). On a multi-MB
payload that runs far past the gRPC deadline -> DEADLINE_EXCEEDED -> DLQ. Such
payloads take a single-pass token-window split instead (one encode, then slice).
"""
import re
from typing import Callable, List

# Beyond this many chars in a single separator-free run, RCTS degrades to the
# per-character encode path. Real words/sentences never approach this.
# ponytail: hardcoded; promote to env var only if a real corpus needs tuning.
MAX_SEPARATORLESS_RUN = 20_000
# Total-size backstop: even fully separated, a multi-MB text means millions of
# per-piece encodes, which also risks the deadline.
MAX_RCTS_CHARS = 1_000_000


def longest_separatorless_run(text: str) -> int:
    """Longest stretch with no whitespace/newline — RCTS's worst case."""
    return max((len(p) for p in re.split(r"\s+", text)), default=0)


def needs_token_window(text: str) -> bool:
    """True when RCTS would risk the tokenizer-per-character deadline blow-up."""
    return len(text) > MAX_RCTS_CHARS or longest_separatorless_run(text) > MAX_SEPARATORLESS_RUN


def chunk_by_token_window(
    encode: Callable[[str], List[int]],
    decode: Callable[[List[int]], str],
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> List[str]:
    """Encode ONCE, then slice fixed token windows with overlap.

    O(N) encode + O(chunks) decodes — bounded regardless of separators. Also
    guarantees <= chunk_size tokens per chunk (RCTS did not, so oversized pieces
    were silently truncated at the model's 512 limit).
    """
    ids = encode(text)
    if len(ids) <= chunk_size:
        return [text]
    step = max(1, chunk_size - chunk_overlap)
    chunks: List[str] = []
    for start in range(0, len(ids), step):
        chunks.append(decode(ids[start:start + chunk_size]))
        if start + chunk_size >= len(ids):
            break
    return chunks
