# tools/stash_crawls_batch.py
"""Sequentially stash a list of terminal crawls to GCS.

Reads an input file of the form:
    <size>\\t<crawl_id>[ → <marker>]

Lines with a marker (anything containing the "→" arrow) are skipped.
Remaining IDs are stashed one at a time via POST /crawler/stash/{id},
respecting disk-pressure on /mnt/data and verifying GCS arrival before
moving to the next crawl. Resume-safe via per-class state files written
next to the input file.

Usage:
    python tools/stash_crawls_batch.py <input-file> [--dry-run]
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("stash_crawls_batch")


class FatalError(Exception):
    """Aborts the batch run; written to <input>.stash_failed.txt if attributable to a crawl."""


_SIZE_MULT = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def parse_size(s: str) -> int:
    """Convert a human-readable size like '106M' or '1.1G' to bytes."""
    s = s.strip()
    if not s:
        raise ValueError("empty size string")
    unit = s[-1].upper()
    if unit not in _SIZE_MULT:
        raise ValueError(f"unknown size unit: {unit!r}")
    num = float(s[:-1])
    return int(num * _SIZE_MULT[unit])


def parse_line(raw: str) -> tuple[int, str] | None:
    """Parse one line of the input file.

    Returns (size_bytes, crawl_id) for processable lines, or None for:
    - blank lines
    - lines containing "→" (marker present, intentionally skipped)
    - malformed lines (no tab, non-digit id, unknown size unit)
    """
    line = raw.rstrip()
    if not line:
        return None
    parts = line.split("\t", 1)
    if len(parts) != 2:
        return None
    size_str, rest = parts
    if "→" in rest:
        return None
    crawl_id = rest.strip()
    if not crawl_id.isdigit():
        return None
    try:
        return parse_size(size_str), crawl_id
    except ValueError:
        return None


def load_work_list(input_path: Path, done: set[str]) -> list[tuple[int, str]]:
    """Parse the input file, drop markers, drop done IDs, sort ascending by size.

    Raises FatalError if duplicate IDs appear in the input.
    """
    text = input_path.read_text(encoding="utf-8")
    seen: dict[str, int] = {}
    for line_no, raw in enumerate(text.splitlines(keepends=True), start=1):
        result = parse_line(raw)
        if result is None:
            continue
        _, crawl_id = result
        if crawl_id in seen:
            raise FatalError(
                f"Duplicate crawl_id '{crawl_id}' at line {line_no} "
                f"(first seen at line {seen[crawl_id]})"
            )
        seen[crawl_id] = line_no

    work: list[tuple[int, str]] = []
    for raw in text.splitlines(keepends=True):
        result = parse_line(raw)
        if result is None:
            continue
        size_bytes, crawl_id = result
        if crawl_id in done:
            continue
        work.append((size_bytes, crawl_id))

    work.sort(key=lambda t: t[0])
    return work


class BatchState:
    """Append-only per-class state files next to the input file."""

    def __init__(self, input_path: Path) -> None:
        self.input_path = input_path
        self.done_path = Path(f"{input_path}.stash_done.txt")
        self.done: set[str] = self._load_done()

    def _load_done(self) -> set[str]:
        if not self.done_path.exists():
            return set()
        return {
            line.strip()
            for line in self.done_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def append(self, klass: str, crawl_id: str, detail: str = "") -> None:
        path = Path(f"{self.input_path}.stash_{klass}.txt")
        if klass == "done":
            line = f"{crawl_id}\n"
        else:
            ts = datetime.now(UTC).isoformat(timespec="seconds")
            if detail:
                line = f"{crawl_id}\t{detail}\t{ts}\n"
            else:
                line = f"{crawl_id}\t{ts}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        if klass == "done":
            self.done.add(crawl_id)
