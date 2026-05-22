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
from datetime import datetime, timezone
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
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if detail:
                line = f"{crawl_id}\t{detail}\t{ts}\n"
            else:
                line = f"{crawl_id}\t{ts}\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        if klass == "done":
            self.done.add(crawl_id)


# ============================================================
# T1: Disk guard + timeout + existence checks
# ============================================================
import os
import shutil
import subprocess
import time

# Disk guard knobs
SAFETY_MARGIN_BYTES = 10 * 1024**3        # 10 GB headroom on top of source size
DISK_WAIT_MAX_SECONDS = 30 * 60           # 30 min total wait per crawl
DISK_WAIT_INTERVAL = 60                   # poll every 60s

# Per-crawl timeout knobs (max 60 min, min 10 min, 3 min per GB)
_TIMEOUT_MIN = 600
_TIMEOUT_MAX = 3600
_TIMEOUT_PER_GB = 180


def per_crawl_timeout(size_bytes: int) -> int:
    """Upload-completion timeout in seconds, scaled by source size."""
    size_g = size_bytes / 1024**3
    return int(min(_TIMEOUT_MAX, max(_TIMEOUT_MIN, size_g * _TIMEOUT_PER_GB)))


def local_tar_exists(crawl_id: str, stash_local_dir: str) -> bool:
    return os.path.exists(os.path.join(stash_local_dir, f"{crawl_id}.tar.gz"))


def dead_letter_exists(crawl_id: str, dead_letter_dir: str) -> bool:
    return os.path.exists(os.path.join(dead_letter_dir, f"{crawl_id}.tar.gz"))


