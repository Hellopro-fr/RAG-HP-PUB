"""GCS Archive Audit Tool.

Audits every archive in gs://{bucket}/crawls/, classifies each, writes a
JSON report, and optionally remediates via --delete or --quarantine.

Shells out to `gcloud storage` — no google-cloud-storage Python dependency.
Authentication is whatever gcloud is configured with on the host.

Run:
    python tools/gcs_archive_audit.py --bucket <name> [--output report.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


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


# ---- Categories ----

OK = "OK"
WRONG_NAME = "WRONG_NAME"
CORRUPTED = "CORRUPTED"
MISSING_PAYLOAD = "MISSING_PAYLOAD"
MISSING_MARKER = "MISSING_MARKER"
ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
DUPLICATE = "DUPLICATE"
INSPECTION_FAILED = "INSPECTION_FAILED"


def classify_by_name(object_name: str) -> Optional[str]:
    """Return WRONG_NAME if the object name ends in `.tmp.tar.gz`, else None.

    Name-only screening — does not download or open the archive.
    """
    base = object_name.rsplit("/", 1)[-1]
    if base.endswith(".tmp.tar.gz"):
        return WRONG_NAME
    return None


def inspect_archive(local_tar_path: Path) -> Tuple[str, Dict]:
    """Open a .tar.gz and classify it.

    Returns (category, details). `details` always includes the callback-payload
    and marker read state; when row count is checked, it also includes
    `expected_count` and `actual_count`.
    """
    details: Dict = {}

    # 1. Integrity — can we open the tar at all?
    try:
        tar = tarfile.open(str(local_tar_path), "r:gz")
    except (tarfile.TarError, OSError, EOFError) as e:
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        members = tar.getmembers()  # forces reading the full index; may raise on truncated tars
    except (tarfile.TarError, OSError, EOFError) as e:
        tar.close()
        details["error"] = f"{type(e).__name__}: {e}"
        return CORRUPTED, details

    try:
        # 2. Extract _callback_payload.json
        payload = _read_json_member(tar, "_callback_payload.json")
        if payload is None:
            details["missing"] = "_callback_payload.json"
            return MISSING_PAYLOAD, details
        details["payload"] = payload

        # 3. Extract _completion_marker.json
        marker = _read_json_member(tar, "_completion_marker.json")
        if marker is None:
            details["missing"] = "_completion_marker.json"
            return MISSING_MARKER, details
        details["marker"] = marker

        # 4. Row count check
        domain = payload.get("domain")
        if not domain:
            # Payload exists but lacks domain — treat as malformed payload
            details["missing"] = "domain field in _callback_payload.json"
            return MISSING_PAYLOAD, details

        expected = payload.get("stored_files_count")
        if expected is None:
            expected = payload.get("success")
        if expected is None:
            # Payload lacks any count field — treat as malformed
            details["missing"] = "stored_files_count/success field in _callback_payload.json"
            return MISSING_PAYLOAD, details

        actual = _count_dataset_files(members, domain)
        details["expected_count"] = int(expected)
        details["actual_count"] = actual

        if int(expected) != actual:
            return ROW_COUNT_MISMATCH, details

        return OK, details
    finally:
        tar.close()


def _read_json_member(tar: tarfile.TarFile, name: str) -> Optional[Dict]:
    """Read and parse a JSON file from the tar by exact member name. Returns None if absent."""
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    try:
        f = tar.extractfile(member)
        if f is None:
            return None
        return json.loads(f.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def _count_dataset_files(members: List[tarfile.TarInfo], domain: str) -> int:
    """Count .json files under storage/datasets/{domain}/ (or sanitized variant).

    Returns the number of JSON files directly under the dataset directory.
    Matches the crawler's convention: one JSON file per successfully crawled URL.
    """
    sanitized = domain.replace(".", "-")
    candidates = [f"storage/datasets/{domain}/", f"storage/datasets/{sanitized}/"]

    for prefix in candidates:
        count = 0
        found_dir = False
        for m in members:
            if m.name.startswith(prefix):
                found_dir = True
                # Only count files (not nested directories), and only .json
                name_after_prefix = m.name[len(prefix):]
                if m.isfile() and "/" not in name_after_prefix and name_after_prefix.endswith(".json"):
                    count += 1
        if found_dir:
            return count
    return 0
