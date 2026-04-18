"""GCS Archive Audit Tool.

Audits every archive in gs://{bucket}/crawls/, classifies each, writes a
JSON report, and optionally remediates via --delete or --quarantine.

Shells out to `gcloud storage` — no google-cloud-storage Python dependency.
Authentication is whatever gcloud is configured with on the host.

Run:
    python tools/gcs_archive_audit.py --bucket <name> [--output report.json]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union


def _run_gcloud(args: List[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a gcloud command via subprocess. Centralized so tests can patch a single point."""
    cmd = ["gcloud"] + args
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def check_gcloud_auth() -> None:
    """Ensure gcloud has an active authenticated account. Exit with a helpful message if not."""
    try:
        result = _run_gcloud(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
    except FileNotFoundError:
        print("ERROR: `gcloud` CLI not found on PATH. Install Google Cloud SDK.", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: `gcloud auth list` failed: {e.stderr}", file=sys.stderr)
        sys.exit(2)

    active = (result.stdout or "").strip()
    if not active:
        print(
            "ERROR: No active gcloud account. Run one of:\n"
            "  gcloud auth login\n"
            "  gcloud auth activate-service-account --key-file=<path>",
            file=sys.stderr,
        )
        sys.exit(2)


def gcloud_ls(uri: str, long: bool = False) -> List[Union[str, Tuple[int, str]]]:
    """List objects under a GCS URI.

    When long=False: returns a list of URIs (strings).
    When long=True: returns a list of (size_bytes, uri) tuples. Non-parseable
    lines are skipped (e.g., the trailing 'TOTAL:' summary line).
    """
    args = ["storage", "ls"]
    if long:
        args.append("-l")
    args.append(uri)
    try:
        result = _run_gcloud(args)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gcloud storage ls failed for '{uri}': {e.stderr}", file=sys.stderr)
        return []

    lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
    if not long:
        return [line for line in lines if line.startswith("gs://")]

    # Long format:
    #   <size>  <YYYY-MM-DDTHH:MM:SSZ>  gs://bucket/path
    # We want (size, uri) tuples, skipping any line that doesn't parse.
    out: List[Tuple[int, str]] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        if not parts[-1].startswith("gs://"):
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        out.append((size, parts[-1]))
    return out


def gcloud_download(obj_uri: str, local_path: Path) -> None:
    """Download a GCS object to a local path. Raises on failure."""
    _run_gcloud(["storage", "cp", obj_uri, str(local_path)])


def gcloud_delete(obj_uri: str) -> None:
    """Delete a GCS object. Raises on failure."""
    _run_gcloud(["storage", "rm", obj_uri])


def gcloud_move(src_uri: str, dst_uri: str) -> None:
    """Move (rename) a GCS object. Server-side where possible. Raises on failure."""
    _run_gcloud(["storage", "mv", src_uri, dst_uri])


def extract_crawl_id(object_name: str) -> Optional[str]:
    """Given `crawls/4365.tar.gz` or `crawls/4365.tmp.tar.gz` or a full gs:// URI,
    return the crawl_id component. Returns None if the name doesn't match.

    Examples:
        'crawls/4365.tar.gz'         -> '4365'
        'crawls/4365.tmp.tar.gz'     -> '4365'
        'gs://b/crawls/4365.tar.gz'  -> '4365'
        'gs://b/crawls/weird'        -> None
    """
    # Strip gs://bucket/ prefix if present
    path = object_name
    if path.startswith("gs://"):
        # gs://bucket/rest/of/path → rest/of/path
        parts = path.split("/", 3)
        path = parts[3] if len(parts) >= 4 else ""

    # Take the basename and strip known suffixes
    base = path.rsplit("/", 1)[-1]
    for suffix in (".tmp.tar.gz", ".tar.gz"):
        if base.endswith(suffix):
            crawl_id = base[: -len(suffix)]
            if crawl_id:
                return crawl_id
    return None
