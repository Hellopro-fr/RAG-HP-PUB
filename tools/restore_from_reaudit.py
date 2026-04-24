"""Move reclassified-OK archives from crawls-quarantine/ back to crawls/.

Reads a re-audit JSON produced by `gcs_archive_audit.py --prefix
crawls-quarantine/`, finds entries with `category == "OK"`, and moves each
back to the target prefix via `gcloud storage mv`. Defensive:
  - Skips any entry whose destination already exists (e.g. a Phase 1A
    upload filled that slot).
  - Never moves non-OK entries (CORRUPTED, WRONG_NAME, ROW_COUNT_MISMATCH).
  - Supports a dry-run mode (no moves; just planning + log).

Run:
    python tools/restore_from_reaudit.py \
        --input quarantine_reaudit.json \
        --bucket <name> \
        --target-prefix crawls/ \
        --log phase2_restore_log.md \
        [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _run_gcloud(args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud command. Centralized for test patching."""
    return subprocess.run(["gcloud"] + args, check=check, capture_output=True, text=True)


def gcloud_move(src_uri: str, dst_uri: str) -> None:
    """Move a GCS object via `gcloud storage mv`. Raises on failure."""
    _run_gcloud(["storage", "mv", src_uri, dst_uri])


def _exists(gs_uri: str) -> bool:
    """Return True if an object exists at gs_uri.

    `gcloud storage ls <obj>` exits 0 when present; non-zero when the URL
    matches no objects. We use check=False and inspect the return code
    rather than raising on absence (which is a normal outcome, not an error).
    """
    result = _run_gcloud(["storage", "ls", gs_uri], check=False)
    return result.returncode == 0


def restore(
    input_path: Path,
    bucket: str,
    target_prefix: str,
    log_path: Path,
    dry_run: bool,
) -> int:
    """Restore reclassified-OK archives back to `target_prefix`.

    Returns the count of moves performed (or would-have-been moves in dry-run).
    """
    with open(input_path, "r", encoding="utf-8") as f:
        audit = json.load(f)

    log_lines: List[str] = [
        f"# Phase 2.3 restore log — {datetime.now(timezone.utc).isoformat()}",
        f"Bucket: {bucket}",
        f"Target prefix: {target_prefix}",
        f"Dry-run: {dry_run}",
        f"Source: {input_path}",
        "",
    ]

    count = 0
    for entry in audit.get("archives", []):
        if entry.get("category") != "OK":
            continue

        obj = entry["object_name"]
        basename = obj.rsplit("/", 1)[-1]
        src_uri = f"gs://{bucket}/{obj}"
        dst_uri = f"gs://{bucket}/{target_prefix.rstrip('/')}/{basename}"
        crawl_id = entry.get("crawl_id", "?")
        tags = ",".join(entry.get("secondary_tags", [])) or "-"

        if _exists(dst_uri):
            log_lines.append(
                f"{'DRY-RUN ' if dry_run else ''}SKIP {crawl_id}: "
                f"{dst_uri} already exists (tags={tags})"
            )
            continue

        if dry_run:
            log_lines.append(
                f"DRY-RUN RESTORED {crawl_id}: {src_uri} -> {dst_uri} (tags={tags})"
            )
        else:
            try:
                gcloud_move(src_uri, dst_uri)
                log_lines.append(
                    f"RESTORED {crawl_id}: {src_uri} -> {dst_uri} (tags={tags})"
                )
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or "").strip() if hasattr(e, "stderr") else str(e)
                log_lines.append(f"FAILED {crawl_id}: {stderr}")
                continue
        count += 1

    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return count


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Surgically move reclassified-OK archives out of quarantine."
    )
    parser.add_argument("--input", required=True, help="Re-audit JSON path")
    parser.add_argument("--bucket", required=True, help="GCS bucket name")
    parser.add_argument("--target-prefix", default="crawls/",
                        help="Destination prefix (default: crawls/)")
    parser.add_argument("--log", required=True, help="Output log markdown path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't move; just plan and log")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    count = restore(
        input_path=Path(args.input),
        bucket=args.bucket,
        target_prefix=args.target_prefix,
        log_path=Path(args.log),
        dry_run=args.dry_run,
    )
    mode = "would restore" if args.dry_run else "restored"
    print(f"{mode} {count} archive(s). Log: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