def gcs_tar_exists(crawl_id: str, bucket: str, prefix: str) -> bool:
    """True iff `gcloud storage ls gs://{bucket}/{prefix}/{crawl_id}.tar.gz` exits 0."""
    uri = f"gs://{bucket}/{prefix}/{crawl_id}.tar.gz"
    result = subprocess.run(
        ["gcloud", "storage", "ls", uri],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def wait_for_disk(needed_bytes: int, disk_target: str) -> None:
    """Block until free space on `disk_target` >= needed_bytes + 10 GB, or raise."""
    threshold = needed_bytes + SAFETY_MARGIN_BYTES
    deadline = time.time() + DISK_WAIT_MAX_SECONDS
    while True:
        free = shutil.disk_usage(disk_target).free
        if free >= threshold:
            return
        if time.time() > deadline:
            raise FatalError(
                f"Disk free {free / 1024**3:.1f} GB < needed "
                f"{threshold / 1024**3:.1f} GB after {DISK_WAIT_MAX_SECONDS}s"
            )
        logger.warning(
            "Disk free %.1f GB < needed %.1f GB; sleeping %ds",
            free / 1024**3,
            threshold / 1024**3,
            DISK_WAIT_INTERVAL,
        )
        time.sleep(DISK_WAIT_INTERVAL)


# ============================================================
# T2: HTTP post + per-crawl process loop + signals
# ============================================================
import signal
import urllib.error
import urllib.request
from dataclasses import dataclass

_stop_requested = False


def install_signal_handlers() -> None:
    """SIGINT/SIGTERM set _stop_requested; process_crawl checks it between polls."""

    def _handler(signum, _frame):
        global _stop_requested
        _stop_requested = True
        logger.warning("Signal %s received — will exit after current crawl boundary", signum)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


@dataclass(frozen=True)
class Config:
    crawler_base_url: str
    stash_local_dir: str
    stash_dead_letter_dir: str
    stash_gcs_bucket: str
    stash_gcs_prefix: str
    disk_target: str
    http_timeout_seconds: int
    poll_interval_seconds: int


@dataclass
class HttpResponse:
    status_code: int
    text: str


def http_post(url: str, timeout: int) -> HttpResponse:
    """POST with empty body. Stdlib only — urllib.request.

    Returns HttpResponse with .status_code and .text. HTTP errors (4xx/5xx) are
    captured as HTTPError and converted into HttpResponse rather than raised.
    """
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(status_code=resp.status, text=body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return HttpResponse(status_code=e.code, text=body)


def process_crawl(
    size_bytes: int,
    crawl_id: str,
    state: "BatchState",
    cfg: Config,
) -> None:
    """Stash one crawl: disk-guard, POST, poll, record."""
    wait_for_disk(size_bytes, cfg.disk_target)

    url = f"{cfg.crawler_base_url}/stash/{crawl_id}"
    logger.info("POST %s (size=%.2fG)", url, size_bytes / 1024**3)
    resp = http_post(url, cfg.http_timeout_seconds)

    if resp.status_code == 404:
        logger.warning("404 on %s — Redis lost job", crawl_id)
        state.append("notfound", crawl_id)
        return
    if resp.status_code == 409:
        logger.info("409 on %s — already stashed/archived", crawl_id)
        state.append("skipped", crawl_id, resp.text[:200].replace("\n", " "))
        return
    if resp.status_code == 400:
        logger.warning("400 on %s — wrong status", crawl_id)
        state.append("invalid", crawl_id, resp.text[:200].replace("\n", " "))
        return
    if resp.status_code >= 500:
        logger.warning("5xx on %s — retrying in 30s", crawl_id)
        time.sleep(30)
        resp = http_post(url, cfg.http_timeout_seconds)
        if resp.status_code >= 500:
            detail = f"5xx persisted: {resp.text[:200]}".replace("\n", " ")
            state.append("failed", crawl_id, detail)
            raise FatalError(f"5xx persisted on {crawl_id}")
    if resp.status_code != 202:
        detail = f"unexpected {resp.status_code}: {resp.text[:200]}".replace("\n", " ")
        state.append("failed", crawl_id, detail)
        raise FatalError(f"Unexpected {resp.status_code} on {crawl_id}")

    timeout_s = per_crawl_timeout(size_bytes)
    deadline = time.time() + timeout_s
    logger.info("Polling completion for %s (timeout=%ds)", crawl_id, timeout_s)

    while time.time() < deadline:
        if _stop_requested:
            state.append("failed", crawl_id, "interrupted during poll")
            raise FatalError(f"Interrupted while polling {crawl_id}")
        if dead_letter_exists(crawl_id, cfg.stash_dead_letter_dir):
            state.append("failed", crawl_id, "dead_letter")
            raise FatalError(f"Upload daemon dead-lettered {crawl_id}")
        if not local_tar_exists(crawl_id, cfg.stash_local_dir):
            if gcs_tar_exists(crawl_id, cfg.stash_gcs_bucket, cfg.stash_gcs_prefix):
                state.append("done", crawl_id)
                logger.info("DONE %s", crawl_id)
                return
        time.sleep(cfg.poll_interval_seconds)

    state.append("failed", crawl_id, f"timeout after {timeout_s}s")
    raise FatalError(f"Timeout waiting for {crawl_id} ({timeout_s}s)")


# ============================================================
# T3: CLI entry + dry-run + summary
# ============================================================
import argparse
import sys


def print_dry_run(
    work_list: list[tuple[int, str]],
    cfg: Config,
    input_path: Path,
    skipped_count: int,
    done_count: int,
) -> None:
    total_bytes = sum(s for s, _ in work_list)
    free_now = shutil.disk_usage(cfg.disk_target).free
    print("=== DRY RUN ===")
    print(f"Input:      {input_path}")
    print(f"Skipped:    {skipped_count} IDs with markers")
    print(f"Resume:     {done_count} IDs in stash_done.txt")
    print(f"To process: {len(work_list)} IDs, total ~{total_bytes / 1024**3:.1f} GB")
    print()
    print("Order (ascending by size):")
    for i, (size_bytes, crawl_id) in enumerate(work_list, start=1):
        size_h = (
            f"{size_bytes / 1024**3:.1f}G"
            if size_bytes >= 1024**3
            else f"{size_bytes / 1024**2:.0f}M"
        )
        print(f"  {i:>4}. {crawl_id:<10} {size_h:>7}    timeout={per_crawl_timeout(size_bytes)}s")
    print()
    print("Config:")
    print(f"  CRAWLER_BASE_URL:        {cfg.crawler_base_url}")
    print(f"  STASH_LOCAL_DIR:         {cfg.stash_local_dir}")
    print(f"  STASH_DEAD_LETTER_DIR:   {cfg.stash_dead_letter_dir}")
    print(f"  STASH_GCS_BUCKET:        {cfg.stash_gcs_bucket}")
    print(f"  STASH_GCS_PREFIX:        {cfg.stash_gcs_prefix}")
    print(f"  DISK_TARGET:             {cfg.disk_target} (free={free_now / 1024**3:.1f}G)")
    print(f"  HTTP_TIMEOUT_SECONDS:    {cfg.http_timeout_seconds}")
    print(f"  POLL_INTERVAL_SECONDS:   {cfg.poll_interval_seconds}")
    print()
    print("No requests will be sent.")


def print_summary(input_path: Path, started_at: float) -> None:
    classes = ["done", "skipped", "invalid", "notfound", "failed"]
    counts: dict[str, int] = {}
    for klass in classes:
        path = Path(f"{input_path}.stash_{klass}.txt")
        if path.exists():
            counts[klass] = sum(
                1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        else:
            counts[klass] = 0
    elapsed = int(time.time() - started_at)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    total = sum(counts.values())
    print()
    print("=== Batch summary ===")
    print(f"Processed: {total}")
    for klass in classes:
        print(f"  {klass.capitalize():<9}{counts[klass]}")
    print(f"Elapsed: {h:02d}:{m:02d}:{s:02d}")


def _build_config_from_env() -> Config:
    bucket = os.environ.get("STASH_GCS_BUCKET", "")
    if not bucket:
        print("STASH_GCS_BUCKET environment variable is required", file=sys.stderr)
        sys.exit(2)
    return Config(
        crawler_base_url=os.environ.get("CRAWLER_BASE_URL", "http://localhost:8500/crawler"),
        stash_local_dir=os.environ.get("STASH_LOCAL_DIR", "/app/stash"),
        stash_dead_letter_dir=os.environ.get(
            "STASH_DEAD_LETTER_DIR", "crawler_archives/dead_letter"
        ),
        stash_gcs_bucket=bucket,
        stash_gcs_prefix=os.environ.get("STASH_GCS_PREFIX", "stash"),
        disk_target=os.environ.get("DISK_TARGET", "/mnt/data"),
        http_timeout_seconds=int(os.environ.get("HTTP_TIMEOUT_SECONDS", "30")),
        poll_interval_seconds=int(os.environ.get("POLL_INTERVAL_SECONDS", "10")),
    )


def _configure_logging(input_path: Path) -> None:
    log_path = Path(f"{input_path}.stash_run.log")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    logger.setLevel(logging.INFO)
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(fmt)
    file_h = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_h.setFormatter(fmt)
    logger.addHandler(stdout_h)
    logger.addHandler(file_h)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequentially stash a list of terminal crawls to GCS.",
    )
    parser.add_argument("input_file", help="Path to <size>\\t<id>[ -> marker] input file")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; make no requests.")
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    cfg = _build_config_from_env()
    _configure_logging(input_path)

    raw_text = input_path.read_text(encoding="utf-8")
    skipped_count = sum(
        1
        for raw in raw_text.splitlines()
        if "\t" in raw and "→" in raw.split("\t", 1)[1]
    )

    state = BatchState(input_path)
    done_count = len(state.done)

    try:
        work_list = load_work_list(input_path, state.done)
    except FatalError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print_dry_run(work_list, cfg, input_path, skipped_count, done_count)
        return 0

    install_signal_handlers()
    started_at = time.time()
    exit_code = 0
    try:
        logger.info("Starting batch: %d crawls to process", len(work_list))
        for size_bytes, crawl_id in work_list:
            if _stop_requested:
                logger.warning("Stop requested — exiting before next crawl")
                break
            process_crawl(size_bytes, crawl_id, state, cfg)
        logger.info("Batch finished successfully")
    except FatalError as e:
        logger.error("FATAL: %s", e)
        exit_code = 1
    except KeyboardInterrupt:
        logger.warning("KeyboardInterrupt received")
        exit_code = 130
    finally:
        print_summary(input_path, started_at)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
