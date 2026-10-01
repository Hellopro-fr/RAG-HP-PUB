"""Payload-size guard for the embedding pipeline.

A pathological item (multi-MB text / base64 blob that survived HTML cleaning)
chunks into thousands of pieces; each output record carries a 1024-float vector
(~18 KB serialized). Beyond ~7,450 chunks the published message exceeds
RabbitMQ's 128 MiB max_message_size and the broker rejects the publish
(PRECONDITION_FAILED), which the consumer retries into a loop.

enforce_chunk_ceiling rejects such items EARLY (right after chunking, before the
expensive GetEmbeddings) as a plain ValueError, which the embedding-service
consumer routes straight to the DLQ (permanent, no retry). The DLQ'd items are
the samples for diagnosing the upstream cleaning gap.

Ceiling is derived from the byte budget, not guessed:
  ~100 MiB safe budget / ~18 KB per chunk ~= 5,800 -> rounded down to 5,000
  (5,000 chunks ~= 90 MiB worst case, 38 MiB headroom under the 128 MiB wall).
5,000 chunks ~= 2M tokens of unique text in ONE item -> far above any legitimate
page or document, so the guard is inert for real data.
"""
import os

# ponytail: env-tunable ceiling. Raise only if a real corpus legitimately needs
# more chunks per item (it never should — split oversized documents upstream).
MAX_CHUNKS_PER_ITEM = int(os.getenv("MAX_CHUNKS_PER_ITEM") or 5000)


def enforce_chunk_ceiling(n_chunks: int, max_chunks: int | None = None, source: str = "") -> None:
    """Raise ValueError (permanent -> DLQ) when an item produces too many chunks."""
    limit = MAX_CHUNKS_PER_ITEM if max_chunks is None else max_chunks
    if n_chunks > limit:
        detail = f" (source={source})" if source else ""
        raise ValueError(
            f"payload_too_large: {n_chunks} chunks > MAX_CHUNKS_PER_ITEM={limit}{detail}"
        )
